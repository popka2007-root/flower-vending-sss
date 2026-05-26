"""Small SQLite wrapper with safe defaults for local machine persistence.

Thread-safety model
-------------------
This class is designed for **single-threaded asyncio** use only.
- ``check_same_thread=False`` is required because SQLite finalisation
  and certain cleanup paths may run in a different asyncio task (but
  still on the same event-loop thread).
- After opening we attempt to call ``set_check_same_thread(True)``
  (Python 3.12+). If unavailable, ``check_same_thread=False`` remains
  in effect and we rely on ``_verify_thread_safety()`` instead.
- Every public method asserts it is called from the main thread that
  created the instance; see ``_verify_thread_safety()``.

If multi-threaded access is ever needed in the future:
1. Replace ``RLock`` with ``asyncio.Lock``.
2. Give each thread its own ``sqlite3.Connection`` (or use a
   connection pool).
3. Remove the ``set_check_same_thread(True)`` call.
4. Relax or remove the ``_verify_thread_safety()`` assertion.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from threading import RLock
from typing import Any, cast


SQLiteValue = str | bytes | int | float | None
SQLiteParameters = Sequence[SQLiteValue] | Mapping[str, SQLiteValue]


class SQLiteDatabase:
    """Own a SQLite connection with WAL-friendly pragmas and serialization helpers."""

    def __init__(
        self,
        path: str | Path,
        *,
        busy_timeout_ms: int = 5_000,
        enable_wal: bool = True,
        synchronous: str = "FULL",
    ) -> None:
        """Open or create a SQLite database at *path*.

        Thread-safety assumptions are documented at module level.
        """
        self._main_thread = threading.current_thread()
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._in_manual_transaction = False
        self._connection = sqlite3.connect(str(self._path), check_same_thread=False)
        if hasattr(self._connection, "set_check_same_thread"):
            self._connection.set_check_same_thread(True)
        self._connection.row_factory = sqlite3.Row
        self._configure_connection(
            busy_timeout_ms=busy_timeout_ms,
            enable_wal=enable_wal,
            synchronous=synchronous,
        )

    def _verify_thread_safety(self) -> None:
        """Assert the caller is on the same thread that created this instance.

        Raises
        ------
        RuntimeError
            If called from a different thread.
        """
        if threading.current_thread() is not self._main_thread:
            raise RuntimeError(
                f"SQLiteDatabase accessed from thread {threading.current_thread().name!r}, "
                f"but it was created on thread {self._main_thread.name!r}. "
                "This class is designed for single-threaded asyncio use only."
            )

    @property
    def path(self) -> Path:
        self._verify_thread_safety()
        return self._path

    @property
    def connection(self) -> sqlite3.Connection:
        self._verify_thread_safety()
        return self._connection

    def close(self) -> None:
        self._verify_thread_safety()
        with self._lock:
            self._connection.close()

    def executescript(self, script: str) -> None:
        self._verify_thread_safety()
        with self._lock:
            self._connection.executescript(script)
            self._connection.commit()

    def execute(
        self,
        sql: str,
        parameters: SQLiteParameters = (),
        *,
        connection: sqlite3.Connection | None = None,
    ) -> None:
        self._verify_thread_safety()
        if connection is not None:
            connection.execute(sql, parameters)
            return
        with self._lock:
            self._connection.execute(sql, parameters)
            if not self._in_manual_transaction:
                self._connection.commit()

    def executemany(
        self,
        sql: str,
        parameter_sets: Iterable[SQLiteParameters],
        *,
        connection: sqlite3.Connection | None = None,
    ) -> None:
        self._verify_thread_safety()
        if connection is not None:
            connection.executemany(sql, parameter_sets)
            return
        with self._lock:
            self._connection.executemany(sql, parameter_sets)
            if not self._in_manual_transaction:
                self._connection.commit()

    def insert(
        self,
        sql: str,
        parameters: SQLiteParameters = (),
        *,
        connection: sqlite3.Connection | None = None,
    ) -> int:
        self._verify_thread_safety()
        if connection is not None:
            cursor = connection.execute(sql, parameters)
            if cursor.lastrowid is None:
                raise RuntimeError("SQLite insert did not produce a row id")
            return cursor.lastrowid
        with self._lock:
            cursor = self._connection.execute(sql, parameters)
            if not self._in_manual_transaction:
                self._connection.commit()
            if cursor.lastrowid is None:
                raise RuntimeError("SQLite insert did not produce a row id")
            return cursor.lastrowid

    def query_one(
        self,
        sql: str,
        parameters: SQLiteParameters = (),
    ) -> sqlite3.Row | None:
        self._verify_thread_safety()
        with self._lock:
            cursor = self._connection.execute(sql, parameters)
            return cast(sqlite3.Row | None, cursor.fetchone())

    def query_all(
        self,
        sql: str,
        parameters: SQLiteParameters = (),
    ) -> list[sqlite3.Row]:
        self._verify_thread_safety()
        with self._lock:
            cursor = self._connection.execute(sql, parameters)
            return list(cast(Sequence[sqlite3.Row], cursor.fetchall()))

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        self._verify_thread_safety()
        with self._lock:
            if self._in_manual_transaction:
                yield self._connection
                return

            self._in_manual_transaction = True
            try:
                self._connection.execute("BEGIN")
                yield self._connection
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise
            finally:
                self._in_manual_transaction = False

    @contextmanager
    def savepoint(self, name: str) -> Iterator[sqlite3.Connection]:
        self._verify_thread_safety()
        with self._lock:
            try:
                self._connection.execute(f"SAVEPOINT {name}")
                yield self._connection
            except Exception:
                self._connection.execute(f"ROLLBACK TO SAVEPOINT {name}")
                raise
            else:
                self._connection.execute(f"RELEASE SAVEPOINT {name}")

    @staticmethod
    def dumps(payload: Mapping[str, Any] | list[Any] | tuple[Any, ...] | None) -> str:
        normalized = {} if payload is None else payload
        return json.dumps(normalized, ensure_ascii=False, sort_keys=True)

    @staticmethod
    def loads(raw_payload: str | None, *, default: Any = None) -> Any:
        if not raw_payload:
            return default
        return json.loads(raw_payload)

    def _configure_connection(
        self,
        *,
        busy_timeout_ms: int,
        enable_wal: bool,
        synchronous: str,
    ) -> None:
        pragmas = [
            ("foreign_keys", "ON"),
            ("busy_timeout", str(busy_timeout_ms)),
            ("synchronous", synchronous.upper()),
        ]
        if enable_wal:
            pragmas.append(("journal_mode", "WAL"))
        with self._lock:
            for name, value in pragmas:
                self._connection.execute(f"PRAGMA {name}={value}")
            self._connection.commit()

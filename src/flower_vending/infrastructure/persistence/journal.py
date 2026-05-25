"""Durable transaction journal for recovery-first persistence."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from flower_vending.app.journal import (
    ApplicationJournalRecord,
    JournalOutcome,
    intent_idempotency_key,
    outcome_idempotency_key,
)
from flower_vending.domain.events import DomainEvent
from flower_vending.infrastructure.persistence.sqlite.database import SQLiteDatabase


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


class JournalEntryKind(StrEnum):
    INTENT = "intent"
    OUTCOME = "outcome"
    EVENT = "event"
    FAULT = "fault"
    RECOVERY = "recovery"


@dataclass(frozen=True, slots=True)
class JournalEntry:
    entry_kind: JournalEntryKind
    entry_name: str
    correlation_id: str
    transaction_id: str | None = None
    machine_state: str | None = None
    transaction_status: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    idempotency_key: str | None = None
    created_at: datetime = field(default_factory=_utc_now)


class SQLiteTransactionJournal:
    """Append-only durable journal used as the recovery source of truth."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def append_entry(
        self,
        entry: JournalEntry,
        *,
        _connection: sqlite3.Connection | None = None,
    ) -> int:
        return self._database.insert(
            """
            INSERT OR IGNORE INTO transaction_journal (
                transaction_id,
                correlation_id,
                entry_kind,
                entry_name,
                machine_state,
                transaction_status,
                payload_json,
                idempotency_key,
                created_at
            ) VALUES (
                :transaction_id,
                :correlation_id,
                :entry_kind,
                :entry_name,
                :machine_state,
                :transaction_status,
                :payload_json,
                :idempotency_key,
                :created_at
            )
            """,
            {
                "transaction_id": entry.transaction_id,
                "correlation_id": entry.correlation_id,
                "entry_kind": entry.entry_kind.value,
                "entry_name": entry.entry_name,
                "machine_state": entry.machine_state,
                "transaction_status": entry.transaction_status,
                "payload_json": self._database.dumps(entry.payload),
                "idempotency_key": entry.idempotency_key,
                "created_at": entry.created_at.isoformat(),
            },
            connection=_connection,
        )

    def append_intent(
        self,
        *,
        intent_name: str,
        correlation_id: str,
        transaction_id: str | None = None,
        machine_state: str | None = None,
        transaction_status: str | None = None,
        idempotency_key: str | None = None,
        **payload: Any,
    ) -> int:
        return self.append_entry(
            JournalEntry(
                entry_kind=JournalEntryKind.INTENT,
                entry_name=intent_name,
                correlation_id=correlation_id,
                transaction_id=transaction_id,
                machine_state=machine_state,
                transaction_status=transaction_status,
                payload=dict(payload),
                idempotency_key=idempotency_key,
            )
        )

    def append_outcome(
        self,
        *,
        action_name: str,
        outcome: JournalOutcome,
        correlation_id: str,
        transaction_id: str | None = None,
        machine_state: str | None = None,
        transaction_status: str | None = None,
        idempotency_key: str | None = None,
        **payload: Any,
    ) -> int:
        return self.append_entry(
            JournalEntry(
                entry_kind=JournalEntryKind.OUTCOME,
                entry_name=f"{action_name}_{outcome.value}",
                correlation_id=correlation_id,
                transaction_id=transaction_id,
                machine_state=machine_state,
                transaction_status=transaction_status,
                payload={"action_name": action_name, "outcome": outcome.value, **dict(payload)},
                idempotency_key=idempotency_key,
            )
        )

    def record_intent(
        self,
        *,
        action_name: str,
        correlation_id: str,
        transaction_id: str,
        logical_step: str,
        machine_state: str | None = None,
        transaction_status: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> int:
        return self.append_intent(
            intent_name=action_name,
            correlation_id=correlation_id,
            transaction_id=transaction_id,
            machine_state=machine_state,
            transaction_status=transaction_status,
            idempotency_key=intent_idempotency_key(
                transaction_id=transaction_id,
                action_name=action_name,
                logical_step=logical_step,
            ),
            logical_step=logical_step,
            **dict(payload or {}),
        )

    def record_outcome(
        self,
        *,
        action_name: str,
        outcome: JournalOutcome,
        correlation_id: str,
        transaction_id: str,
        logical_step: str,
        machine_state: str | None = None,
        transaction_status: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> int:
        return self.append_outcome(
            action_name=action_name,
            outcome=outcome,
            correlation_id=correlation_id,
            transaction_id=transaction_id,
            machine_state=machine_state,
            transaction_status=transaction_status,
            idempotency_key=outcome_idempotency_key(
                transaction_id=transaction_id,
                action_name=action_name,
                logical_step=logical_step,
            ),
            logical_step=logical_step,
            intent_idempotency_key=intent_idempotency_key(
                transaction_id=transaction_id,
                action_name=action_name,
                logical_step=logical_step,
            ),
            **dict(payload or {}),
        )

    def append_event(
        self,
        event: DomainEvent,
        *,
        machine_state: str | None = None,
        transaction_status: str | None = None,
        idempotency_key: str | None = None,
        _connection: sqlite3.Connection | None = None,
    ) -> int:
        return self.append_entry(
            JournalEntry(
                entry_kind=JournalEntryKind.EVENT,
                entry_name=event.event_type,
                correlation_id=event.correlation_id,
                transaction_id=event.transaction_id,
                machine_state=machine_state,
                transaction_status=transaction_status,
                payload=dict(event.payload),
                idempotency_key=idempotency_key,
                created_at=event.occurred_at,
            ),
            _connection=_connection,
        )

    def read_for_transaction(self, transaction_id: str) -> tuple[JournalEntry, ...]:
        rows = self._database.query_all(
            """
            SELECT
                transaction_id,
                correlation_id,
                entry_kind,
                entry_name,
                machine_state,
                transaction_status,
                payload_json,
                idempotency_key,
                created_at
            FROM transaction_journal
            WHERE transaction_id = ?
            ORDER BY journal_id ASC
            """,
            (transaction_id,),
        )
        return tuple(self._row_to_entry(row) for row in rows)

    def list_recent(self, *, limit: int = 50) -> tuple[dict[str, Any], ...]:
        rows = self._database.query_all(
            """
            SELECT
                journal_id,
                transaction_id,
                correlation_id,
                entry_kind,
                entry_name,
                machine_state,
                transaction_status,
                payload_json,
                idempotency_key,
                created_at
            FROM transaction_journal
            WHERE entry_kind = 'event'
            ORDER BY created_at DESC, journal_id DESC
            LIMIT ?
            """,
            (limit,),
        )
        return tuple(self._row_to_recent_event(row) for row in rows)

    def unresolved_transaction_ids(self) -> tuple[str, ...]:
        rows = self._database.query_all(
            """
            SELECT DISTINCT transaction_id
            FROM transaction_journal
            WHERE transaction_id IS NOT NULL
              AND (
                transaction_status IS NULL
                OR transaction_status NOT IN ('completed', 'cancelled')
              )
            ORDER BY transaction_id ASC
            """
        )
        return tuple(row["transaction_id"] for row in rows)

    def unresolved_intents(self) -> tuple[ApplicationJournalRecord, ...]:
        rows = self._database.query_all(
            """
            SELECT
                i.transaction_id,
                i.correlation_id,
                i.entry_kind,
                i.entry_name,
                i.machine_state,
                i.transaction_status,
                i.payload_json,
                i.idempotency_key,
                i.created_at
            FROM transaction_journal i
            LEFT JOIN transaction_journal o
              ON o.entry_kind = 'outcome'
             AND o.idempotency_key = replace(i.idempotency_key, ':intent', ':outcome')
            WHERE i.entry_kind = 'intent'
              AND i.idempotency_key IS NOT NULL
              AND o.journal_id IS NULL
            ORDER BY i.journal_id ASC
            """
        )
        return tuple(self._row_to_application_record(row) for row in rows)

    def unresolved_intent_transaction_ids(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    entry.transaction_id
                    for entry in self.unresolved_intents()
                    if entry.transaction_id is not None
                }
            )
        )

    def orphaned_outcomes(self) -> tuple[ApplicationJournalRecord, ...]:
        rows = self._database.query_all(
            """
            SELECT
                o.transaction_id,
                o.correlation_id,
                o.entry_kind,
                o.entry_name,
                o.machine_state,
                o.transaction_status,
                o.payload_json,
                o.idempotency_key,
                o.created_at
            FROM transaction_journal o
            LEFT JOIN transaction_journal i
              ON i.entry_kind = 'intent'
             AND i.idempotency_key = replace(o.idempotency_key, ':outcome', ':intent')
            WHERE o.entry_kind = 'outcome'
              AND o.idempotency_key IS NOT NULL
              AND i.journal_id IS NULL
            ORDER BY o.journal_id ASC
            """
        )
        return tuple(self._row_to_application_record(row) for row in rows)

    def _row_to_entry(self, row: Any) -> JournalEntry:
        return JournalEntry(
            entry_kind=JournalEntryKind(row["entry_kind"]),
            entry_name=row["entry_name"],
            correlation_id=row["correlation_id"],
            transaction_id=row["transaction_id"],
            machine_state=row["machine_state"],
            transaction_status=row["transaction_status"],
            payload=self._database.loads(row["payload_json"], default={}) or {},
            idempotency_key=row["idempotency_key"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def _row_to_recent_event(self, row: Any) -> dict[str, Any]:
        return {
            "source": "transaction_journal",
            "event_id": row["journal_id"],
            "entry_kind": row["entry_kind"],
            "event_type": row["entry_name"],
            "correlation_id": row["correlation_id"],
            "transaction_id": row["transaction_id"],
            "machine_state": row["machine_state"],
            "transaction_status": row["transaction_status"],
            "payload": self._database.loads(row["payload_json"], default={}) or {},
            "idempotency_key": row["idempotency_key"],
            "occurred_at": row["created_at"],
        }

    def _row_to_application_record(self, row: Any) -> ApplicationJournalRecord:
        return ApplicationJournalRecord(
            entry_kind=row["entry_kind"],
            entry_name=row["entry_name"],
            correlation_id=row["correlation_id"],
            transaction_id=row["transaction_id"],
            machine_state=row["machine_state"],
            transaction_status=row["transaction_status"],
            payload=self._database.loads(row["payload_json"], default={}) or {},
            idempotency_key=row["idempotency_key"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

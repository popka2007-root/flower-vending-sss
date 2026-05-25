"""Database migration tests: apply, rollback, and schema version tracking."""

from __future__ import annotations

import sqlite3
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

from flower_vending.infrastructure.persistence.sqlite.database import SQLiteDatabase
from flower_vending.infrastructure.persistence.sqlite.schema import (
    CURRENT_SCHEMA_VERSION,
    ensure_sqlite_schema,
)


V1_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_metadata (
    schema_key TEXT PRIMARY KEY,
    schema_value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS products (
    product_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    display_name TEXT NOT NULL,
    price_minor_units INTEGER NOT NULL,
    currency_code TEXT NOT NULL,
    category TEXT NOT NULL,
    is_bouquet INTEGER NOT NULL,
    enabled INTEGER NOT NULL,
    temperature_profile TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS slots (
    slot_id TEXT PRIMARY KEY,
    product_id TEXT NOT NULL,
    capacity INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    sensor_state TEXT NOT NULL,
    is_enabled INTEGER NOT NULL,
    last_reconciled_at TEXT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (product_id) REFERENCES products(product_id)
);

CREATE TABLE IF NOT EXISTS machine_status_projection (
    machine_id TEXT PRIMARY KEY,
    machine_state TEXT NOT NULL,
    service_mode INTEGER NOT NULL,
    exact_change_only INTEGER NOT NULL,
    sale_blockers_json TEXT NOT NULL,
    warnings_json TEXT NOT NULL,
    active_transaction_id TEXT NULL,
    allow_cash_sales INTEGER NOT NULL,
    allow_vending INTEGER NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS money_inventory (
    inventory_id TEXT PRIMARY KEY,
    currency_code TEXT NOT NULL,
    accounting_counts_json TEXT NOT NULL,
    reserved_counts_json TEXT NOT NULL,
    physical_state_confidence REAL NOT NULL,
    exact_change_only INTEGER NOT NULL,
    last_reconciled_at TEXT NULL,
    drift_detected INTEGER NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS transactions (
    transaction_id TEXT PRIMARY KEY,
    correlation_id TEXT NOT NULL,
    product_id TEXT NOT NULL,
    slot_id TEXT NOT NULL,
    price_minor_units INTEGER NOT NULL,
    currency_code TEXT NOT NULL,
    status TEXT NOT NULL,
    accepted_minor_units INTEGER NOT NULL,
    change_due_minor_units INTEGER NOT NULL,
    payment_status TEXT NOT NULL,
    payout_status TEXT NOT NULL,
    dispense_status TEXT NOT NULL,
    delivery_status TEXT NOT NULL,
    recovery_status TEXT NOT NULL,
    payment_session_json TEXT NULL,
    change_reserve_json TEXT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS transaction_journal (
    journal_id INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_id TEXT NULL,
    correlation_id TEXT NOT NULL,
    entry_kind TEXT NOT NULL,
    entry_name TEXT NOT NULL,
    machine_state TEXT NULL,
    transaction_status TEXT NULL,
    payload_json TEXT NOT NULL,
    idempotency_key TEXT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (transaction_id) REFERENCES transactions(transaction_id)
);

CREATE TABLE IF NOT EXISTS device_fault_log (
    fault_id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_name TEXT NOT NULL,
    fault_code TEXT NOT NULL,
    message TEXT NOT NULL,
    critical INTEGER NOT NULL,
    correlation_id TEXT NULL,
    transaction_id TEXT NULL,
    details_json TEXT NOT NULL,
    acknowledged INTEGER NOT NULL DEFAULT 0,
    occurred_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS service_events (
    service_event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    operator_id TEXT NULL,
    correlation_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    occurred_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS temperature_events (
    temperature_event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    sensor_name TEXT NOT NULL,
    celsius REAL NOT NULL,
    event_type TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    details_json TEXT NOT NULL,
    occurred_at TEXT NOT NULL
);
"""


@pytest.fixture
def tmp_db_path() -> Iterator[Path]:
    tmpdir = tempfile.mkdtemp(prefix="migration_test_")
    yield Path(tmpdir) / "test_v1.db"


def _create_v1_database(path: Path) -> SQLiteDatabase:
    db = SQLiteDatabase(path, enable_wal=False, synchronous="OFF")
    db.executescript(V1_SCHEMA_SQL)
    db.execute(
        "INSERT INTO schema_metadata (schema_key, schema_value) VALUES (?, ?)",
        ("schema_version", "1"),
    )
    return db


class TestMigrationV1ToV2:
    def test_v1_schema_has_foreign_key_on_transaction_journal(self, tmp_db_path: Path) -> None:
        db = _create_v1_database(tmp_db_path)
        try:
            row = db.query_one(
                "SELECT sql FROM sqlite_master WHERE name = 'transaction_journal' AND type = 'table'"
            )
            assert row is not None
            assert "FOREIGN KEY" in row["sql"]
        finally:
            db.close()

    def test_v2_schema_removes_foreign_key(self, tmp_db_path: Path) -> None:
        db = SQLiteDatabase(tmp_db_path, enable_wal=False, synchronous="OFF")
        try:
            ensure_sqlite_schema(db)
            row = db.query_one(
                "SELECT sql FROM sqlite_master WHERE name = 'transaction_journal' AND type = 'table'"
            )
            assert row is not None
            assert (
                "FOREIGN KEY" not in row["sql"]
            ), "v2 schema should remove FK from transaction_journal"
        finally:
            db.close()

    def test_migrate_v1_to_v2_preserves_data(self, tmp_db_path: Path) -> None:
        db = _create_v1_database(tmp_db_path)
        try:
            db.execute(
                "INSERT INTO transactions (transaction_id, correlation_id, product_id, slot_id, "
                "price_minor_units, currency_code, status, accepted_minor_units, change_due_minor_units, "
                "payment_status, payout_status, dispense_status, delivery_status, recovery_status, "
                "created_at, updated_at) "
                "VALUES ('tx-1', 'corr-1', 'rose_red', 'A1', 500, 'RUB', 'completed', 500, 0, "
                "'confirmed', 'none', 'dispensed', 'completed', 'none', "
                "'2024-01-01T00:00:00', '2024-01-01T00:00:00')"
            )
            db.execute(
                "INSERT INTO transaction_journal (transaction_id, correlation_id, entry_kind, "
                "entry_name, payload_json, created_at) "
                "VALUES ('tx-1', 'corr-1', 'intent', 'test_intent', '{}', '2024-01-01T00:00:00')"
            )
        finally:
            db.close()

        db2 = SQLiteDatabase(tmp_db_path, enable_wal=False, synchronous="OFF")
        try:
            ensure_sqlite_schema(db2)
            row = db2.query_one(
                "SELECT entry_name, entry_kind FROM transaction_journal WHERE transaction_id = ?",
                ("tx-1",),
            )
            assert row is not None, "migrated data should be present"
            assert row["entry_name"] == "test_intent"
            assert row["entry_kind"] == "intent"
        finally:
            db2.close()

    def test_migrate_v1_to_v2_updates_schema_version(self, tmp_db_path: Path) -> None:
        db = _create_v1_database(tmp_db_path)
        db.close()

        db2 = SQLiteDatabase(tmp_db_path, enable_wal=False, synchronous="OFF")
        try:
            ensure_sqlite_schema(db2)
            row = db2.query_one(
                "SELECT schema_value FROM schema_metadata WHERE schema_key = 'schema_version'"
            )
            assert row is not None
            assert int(row["schema_value"]) == CURRENT_SCHEMA_VERSION
        finally:
            db2.close()

    def test_fresh_v2_schema_has_correct_version(self, tmp_db_path: Path) -> None:
        db = SQLiteDatabase(tmp_db_path, enable_wal=False, synchronous="OFF")
        try:
            ensure_sqlite_schema(db)
            row = db.query_one(
                "SELECT schema_value FROM schema_metadata WHERE schema_key = 'schema_version'"
            )
            assert row is not None
            assert int(row["schema_value"]) == CURRENT_SCHEMA_VERSION
        finally:
            db.close()

    def test_idempotent_migration_does_not_corrupt(self, tmp_db_path: Path) -> None:
        db = SQLiteDatabase(tmp_db_path, enable_wal=False, synchronous="OFF")
        try:
            ensure_sqlite_schema(db)
            ensure_sqlite_schema(db)
            ensure_sqlite_schema(db)
            row = db.query_one(
                "SELECT schema_value FROM schema_metadata WHERE schema_key = 'schema_version'"
            )
            assert row is not None
            assert int(row["schema_value"]) == CURRENT_SCHEMA_VERSION
        finally:
            db.close()

    def test_v1_cannot_insert_without_transaction_row(self, tmp_db_path: Path) -> None:
        db = _create_v1_database(tmp_db_path)
        try:
            with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
                db.execute(
                    "INSERT INTO transaction_journal (transaction_id, correlation_id, entry_kind, "
                    "entry_name, payload_json, created_at) "
                    "VALUES ('nonexistent', 'corr-1', 'intent', 'test', '{}', '2024-01-01T00:00:00')"
                )
        finally:
            db.close()

    def test_v2_allows_insert_without_transaction_row(self, tmp_db_path: Path) -> None:
        db = SQLiteDatabase(tmp_db_path, enable_wal=False, synchronous="OFF")
        try:
            ensure_sqlite_schema(db)
            db.execute(
                "INSERT INTO transaction_journal (transaction_id, correlation_id, entry_kind, "
                "entry_name, payload_json, created_at) "
                "VALUES ('nonexistent', 'corr-1', 'intent', 'test', '{}', '2024-01-01T00:00:00')"
            )
            row = db.query_one(
                "SELECT entry_name FROM transaction_journal WHERE transaction_id = 'nonexistent'"
            )
            assert row is not None
        finally:
            db.close()

    def test_all_tables_present_after_migration(self, tmp_db_path: Path) -> None:
        db = _create_v1_database(tmp_db_path)
        db.close()

        expected_tables = {
            "schema_metadata",
            "products",
            "slots",
            "machine_status_projection",
            "money_inventory",
            "transactions",
            "transaction_journal",
            "device_fault_log",
            "service_events",
            "temperature_events",
        }

        db2 = SQLiteDatabase(tmp_db_path, enable_wal=False, synchronous="OFF")
        try:
            ensure_sqlite_schema(db2)
            rows = db2.query_all("SELECT name FROM sqlite_master WHERE type='table'")
            actual_tables = {row["name"] for row in rows}
            assert expected_tables.issubset(
                actual_tables
            ), f"missing tables: {expected_tables - actual_tables}"
        finally:
            db2.close()

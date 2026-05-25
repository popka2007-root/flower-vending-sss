"""SQLite schema for local durable vending-machine persistence."""

from __future__ import annotations

from flower_vending.infrastructure.persistence.sqlite.database import SQLiteDatabase


CURRENT_SCHEMA_VERSION = 2


SCHEMA_SQL = """
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
    created_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_transaction_journal_idempotency
ON transaction_journal(idempotency_key)
WHERE idempotency_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_transaction_journal_transaction
ON transaction_journal(transaction_id, journal_id);

CREATE INDEX IF NOT EXISTS idx_transactions_status
ON transactions(status, recovery_status, updated_at);

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

CREATE INDEX IF NOT EXISTS idx_device_fault_log_unacked
ON device_fault_log(acknowledged, occurred_at);

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

CREATE TABLE IF NOT EXISTS recovery_log (
    recovery_log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_id TEXT NULL,
    correlation_id TEXT NOT NULL,
    action_name TEXT NOT NULL,
    outcome TEXT NOT NULL,
    details_json TEXT NOT NULL,
    occurred_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS device_settings (
    logical_device_name TEXT PRIMARY KEY,
    driver_name TEXT NOT NULL,
    config_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS applied_config (
    config_snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_path TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    yaml_text TEXT NOT NULL,
    applied_at TEXT NOT NULL
);
"""


def ensure_sqlite_schema(database: SQLiteDatabase) -> None:
    database.executescript(SCHEMA_SQL)
    _migrate_v1_to_v2(database)
    database.execute(
        """
        INSERT INTO schema_metadata (schema_key, schema_value)
        VALUES (?, ?)
        ON CONFLICT(schema_key) DO UPDATE SET schema_value = excluded.schema_value
        """,
        ("schema_version", str(CURRENT_SCHEMA_VERSION)),
    )


def _migrate_v1_to_v2(database: SQLiteDatabase) -> None:
    row = database.query_one(
        "SELECT schema_value FROM schema_metadata WHERE schema_key = 'schema_version'"
    )
    if row is not None and int(row["schema_value"]) >= 2:
        return
    with database.transaction() as conn:
        conn.execute("ALTER TABLE transaction_journal RENAME TO transaction_journal_old")
        conn.executescript("""
            CREATE TABLE transaction_journal (
                journal_id INTEGER PRIMARY KEY AUTOINCREMENT,
                transaction_id TEXT NULL,
                correlation_id TEXT NOT NULL,
                entry_kind TEXT NOT NULL,
                entry_name TEXT NOT NULL,
                machine_state TEXT NULL,
                transaction_status TEXT NULL,
                payload_json TEXT NOT NULL,
                idempotency_key TEXT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            INSERT INTO transaction_journal
                (journal_id, transaction_id, correlation_id, entry_kind, entry_name,
                 machine_state, transaction_status, payload_json, idempotency_key, created_at)
            SELECT
                journal_id, transaction_id, correlation_id, entry_kind, entry_name,
                machine_state, transaction_status, payload_json, idempotency_key, created_at
            FROM transaction_journal_old
            ORDER BY journal_id ASC
        """)
        conn.execute("DROP TABLE transaction_journal_old")
    database.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_transaction_journal_idempotency
        ON transaction_journal(idempotency_key)
        WHERE idempotency_key IS NOT NULL
    """)
    database.execute("""
        CREATE INDEX IF NOT EXISTS idx_transaction_journal_transaction
        ON transaction_journal(transaction_id, journal_id)
    """)

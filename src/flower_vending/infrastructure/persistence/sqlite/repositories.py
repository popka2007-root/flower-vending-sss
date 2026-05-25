"""SQLite repositories for catalog, runtime, journal-adjacent, and audit state."""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from typing import Any

from flower_vending.devices.contracts import DeviceFault
from flower_vending.domain.entities import MachineStatus, MoneyInventory, Product, Slot, Transaction
from flower_vending.infrastructure.persistence.sqlite.database import SQLiteDatabase
from flower_vending.infrastructure.persistence.sqlite.mappers import (
    machine_status_from_row,
    machine_status_to_record,
    money_inventory_from_row,
    money_inventory_to_record,
    product_from_row,
    product_to_record,
    slot_from_row,
    slot_to_record,
    transaction_from_row,
    transaction_to_record,
)


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class ProductRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def save(self, product: Product) -> None:
        record = product_to_record(product, updated_at=_utc_now_iso())
        self._database.execute(
            """
            INSERT INTO products (
                product_id,
                name,
                display_name,
                price_minor_units,
                currency_code,
                category,
                is_bouquet,
                enabled,
                temperature_profile,
                metadata_json,
                updated_at
            ) VALUES (
                :product_id,
                :name,
                :display_name,
                :price_minor_units,
                :currency_code,
                :category,
                :is_bouquet,
                :enabled,
                :temperature_profile,
                :metadata_json,
                :updated_at
            )
            ON CONFLICT(product_id) DO UPDATE SET
                name = excluded.name,
                display_name = excluded.display_name,
                price_minor_units = excluded.price_minor_units,
                currency_code = excluded.currency_code,
                category = excluded.category,
                is_bouquet = excluded.is_bouquet,
                enabled = excluded.enabled,
                temperature_profile = excluded.temperature_profile,
                metadata_json = excluded.metadata_json,
                updated_at = excluded.updated_at
            """,
            {
                **record,
                "metadata_json": self._database.dumps(record["metadata_json"]),
            },
        )

    def get(self, product_id: str) -> Product | None:
        row = self._database.query_one("SELECT * FROM products WHERE product_id = ?", (product_id,))
        if row is None:
            return None
        return product_from_row(
            row,
            metadata_json=self._database.loads(row["metadata_json"], default={}) or {},
        )

    def list_all(self) -> tuple[Product, ...]:
        rows = self._database.query_all("SELECT * FROM products ORDER BY product_id ASC")
        return tuple(
            product_from_row(
                row,
                metadata_json=self._database.loads(row["metadata_json"], default={}) or {},
            )
            for row in rows
        )

    def delete_all(self) -> None:
        self._database.execute("DELETE FROM products")


class SlotRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def save(self, slot: Slot) -> None:
        record = slot_to_record(slot, updated_at=_utc_now_iso())
        self._database.execute(
            """
            INSERT INTO slots (
                slot_id,
                product_id,
                capacity,
                quantity,
                sensor_state,
                is_enabled,
                last_reconciled_at,
                updated_at
            ) VALUES (
                :slot_id,
                :product_id,
                :capacity,
                :quantity,
                :sensor_state,
                :is_enabled,
                :last_reconciled_at,
                :updated_at
            )
            ON CONFLICT(slot_id) DO UPDATE SET
                product_id = excluded.product_id,
                capacity = excluded.capacity,
                quantity = excluded.quantity,
                sensor_state = excluded.sensor_state,
                is_enabled = excluded.is_enabled,
                last_reconciled_at = excluded.last_reconciled_at,
                updated_at = excluded.updated_at
            """,
            record,
        )

    def get(self, slot_id: str) -> Slot | None:
        row = self._database.query_one("SELECT * FROM slots WHERE slot_id = ?", (slot_id,))
        if row is None:
            return None
        return slot_from_row(row)

    def list_all(self) -> tuple[Slot, ...]:
        rows = self._database.query_all("SELECT * FROM slots ORDER BY slot_id ASC")
        return tuple(slot_from_row(row) for row in rows)

    def delete_all(self) -> None:
        self._database.execute("DELETE FROM slots")


class MachineStatusRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def save(
        self,
        status: MachineStatus,
        *,
        machine_id: str = "primary",
        _connection: sqlite3.Connection | None = None,
    ) -> None:
        record = machine_status_to_record(status, machine_id=machine_id, updated_at=_utc_now_iso())
        self._database.execute(
            """
            INSERT INTO machine_status_projection (
                machine_id,
                machine_state,
                service_mode,
                exact_change_only,
                sale_blockers_json,
                warnings_json,
                active_transaction_id,
                allow_cash_sales,
                allow_vending,
                updated_at
            ) VALUES (
                :machine_id,
                :machine_state,
                :service_mode,
                :exact_change_only,
                :sale_blockers_json,
                :warnings_json,
                :active_transaction_id,
                :allow_cash_sales,
                :allow_vending,
                :updated_at
            )
            ON CONFLICT(machine_id) DO UPDATE SET
                machine_state = excluded.machine_state,
                service_mode = excluded.service_mode,
                exact_change_only = excluded.exact_change_only,
                sale_blockers_json = excluded.sale_blockers_json,
                warnings_json = excluded.warnings_json,
                active_transaction_id = excluded.active_transaction_id,
                allow_cash_sales = excluded.allow_cash_sales,
                allow_vending = excluded.allow_vending,
                updated_at = excluded.updated_at
            """,
            {
                **record,
                "sale_blockers_json": self._database.dumps(record["sale_blockers_json"]),
                "warnings_json": self._database.dumps(record["warnings_json"]),
            },
            connection=_connection,
        )

    def get(self, *, machine_id: str = "primary") -> MachineStatus | None:
        row = self._database.query_one(
            "SELECT * FROM machine_status_projection WHERE machine_id = ?",
            (machine_id,),
        )
        if row is None:
            return None
        return machine_status_from_row(
            row,
            sale_blockers=self._database.loads(row["sale_blockers_json"], default=[]) or [],
            warnings=self._database.loads(row["warnings_json"], default=[]) or [],
        )

    def snapshot(self, *, machine_id: str = "primary") -> dict[str, Any] | None:
        row = self._database.query_one(
            "SELECT * FROM machine_status_projection WHERE machine_id = ?",
            (machine_id,),
        )
        if row is None:
            return None
        return {
            "machine_id": row["machine_id"],
            "machine_state": row["machine_state"],
            "service_mode": bool(row["service_mode"]),
            "exact_change_only": bool(row["exact_change_only"]),
            "sale_blockers": self._database.loads(row["sale_blockers_json"], default=[]) or [],
            "warnings": self._database.loads(row["warnings_json"], default=[]) or [],
            "active_transaction_id": row["active_transaction_id"],
            "allow_cash_sales": bool(row["allow_cash_sales"]),
            "allow_vending": bool(row["allow_vending"]),
            "updated_at": row["updated_at"],
        }


class MoneyInventoryRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def save(
        self,
        inventory: MoneyInventory,
        *,
        inventory_id: str = "main",
        _connection: sqlite3.Connection | None = None,
    ) -> None:
        record = money_inventory_to_record(inventory, inventory_id=inventory_id, updated_at=_utc_now_iso())
        self._database.execute(
            """
            INSERT INTO money_inventory (
                inventory_id,
                currency_code,
                accounting_counts_json,
                reserved_counts_json,
                physical_state_confidence,
                exact_change_only,
                last_reconciled_at,
                drift_detected,
                updated_at
            ) VALUES (
                :inventory_id,
                :currency_code,
                :accounting_counts_json,
                :reserved_counts_json,
                :physical_state_confidence,
                :exact_change_only,
                :last_reconciled_at,
                :drift_detected,
                :updated_at
            )
            ON CONFLICT(inventory_id) DO UPDATE SET
                currency_code = excluded.currency_code,
                accounting_counts_json = excluded.accounting_counts_json,
                reserved_counts_json = excluded.reserved_counts_json,
                physical_state_confidence = excluded.physical_state_confidence,
                exact_change_only = excluded.exact_change_only,
                last_reconciled_at = excluded.last_reconciled_at,
                drift_detected = excluded.drift_detected,
                updated_at = excluded.updated_at
            """,
            {
                **record,
                "accounting_counts_json": self._database.dumps(record["accounting_counts_json"]),
                "reserved_counts_json": self._database.dumps(record["reserved_counts_json"]),
            },
            connection=_connection,
        )

    def get(self, *, inventory_id: str = "main") -> MoneyInventory | None:
        row = self._database.query_one(
            "SELECT * FROM money_inventory WHERE inventory_id = ?",
            (inventory_id,),
        )
        if row is None:
            return None
        return money_inventory_from_row(
            row,
            accounting_counts=self._database.loads(row["accounting_counts_json"], default={}) or {},
            reserved_counts=self._database.loads(row["reserved_counts_json"], default={}) or {},
        )

    def snapshot(self, *, inventory_id: str = "main") -> dict[str, Any] | None:
        row = self._database.query_one(
            "SELECT * FROM money_inventory WHERE inventory_id = ?",
            (inventory_id,),
        )
        if row is None:
            return None
        accounting_counts = {
            str(denomination): int(count)
            for denomination, count in (
                self._database.loads(row["accounting_counts_json"], default={}) or {}
            ).items()
        }
        reserved_counts = {
            str(denomination): int(count)
            for denomination, count in (
                self._database.loads(row["reserved_counts_json"], default={}) or {}
            ).items()
        }
        available_counts = {
            denomination: max(0, count - reserved_counts.get(denomination, 0))
            for denomination, count in accounting_counts.items()
        }
        return {
            "inventory_id": row["inventory_id"],
            "currency_code": row["currency_code"],
            "accounting_counts": accounting_counts,
            "reserved_counts": reserved_counts,
            "available_counts": available_counts,
            "physical_state_confidence": row["physical_state_confidence"],
            "exact_change_only": bool(row["exact_change_only"]),
            "last_reconciled_at": row["last_reconciled_at"],
            "drift_detected": bool(row["drift_detected"]),
            "updated_at": row["updated_at"],
        }


class TransactionRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def save(
        self,
        transaction: Transaction,
        *,
        _connection: sqlite3.Connection | None = None,
    ) -> None:
        record = transaction_to_record(transaction)
        self._database.execute(
            """
            INSERT INTO transactions (
                transaction_id,
                correlation_id,
                product_id,
                slot_id,
                price_minor_units,
                currency_code,
                status,
                accepted_minor_units,
                change_due_minor_units,
                payment_status,
                payout_status,
                dispense_status,
                delivery_status,
                recovery_status,
                payment_session_json,
                change_reserve_json,
                created_at,
                updated_at
            ) VALUES (
                :transaction_id,
                :correlation_id,
                :product_id,
                :slot_id,
                :price_minor_units,
                :currency_code,
                :status,
                :accepted_minor_units,
                :change_due_minor_units,
                :payment_status,
                :payout_status,
                :dispense_status,
                :delivery_status,
                :recovery_status,
                :payment_session_json,
                :change_reserve_json,
                :created_at,
                :updated_at
            )
            ON CONFLICT(transaction_id) DO UPDATE SET
                correlation_id = excluded.correlation_id,
                product_id = excluded.product_id,
                slot_id = excluded.slot_id,
                price_minor_units = excluded.price_minor_units,
                currency_code = excluded.currency_code,
                status = excluded.status,
                accepted_minor_units = excluded.accepted_minor_units,
                change_due_minor_units = excluded.change_due_minor_units,
                payment_status = excluded.payment_status,
                payout_status = excluded.payout_status,
                dispense_status = excluded.dispense_status,
                delivery_status = excluded.delivery_status,
                recovery_status = excluded.recovery_status,
                payment_session_json = excluded.payment_session_json,
                change_reserve_json = excluded.change_reserve_json,
                created_at = excluded.created_at,
                updated_at = excluded.updated_at
            """,
            {
                **record,
                "payment_session_json": (
                    None
                    if record["payment_session_json"] is None
                    else self._database.dumps(record["payment_session_json"])
                ),
                "change_reserve_json": (
                    None
                    if record["change_reserve_json"] is None
                    else self._database.dumps(record["change_reserve_json"])
                ),
            },
            connection=_connection,
        )

    def get(self, transaction_id: str) -> Transaction | None:
        row = self._database.query_one(
            "SELECT * FROM transactions WHERE transaction_id = ?",
            (transaction_id,),
        )
        if row is None:
            return None
        return transaction_from_row(
            row,
            payment_session_json=self._database.loads(row["payment_session_json"], default=None),
            change_reserve_json=self._database.loads(row["change_reserve_json"], default=None),
        )

    def list_unresolved(self) -> tuple[Transaction, ...]:
        rows = self._database.query_all(
            """
            SELECT * FROM transactions
            WHERE status NOT IN ('completed', 'cancelled')
               OR recovery_status <> 'none'
            ORDER BY updated_at ASC
            """
        )
        return tuple(
            transaction_from_row(
                row,
                payment_session_json=self._database.loads(row["payment_session_json"], default=None),
                change_reserve_json=self._database.loads(row["change_reserve_json"], default=None),
            )
            for row in rows
        )

    def list_unresolved_summaries(self) -> tuple[dict[str, Any], ...]:
        rows = self._database.query_all(
            """
            SELECT
                transaction_id,
                correlation_id,
                product_id,
                slot_id,
                price_minor_units,
                currency_code,
                status,
                accepted_minor_units,
                change_due_minor_units,
                payment_status,
                payout_status,
                dispense_status,
                delivery_status,
                recovery_status,
                created_at,
                updated_at
            FROM transactions
            WHERE status NOT IN ('completed', 'cancelled')
               OR recovery_status <> 'none'
            ORDER BY updated_at ASC
            """
        )
        return tuple(dict(row) for row in rows)


class DeviceFaultLogRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def record(
        self,
        *,
        device_name: str,
        fault: DeviceFault,
        correlation_id: str | None = None,
        transaction_id: str | None = None,
        occurred_at: str | None = None,
    ) -> int:
        return self._database.insert(
            """
            INSERT INTO device_fault_log (
                device_name,
                fault_code,
                message,
                critical,
                correlation_id,
                transaction_id,
                details_json,
                acknowledged,
                occurred_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)
            """,
            (
                device_name,
                fault.code,
                fault.message,
                int(fault.critical),
                correlation_id,
                transaction_id,
                self._database.dumps(dict(fault.details)),
                occurred_at or _utc_now_iso(),
            ),
        )

    def list_unacknowledged(self) -> tuple[dict[str, Any], ...]:
        rows = self._database.query_all(
            """
            SELECT * FROM device_fault_log
            WHERE acknowledged = 0
            ORDER BY occurred_at ASC
            """
        )
        return tuple(self._row_to_dict(row) for row in rows)

    def acknowledge(self, fault_id: int) -> None:
        self._database.execute(
            "UPDATE device_fault_log SET acknowledged = 1 WHERE fault_id = ?",
            (fault_id,),
        )

    def _row_to_dict(self, row: Any) -> dict[str, Any]:
        payload = dict(row)
        payload["details"] = self._database.loads(payload.pop("details_json"), default={}) or {}
        payload["critical"] = bool(payload["critical"])
        payload["acknowledged"] = bool(payload["acknowledged"])
        return payload


class OperationalEventRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def record_service_event(
        self,
        *,
        event_type: str,
        correlation_id: str,
        operator_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> int:
        return self._database.insert(
            """
            INSERT INTO service_events (
                event_type,
                operator_id,
                correlation_id,
                payload_json,
                occurred_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                event_type,
                operator_id,
                correlation_id,
                self._database.dumps(payload),
                _utc_now_iso(),
            ),
        )

    def record_temperature_event(
        self,
        *,
        sensor_name: str,
        celsius: float,
        event_type: str,
        correlation_id: str,
        details: dict[str, Any] | None = None,
    ) -> int:
        return self._database.insert(
            """
            INSERT INTO temperature_events (
                sensor_name,
                celsius,
                event_type,
                correlation_id,
                details_json,
                occurred_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                sensor_name,
                celsius,
                event_type,
                correlation_id,
                self._database.dumps(details),
                _utc_now_iso(),
            ),
        )

    def list_recent(self, *, limit: int = 50) -> tuple[dict[str, Any], ...]:
        service_rows = self._database.query_all(
            """
            SELECT
                service_event_id AS event_id,
                'service_events' AS source,
                event_type,
                operator_id,
                NULL AS sensor_name,
                NULL AS celsius,
                correlation_id,
                NULL AS transaction_id,
                payload_json AS payload_json,
                occurred_at
            FROM service_events
            ORDER BY occurred_at DESC, service_event_id DESC
            LIMIT ?
            """,
            (limit,),
        )
        temperature_rows = self._database.query_all(
            """
            SELECT
                temperature_event_id AS event_id,
                'temperature_events' AS source,
                event_type,
                NULL AS operator_id,
                sensor_name,
                celsius,
                correlation_id,
                NULL AS transaction_id,
                details_json AS payload_json,
                occurred_at
            FROM temperature_events
            ORDER BY occurred_at DESC, temperature_event_id DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = [*service_rows, *temperature_rows]
        rows.sort(key=lambda row: (row["occurred_at"], row["source"], row["event_id"]), reverse=True)
        return tuple(self._event_row_to_dict(row) for row in rows[:limit])

    def _event_row_to_dict(self, row: Any) -> dict[str, Any]:
        return {
            "source": row["source"],
            "event_id": row["event_id"],
            "event_type": row["event_type"],
            "correlation_id": row["correlation_id"],
            "transaction_id": row["transaction_id"],
            "operator_id": row["operator_id"],
            "sensor_name": row["sensor_name"],
            "celsius": row["celsius"],
            "payload": self._database.loads(row["payload_json"], default={}) or {},
            "occurred_at": row["occurred_at"],
        }

class DeviceSettingsRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def save(
        self,
        *,
        logical_device_name: str,
        driver_name: str,
        config: dict[str, Any],
    ) -> None:
        self._database.execute(
            """
            INSERT INTO device_settings (
                logical_device_name,
                driver_name,
                config_json,
                updated_at
            ) VALUES (?, ?, ?, ?)
            ON CONFLICT(logical_device_name) DO UPDATE SET
                driver_name = excluded.driver_name,
                config_json = excluded.config_json,
                updated_at = excluded.updated_at
            """,
            (
                logical_device_name,
                driver_name,
                self._database.dumps(config),
                _utc_now_iso(),
            ),
        )

    def get(self, logical_device_name: str) -> dict[str, Any] | None:
        row = self._database.query_one(
            "SELECT * FROM device_settings WHERE logical_device_name = ?",
            (logical_device_name,),
        )
        if row is None:
            return None
        return {
            "logical_device_name": row["logical_device_name"],
            "driver_name": row["driver_name"],
            "config": self._database.loads(row["config_json"], default={}) or {},
            "updated_at": row["updated_at"],
        }


class AppliedConfigRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def save_snapshot(self, *, source_path: str, yaml_text: str) -> int:
        config_hash = hashlib.sha256(yaml_text.encode("utf-8")).hexdigest()
        return self._database.insert(
            """
            INSERT INTO applied_config (
                source_path,
                config_hash,
                yaml_text,
                applied_at
            ) VALUES (?, ?, ?, ?)
            """,
            (source_path, config_hash, yaml_text, _utc_now_iso()),
        )

    def latest(self) -> dict[str, Any] | None:
        row = self._database.query_one(
            """
            SELECT * FROM applied_config
            ORDER BY config_snapshot_id DESC
            LIMIT 1
            """
        )
        if row is None:
            return None
        return dict(row)

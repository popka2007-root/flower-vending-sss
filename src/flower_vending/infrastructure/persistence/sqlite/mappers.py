"""Serialization helpers for persistence-backed domain entities."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from flower_vending.domain.entities import (
    ChangeReserve,
    ChangeReserveStatus,
    DeliveryStatus,
    MachineStatus,
    MoneyInventory,
    PaymentSession,
    PaymentSessionStatus,
    PaymentStatus,
    PayoutStatus,
    Product,
    RecoveryStatus,
    Slot,
    Transaction,
    TransactionStatus,
)
from flower_vending.domain.entities.transaction import DispenseStatus
from flower_vending.domain.value_objects import (
    Amount,
    CorrelationId,
    Currency,
    ProductId,
    SlotId,
    TransactionId,
)


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _iso(ts: datetime | None) -> str | None:
    return ts.isoformat() if ts is not None else None


def _parse_iso(ts: str | None) -> datetime | None:
    return datetime.fromisoformat(ts) if ts else None


def _int_key_map(raw: dict[str, Any] | dict[int, Any]) -> dict[int, int]:
    return {int(key): int(value) for key, value in raw.items()}


def product_to_record(product: Product, *, updated_at: str) -> dict[str, Any]:
    return {
        "product_id": product.product_id.value,
        "name": product.name,
        "display_name": product.display_name,
        "price_minor_units": product.price.minor_units,
        "currency_code": product.price.currency.code,
        "category": product.category,
        "is_bouquet": int(product.is_bouquet),
        "enabled": int(product.enabled),
        "temperature_profile": product.temperature_profile,
        "metadata_json": product.metadata,
        "updated_at": updated_at,
    }


def product_from_row(row: Any, *, metadata_json: dict[str, Any]) -> Product:
    return Product(
        product_id=ProductId(row["product_id"]),
        name=row["name"],
        display_name=row["display_name"],
        price=Amount(row["price_minor_units"], Currency(row["currency_code"])),
        category=row["category"],
        is_bouquet=bool(row["is_bouquet"]),
        enabled=bool(row["enabled"]),
        temperature_profile=row["temperature_profile"],
        metadata=metadata_json,
    )


def slot_to_record(slot: Slot, *, updated_at: str) -> dict[str, Any]:
    return {
        "slot_id": slot.slot_id.value,
        "product_id": slot.product_id.value,
        "capacity": slot.capacity,
        "quantity": slot.quantity,
        "sensor_state": slot.sensor_state,
        "is_enabled": int(slot.is_enabled),
        "last_reconciled_at": slot.last_reconciled_at,
        "updated_at": updated_at,
    }


def slot_from_row(row: Any) -> Slot:
    return Slot(
        slot_id=SlotId(row["slot_id"]),
        product_id=ProductId(row["product_id"]),
        capacity=row["capacity"],
        quantity=row["quantity"],
        sensor_state=row["sensor_state"],
        is_enabled=bool(row["is_enabled"]),
        last_reconciled_at=row["last_reconciled_at"],
    )


def machine_status_to_record(
    status: MachineStatus, *, machine_id: str, updated_at: str
) -> dict[str, Any]:
    return {
        "machine_id": machine_id,
        "machine_state": status.machine_state,
        "service_mode": int(status.service_mode),
        "exact_change_only": int(status.exact_change_only),
        "sale_blockers_json": sorted(status.sale_blockers),
        "warnings_json": sorted(status.warnings),
        "active_transaction_id": status.active_transaction_id,
        "allow_cash_sales": int(status.allow_cash_sales),
        "allow_vending": int(status.allow_vending),
        "updated_at": updated_at,
    }


def machine_status_from_row(
    row: Any, *, sale_blockers: list[str], warnings: list[str]
) -> MachineStatus:
    return MachineStatus(
        machine_state=row["machine_state"],
        service_mode=bool(row["service_mode"]),
        exact_change_only=bool(row["exact_change_only"]),
        sale_blockers=set(sale_blockers),
        warnings=set(warnings),
        active_transaction_id=row["active_transaction_id"],
        allow_cash_sales=bool(row["allow_cash_sales"]),
        allow_vending=bool(row["allow_vending"]),
    )


def money_inventory_to_record(
    inventory: MoneyInventory,
    *,
    inventory_id: str,
    updated_at: str,
) -> dict[str, Any]:
    return {
        "inventory_id": inventory_id,
        "currency_code": inventory.currency.code,
        "accounting_counts_json": inventory.accounting_counts_by_denomination,
        "reserved_counts_json": inventory.reserved_counts_by_denomination,
        "physical_state_confidence": inventory.physical_state_confidence,
        "exact_change_only": int(inventory.exact_change_only),
        "last_reconciled_at": inventory.last_reconciled_at,
        "drift_detected": int(inventory.drift_detected),
        "updated_at": updated_at,
    }


def money_inventory_from_row(
    row: Any,
    *,
    accounting_counts: dict[str, Any] | dict[int, Any],
    reserved_counts: dict[str, Any] | dict[int, Any],
) -> MoneyInventory:
    return MoneyInventory(
        currency=Currency(row["currency_code"]),
        accounting_counts_by_denomination=_int_key_map(accounting_counts),
        reserved_counts_by_denomination=_int_key_map(reserved_counts),
        physical_state_confidence=row["physical_state_confidence"],
        exact_change_only=bool(row["exact_change_only"]),
        last_reconciled_at=row["last_reconciled_at"],
        drift_detected=bool(row["drift_detected"]),
    )


def payment_session_to_json(session: PaymentSession | None) -> dict[str, Any] | None:
    if session is None:
        return None
    return {
        "transaction_id": session.transaction_id,
        "status": session.status.value,
        "accepted_minor_units": session.accepted_amount.minor_units,
        "currency_code": session.accepted_amount.currency.code,
        "accepted_bills": list(session.accepted_bills),
        "validator_enabled": session.validator_enabled,
        "started_at": _iso(session.started_at),
        "expires_at": _iso(session.expires_at),
        "cancel_requested": session.cancel_requested,
    }


def payment_session_from_json(payload: dict[str, Any] | None) -> PaymentSession | None:
    if payload is None:
        return None
    return PaymentSession(
        transaction_id=payload["transaction_id"],
        status=PaymentSessionStatus(payload["status"]),
        accepted_amount=Amount(
            int(payload["accepted_minor_units"]),
            Currency(payload.get("currency_code", "RUB")),
        ),
        accepted_bills=[int(value) for value in payload.get("accepted_bills", [])],
        validator_enabled=bool(payload["validator_enabled"]),
        started_at=_parse_iso(payload["started_at"]) or _now(),
        expires_at=_parse_iso(payload["expires_at"]) or _now(),
        cancel_requested=bool(payload["cancel_requested"]),
    )


def change_reserve_to_json(reserve: ChangeReserve | None) -> dict[str, Any] | None:
    if reserve is None:
        return None
    return {
        "transaction_id": reserve.transaction_id,
        "reserved_counts_by_denomination": reserve.reserved_counts_by_denomination,
        "currency_code": reserve.currency.code,
        "status": reserve.status.value,
        "created_at": _iso(reserve.created_at),
        "released_at": _iso(reserve.released_at),
    }


def change_reserve_from_json(payload: dict[str, Any] | None) -> ChangeReserve | None:
    if payload is None:
        return None
    return ChangeReserve(
        transaction_id=payload["transaction_id"],
        reserved_counts_by_denomination=_int_key_map(payload["reserved_counts_by_denomination"]),
        currency=Currency(payload.get("currency_code", "RUB")),
        status=ChangeReserveStatus(payload["status"]),
        created_at=_parse_iso(payload["created_at"]) or _now(),
        released_at=_parse_iso(payload.get("released_at")),
    )


def transaction_to_record(transaction: Transaction) -> dict[str, Any]:
    return {
        "transaction_id": transaction.transaction_id.value,
        "correlation_id": transaction.correlation_id.value,
        "product_id": transaction.product_id.value,
        "slot_id": transaction.slot_id.value,
        "price_minor_units": transaction.price.minor_units,
        "currency_code": transaction.price.currency.code,
        "status": transaction.status.value,
        "accepted_minor_units": transaction.accepted_amount.minor_units,
        "change_due_minor_units": transaction.change_due.minor_units,
        "payment_status": transaction.payment_status.value,
        "payout_status": transaction.payout_status.value,
        "dispense_status": transaction.dispense_status.value,
        "delivery_status": transaction.delivery_status.value,
        "recovery_status": transaction.recovery_status.value,
        "payment_session_json": payment_session_to_json(transaction.payment_session),
        "change_reserve_json": change_reserve_to_json(transaction.change_reserve),
        "created_at": _iso(transaction.created_at),
        "updated_at": _iso(transaction.updated_at),
    }


def transaction_from_row(
    row: Any,
    *,
    payment_session_json: dict[str, Any] | None,
    change_reserve_json: dict[str, Any] | None,
) -> Transaction:
    return Transaction(
        transaction_id=TransactionId(row["transaction_id"]),
        correlation_id=CorrelationId(row["correlation_id"]),
        product_id=ProductId(row["product_id"]),
        slot_id=SlotId(row["slot_id"]),
        price=Amount(row["price_minor_units"], Currency(row["currency_code"])),
        status=TransactionStatus(row["status"]),
        accepted_amount=Amount(row["accepted_minor_units"], Currency(row["currency_code"])),
        change_due=Amount(row["change_due_minor_units"], Currency(row["currency_code"])),
        payment_status=PaymentStatus(row["payment_status"]),
        payout_status=PayoutStatus(row["payout_status"]),
        dispense_status=DispenseStatus(row["dispense_status"]),
        delivery_status=DeliveryStatus(row["delivery_status"]),
        recovery_status=RecoveryStatus(row["recovery_status"]),
        payment_session=payment_session_from_json(payment_session_json),
        change_reserve=change_reserve_from_json(change_reserve_json),
        created_at=_parse_iso(row["created_at"]) or _now(),
        updated_at=_parse_iso(row["updated_at"]) or _now(),
        _cancelled=TransactionStatus(row["status"]) is TransactionStatus.CANCELLED,
    )

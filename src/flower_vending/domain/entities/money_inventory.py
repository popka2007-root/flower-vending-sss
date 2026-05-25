"""Money inventory entity."""

from __future__ import annotations

import asyncio

from flower_vending.domain.entities.change_reserve import ChangeReserve
from flower_vending.domain.exceptions import ChangeUnavailableError, DomainValidationError
from flower_vending.domain.value_objects import Currency


class MoneyInventory:
    __slots__ = (
        "_accounting_counts",
        "_reserved_counts",
        "currency",
        "physical_state_confidence",
        "exact_change_only",
        "last_reconciled_at",
        "drift_detected",
        "_lock",
    )

    def __init__(
        self,
        currency: Currency | None = None,
        accounting_counts_by_denomination: dict[int, int] | None = None,
        reserved_counts_by_denomination: dict[int, int] | None = None,
        physical_state_confidence: float = 1.0,
        exact_change_only: bool = False,
        last_reconciled_at: str | None = None,
        drift_detected: bool = False,
    ) -> None:
        self.currency = currency if currency is not None else Currency()
        self._accounting_counts = (
            dict(accounting_counts_by_denomination) if accounting_counts_by_denomination else {}
        )
        self._reserved_counts = (
            dict(reserved_counts_by_denomination) if reserved_counts_by_denomination else {}
        )
        self.physical_state_confidence = physical_state_confidence
        self.exact_change_only = exact_change_only
        self.last_reconciled_at = last_reconciled_at
        self.drift_detected = drift_detected
        self._lock = asyncio.Lock()

    @property
    def accounting_counts_by_denomination(self) -> dict[int, int]:
        return dict(self._accounting_counts)

    @property
    def reserved_counts_by_denomination(self) -> dict[int, int]:
        return dict(self._reserved_counts)

    async def available_counts(self) -> dict[int, int]:
        async with self._lock:
            return self._available_unlocked()

    def _available_unlocked(self) -> dict[int, int]:
        available: dict[int, int] = {}
        for denomination, count in self._accounting_counts.items():
            reserved = self._reserved_counts.get(denomination, 0)
            available[denomination] = max(0, count - reserved)
        return available

    async def can_reserve(self, plan: dict[int, int]) -> bool:
        async with self._lock:
            return self._can_reserve_unlocked(plan)

    def _can_reserve_unlocked(self, plan: dict[int, int]) -> bool:
        available = self._available_unlocked()
        return all(available.get(denomination, 0) >= count for denomination, count in plan.items())

    async def reserve(self, transaction_id: str, plan: dict[int, int]) -> ChangeReserve:
        for count in plan.values():
            if count < 0:
                raise DomainValidationError("reserve plan cannot contain negative values")

        async with self._lock:
            if not self._can_reserve_unlocked(plan):
                raise ChangeUnavailableError("insufficient change inventory for requested reserve")
            for denomination, count in plan.items():
                self._reserved_counts[denomination] = (
                    self._reserved_counts.get(denomination, 0) + count
                )
            return ChangeReserve(
                transaction_id=transaction_id,
                reserved_counts_by_denomination=dict(plan),
                currency=self.currency,
            )

    async def release(self, reserve: ChangeReserve) -> None:
        async with self._lock:
            for denomination, count in reserve.reserved_counts_by_denomination.items():
                current = self._reserved_counts.get(denomination, 0)
                self._reserved_counts[denomination] = max(0, current - count)
            reserve.release()

    def clear_drift(self) -> None:
        self.drift_detected = False

    async def consume(self, reserve: ChangeReserve) -> None:
        for count in reserve.reserved_counts_by_denomination.values():
            if count < 0:
                raise DomainValidationError("consume plan cannot contain negative values")

        async with self._lock:
            for denomination, count in reserve.reserved_counts_by_denomination.items():
                self._accounting_counts[denomination] = (
                    self._accounting_counts.get(denomination, 0) - count
                )
                self._reserved_counts[denomination] = max(
                    0, self._reserved_counts.get(denomination, 0) - count
                )
            reserve.consume()

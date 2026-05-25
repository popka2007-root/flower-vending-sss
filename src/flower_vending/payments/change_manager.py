"""Application-facing change manager."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from flower_vending.devices.contracts import (
    ChangeDispenseRequest,
    ChangeDispenseResult,
    PayoutStatus,
)
from flower_vending.devices.interfaces import ChangeDispenser
from flower_vending.domain.entities import ChangeReserve, MoneyInventory, Transaction
from flower_vending.domain.exceptions import ChangeUnavailableError, PartialPayoutError


@dataclass(frozen=True, slots=True)
class SaleChangeAssessment:
    sale_supported: bool
    exact_change_only: bool
    reserved_change_minor_units: int
    plan: dict[int, int]


class ChangeManager:
    """Owns payout planning, reservation, and payout settlement."""

    def __init__(
        self,
        inventory: MoneyInventory,
        change_dispenser: ChangeDispenser,
        accepted_bill_denominations: Iterable[int] = (),
    ) -> None:
        self._inventory = inventory
        self._change_dispenser = change_dispenser
        self._accepted_bill_denominations = tuple(sorted(set(accepted_bill_denominations)))

    @property
    def inventory(self) -> MoneyInventory:
        return self._inventory

    async def assess_sale(self, transaction: Transaction) -> SaleChangeAssessment:
        if self._inventory.drift_detected:
            return SaleChangeAssessment(False, True, 0, {})
        worst_case_change = await self._calculate_worst_case_change(transaction.price.minor_units)
        if worst_case_change is None:
            return SaleChangeAssessment(False, True, 0, {})
        if worst_case_change == 0:
            return SaleChangeAssessment(True, False, 0, {})
        plan = await self.plan_change(worst_case_change)
        if plan is None:
            return SaleChangeAssessment(False, True, 0, {})
        return SaleChangeAssessment(True, False, worst_case_change, plan)

    async def reserve_for_transaction(
        self, transaction_id: str, plan: dict[int, int]
    ) -> ChangeReserve:
        return await self._inventory.reserve(transaction_id=transaction_id, plan=plan)

    async def finalize_reserve(self, transaction: Transaction) -> ChangeReserve | None:
        reserve = transaction.change_reserve
        change_due = transaction.change_due.minor_units
        if change_due == 0:
            if reserve is not None:
                await self._inventory.release(reserve)
                transaction.change_reserve = None
            return None

        if reserve is not None:
            await self._inventory.release(reserve)
            transaction.change_reserve = None

        plan = await self.plan_change(change_due)
        if plan is None:
            raise ChangeUnavailableError("unable to finalize exact payout plan")
        final_reserve = await self._inventory.reserve(transaction.transaction_id.value, plan)
        transaction.attach_change_reserve(final_reserve)
        return final_reserve

    def prepare_payout_request(self, transaction: Transaction) -> ChangeDispenseRequest | None:
        if transaction.change_due.is_zero():
            return None
        reserve = transaction.change_reserve
        if reserve is None:
            raise ChangeUnavailableError("transaction has no finalized change reserve")
        return ChangeDispenseRequest(
            request_id=f"{transaction.transaction_id.value}:change",
            counts_by_denomination=reserve.reserved_counts_by_denomination,
            currency=transaction.price.currency.code,
            correlation_id=transaction.correlation_id.value,
        )

    async def dispense(self, transaction: Transaction) -> ChangeDispenseResult | None:
        request = self.prepare_payout_request(transaction)
        if request is None:
            return None
        result = await self._change_dispenser.dispense(request)
        if result.status is PayoutStatus.DISPENSED:
            if transaction.change_reserve is None:
                raise ChangeUnavailableError("missing reserve on successful payout")
            await self._inventory.consume(transaction.change_reserve)
            transaction.mark_change_dispensed()
            return result
        if result.status is PayoutStatus.PARTIAL:
            if transaction.change_reserve is not None:
                transaction.change_reserve.mark_ambiguous()
            self._inventory.drift_detected = True
            transaction.mark_change_partial()
            raise PartialPayoutError("change payout completed partially")
        if transaction.change_reserve is not None:
            transaction.change_reserve.mark_ambiguous()
        transaction.mark_ambiguous()
        self._inventory.drift_detected = True
        raise ChangeUnavailableError("change payout did not complete successfully")

    async def dispense_refund(
        self,
        *,
        transaction_id: str,
        correlation_id: str,
        amount_minor_units: int,
        currency: str,
    ) -> ChangeDispenseResult | None:
        if amount_minor_units <= 0:
            return None
        plan = await self.plan_change(amount_minor_units)
        if plan is None:
            raise ChangeUnavailableError("unable to refund accepted cash safely")
        reserve = await self._inventory.reserve(
            transaction_id=f"{transaction_id}:refund", plan=plan
        )
        request = ChangeDispenseRequest(
            request_id=f"{transaction_id}:refund",
            counts_by_denomination=reserve.reserved_counts_by_denomination,
            currency=currency,
            correlation_id=correlation_id,
        )
        result = await self._change_dispenser.dispense(request)
        if result.status is PayoutStatus.DISPENSED:
            await self._inventory.consume(reserve)
            return result
        reserve.mark_ambiguous()
        self._inventory.drift_detected = True
        if result.status is PayoutStatus.PARTIAL:
            raise PartialPayoutError("refund payout completed partially")
        raise ChangeUnavailableError("refund payout did not complete successfully")

    def clear_drift(self) -> None:
        self._inventory.clear_drift()

    async def plan_change(self, target_minor_units: int) -> dict[int, int] | None:
        if target_minor_units < 0:
            raise ValueError("target_minor_units must be non-negative")
        if target_minor_units == 0:
            return {}
        available = await self._inventory.available_counts()
        denoms = sorted((d for d, c in available.items() if c > 0), reverse=True)

        def backtrack(index: int, remaining: int) -> dict[int, int] | None:
            if remaining == 0:
                return {}
            if index >= len(denoms):
                return None
            denomination = denoms[index]
            max_count = min(available[denomination], remaining // denomination)
            for count in range(max_count, -1, -1):
                next_remaining = remaining - denomination * count
                plan = backtrack(index + 1, next_remaining)
                if plan is not None:
                    if count > 0:
                        plan = dict(plan)
                        plan[denomination] = count
                    return plan
            return None

        return backtrack(0, target_minor_units)

    async def _calculate_worst_case_change(self, price_minor_units: int) -> int | None:
        if self._inventory.exact_change_only:
            return 0
        denominations = tuple(
            denomination for denomination in self._accepted_bill_denominations if denomination > 0
        )
        if not denominations:
            return 0
        worst_case_change = 0
        reachable_underpaid_amounts = {0}
        pending = [0]
        while pending:
            accepted_minor_units = pending.pop()
            for denomination in denominations:
                projected_total = accepted_minor_units + denomination
                if projected_total < price_minor_units:
                    if projected_total not in reachable_underpaid_amounts:
                        reachable_underpaid_amounts.add(projected_total)
                        pending.append(projected_total)
                    continue
                change_due = projected_total - price_minor_units
                if await self.plan_change(change_due) is None:
                    return None
                worst_case_change = max(worst_case_change, change_due)
        return worst_case_change

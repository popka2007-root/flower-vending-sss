"""Deterministic mock change dispenser."""

from __future__ import annotations

from collections.abc import Mapping

from flower_vending.devices.contracts import (
    ChangeDispenseRequest,
    ChangeDispenseResult,
    DeviceCommandPolicy,
    DeviceFaultCode,
    DeviceOperationalState,
    PhysicalReconciliationStatus,
    PhysicalStateReconciliation,
    PayoutStatus,
)
from flower_vending.devices.exceptions import DeviceAdapterError
from flower_vending.devices.interfaces import ChangeDispenser
from flower_vending.simulators.devices.base import MockManagedDevice
from flower_vending.simulators.faults import SimulatorFaultCode


class MockChangeDispenser(MockManagedDevice, ChangeDispenser):
    def __init__(
        self,
        name: str = "mock_change_dispenser",
        *,
        inventory: dict[int, int] | None = None,
        command_policy: DeviceCommandPolicy | None = None,
    ) -> None:
        super().__init__(name, command_policy=command_policy)
        self._inventory = dict(inventory or {})

    async def can_dispense(self, request: ChangeDispenseRequest) -> bool:
        if self.injector.has(SimulatorFaultCode.PAYOUT_UNAVAILABLE):
            return False
        return all(
            self._inventory.get(denomination, 0) >= count
            for denomination, count in request.counts_by_denomination.items()
        )

    async def dispense(self, request: ChangeDispenseRequest) -> ChangeDispenseResult:
        async def operation() -> ChangeDispenseResult:
            return await self._dispense_once(request)

        return await self._run_command(
            "dispense",
            operation,
            correlation_id=request.correlation_id,
            idempotency_key=request.request_id,
            classify_result_fault=self._result_fault_code,
            is_result_ambiguous=lambda result: result.status is PayoutStatus.AMBIGUOUS,
            reconcile=self._reconcile_dispense_result,
        )

    async def get_accounting_inventory(self) -> dict[int, int]:
        return dict(self._inventory)

    async def _dispense_once(self, request: ChangeDispenseRequest) -> ChangeDispenseResult:
        await self._consume_policy_fault(
            "dispense",
            SimulatorFaultCode.COMMAND_TIMEOUT,
            SimulatorFaultCode.TRANSIENT_COMMAND_FAILURE,
            correlation_id=request.correlation_id,
            idempotency_key=request.request_id,
        )

        unavailable = self.injector.consume(SimulatorFaultCode.PAYOUT_UNAVAILABLE)
        if unavailable is not None:
            self._activate_fault(
                code=unavailable.code.value,
                message=unavailable.message or "payout unavailable",
                **unavailable.details,
            )
            return ChangeDispenseResult(
                request_id=request.request_id,
                status=PayoutStatus.FAILED,
                details={"fault_code": unavailable.code.value, **unavailable.details},
            )

        if not await self.can_dispense(request):
            return ChangeDispenseResult(
                request_id=request.request_id,
                status=PayoutStatus.FAILED,
                details={"reason": "insufficient_inventory"},
            )

        ambiguous = self.injector.consume(SimulatorFaultCode.AMBIGUOUS_PHYSICAL_RESULT)
        if ambiguous is not None:
            self._activate_fault(
                code=ambiguous.code.value,
                message=ambiguous.message or "ambiguous payout result",
                manual_review_required=True,
                **ambiguous.details,
            )
            return ChangeDispenseResult(
                request_id=request.request_id,
                status=PayoutStatus.AMBIGUOUS,
                paid_counts_by_denomination=dict(
                    ambiguous.details.get("paid_counts_by_denomination", {})
                ),
                details={
                    "fault_code": DeviceFaultCode.AMBIGUOUS_PHYSICAL_RESULT.value,
                    "manual_review_required": True,
                    **ambiguous.details,
                },
            )

        partial = self.injector.consume(SimulatorFaultCode.PARTIAL_PAYOUT)
        if partial is not None:
            paid = self._partial_plan(request.counts_by_denomination)
            self._consume_inventory(paid)
            self._activate_fault(
                code=partial.code.value,
                message=partial.message or "partial payout",
                critical=False,
                **partial.details,
            )
            return ChangeDispenseResult(
                request_id=request.request_id,
                status=PayoutStatus.PARTIAL,
                paid_counts_by_denomination=paid,
                details={"fault_code": partial.code.value, **partial.details},
            )

        self._heartbeat(state=DeviceOperationalState.READY, inventory=dict(self._inventory))
        return ChangeDispenseResult(
            request_id=request.request_id,
            status=PayoutStatus.DISPENSED,
            paid_counts_by_denomination=dict(request.counts_by_denomination),
        )

    def _consume_inventory(self, plan: Mapping[int, int]) -> None:
        for denomination, count in plan.items():
            self._inventory[denomination] = self._inventory.get(denomination, 0) - count

    def _partial_plan(self, requested: Mapping[int, int]) -> dict[int, int]:
        paid: dict[int, int] = {}
        remaining_skip = 1
        for denomination in sorted(requested.keys(), reverse=True):
            count = requested[denomination]
            if count <= 0:
                continue
            paid_count = count
            if remaining_skip > 0:
                paid_count = max(0, count - 1)
                remaining_skip -= count - paid_count
            if paid_count > 0:
                paid[denomination] = paid_count
        if not paid:
            raise DeviceAdapterError("partial payout plan would dispense nothing")
        return paid

    def _result_fault_code(self, result: ChangeDispenseResult) -> str | None:
        if result.status is PayoutStatus.DISPENSED:
            return None
        if result.status is PayoutStatus.PARTIAL:
            return None
        fault_code = result.details.get("fault_code")
        return str(fault_code) if fault_code else None

    def _reconcile_dispense_result(
        self,
        result: ChangeDispenseResult,
    ) -> PhysicalStateReconciliation:
        if result.status is not PayoutStatus.AMBIGUOUS:
            return PhysicalStateReconciliation(status=PhysicalReconciliationStatus.CONFIRMED)
        return PhysicalStateReconciliation(
            status=PhysicalReconciliationStatus.AMBIGUOUS,
            observed_state={
                "paid_counts_by_denomination": dict(result.paid_counts_by_denomination),
            },
            expected_state={"status": PayoutStatus.DISPENSED.value},
            message="payout physical result could not be reconciled automatically",
        )

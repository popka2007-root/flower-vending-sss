"""Deterministic mock bill validator."""

from __future__ import annotations

import asyncio

from flower_vending.devices.contracts import (
    BillValidatorEvent,
    BillValidatorEventType,
    DeviceCommandPolicy,
    DeviceOperationalState,
    MoneyValue,
)
from flower_vending.devices.exceptions import (
    DeviceAdapterError,
    DeviceNotStartedError,
    UnsupportedDeviceOperationError,
)
from flower_vending.devices.interfaces import BillValidator
from flower_vending.simulators.devices.base import MockManagedDevice
from flower_vending.simulators.faults import SimulatorFaultCode


class MockBillValidator(MockManagedDevice, BillValidator):
    def __init__(
        self,
        name: str = "mock_bill_validator",
        *,
        supported_bill_values: tuple[int, ...] = (500, 1000, 2000, 5000),
        escrow_supported: bool = False,
        command_policy: DeviceCommandPolicy | None = None,
    ) -> None:
        super().__init__(name, command_policy=command_policy)
        self._supported_bill_values = supported_bill_values
        self._escrow_supported = escrow_supported
        self._accepting = False
        self._events: asyncio.Queue[BillValidatorEvent] = asyncio.Queue()

    def supports_escrow(self) -> bool:
        return self._escrow_supported

    async def enable_acceptance(self, correlation_id: str | None = None) -> None:
        if not self._started:
            raise DeviceNotStartedError(f"{self.name} has not been started")

        async def operation() -> None:
            await self._consume_policy_fault(
                "enable_acceptance",
                SimulatorFaultCode.COMMAND_TIMEOUT,
                SimulatorFaultCode.TRANSIENT_COMMAND_FAILURE,
                SimulatorFaultCode.AMBIGUOUS_PHYSICAL_RESULT,
                correlation_id=correlation_id,
                idempotency_key=correlation_id,
            )
            plan = self.injector.consume(SimulatorFaultCode.VALIDATOR_UNAVAILABLE)
            if plan is not None:
                self._activate_fault(
                    code=plan.code.value,
                    message=plan.message or "validator unavailable",
                    **plan.details,
                )
                raise DeviceAdapterError(plan.message or "validator unavailable")
            self._accepting = True
            self._heartbeat(state=DeviceOperationalState.READY, accepting=True)

        await self._run_command(
            "enable_acceptance",
            operation,
            correlation_id=correlation_id,
            idempotency_key=correlation_id,
        )

    async def disable_acceptance(self, correlation_id: str | None = None) -> None:
        async def operation() -> None:
            await self._consume_policy_fault(
                "disable_acceptance",
                SimulatorFaultCode.COMMAND_TIMEOUT,
                SimulatorFaultCode.TRANSIENT_COMMAND_FAILURE,
                SimulatorFaultCode.AMBIGUOUS_PHYSICAL_RESULT,
                correlation_id=correlation_id,
                idempotency_key=correlation_id,
            )
            self._accepting = False
            self._heartbeat(state=DeviceOperationalState.DISABLED, accepting=False)
            await self._events.put(
                BillValidatorEvent(
                    event_type=BillValidatorEventType.VALIDATOR_DISABLED,
                    validator_name=self.name,
                    correlation_id=correlation_id,
                )
            )

        await self._run_command(
            "disable_acceptance",
            operation,
            correlation_id=correlation_id,
            idempotency_key=correlation_id,
            success_state=DeviceOperationalState.DISABLED,
        )

    async def accept_escrow(self, correlation_id: str | None = None) -> None:
        if not self._escrow_supported:
            raise UnsupportedDeviceOperationError("mock validator does not support escrow")

    async def return_escrow(self, correlation_id: str | None = None) -> None:
        if not self._escrow_supported:
            raise UnsupportedDeviceOperationError("mock validator does not support escrow")

    async def read_event(self, timeout_s: float | None = None) -> BillValidatorEvent | None:
        if timeout_s is None:
            return await self._events.get()
        try:
            return await asyncio.wait_for(self._events.get(), timeout_s)
        except asyncio.TimeoutError:
            return None

    async def simulate_insert_bill(
        self,
        bill_minor_units: int,
        *,
        correlation_id: str | None = None,
        currency: str = "RUB",
    ) -> None:
        if not self._started:
            raise DeviceNotStartedError(f"{self.name} has not been started")
        if not self._accepting:
            raise DeviceAdapterError("validator is not accepting bills")
        bill_value = MoneyValue(minor_units=bill_minor_units, currency=currency)
        await self._events.put(
            BillValidatorEvent(
                event_type=BillValidatorEventType.BILL_DETECTED,
                validator_name=self.name,
                correlation_id=correlation_id,
                bill_value=bill_value,
            )
        )
        jam_plan = self.injector.consume(SimulatorFaultCode.BILL_JAM)
        if jam_plan is not None:
            self._accepting = False
            self._activate_fault(
                code=jam_plan.code.value,
                message=jam_plan.message or "bill jam",
                **jam_plan.details,
            )
            await self._events.put(
                BillValidatorEvent(
                    event_type=BillValidatorEventType.VALIDATOR_FAULT,
                    validator_name=self.name,
                    correlation_id=correlation_id,
                    bill_value=bill_value,
                    details={"fault_code": jam_plan.code.value, **jam_plan.details},
                )
            )
            return

        rejected_plan = self.injector.consume(SimulatorFaultCode.BILL_REJECTED)
        if rejected_plan is not None or bill_minor_units not in self._supported_bill_values:
            await self._events.put(
                BillValidatorEvent(
                    event_type=BillValidatorEventType.BILL_REJECTED,
                    validator_name=self.name,
                    correlation_id=correlation_id,
                    bill_value=bill_value,
                    details={
                        "reason": rejected_plan.message if rejected_plan else "unsupported_bill"
                    },
                )
            )
            return

        await self._events.put(
            BillValidatorEvent(
                event_type=BillValidatorEventType.BILL_VALIDATED,
                validator_name=self.name,
                correlation_id=correlation_id,
                bill_value=bill_value,
            )
        )
        if self._escrow_supported:
            await self._events.put(
                BillValidatorEvent(
                    event_type=BillValidatorEventType.ESCROW_AVAILABLE,
                    validator_name=self.name,
                    correlation_id=correlation_id,
                    bill_value=bill_value,
                )
            )
        await self._events.put(
            BillValidatorEvent(
                event_type=BillValidatorEventType.BILL_STACKED,
                validator_name=self.name,
                correlation_id=correlation_id,
                bill_value=bill_value,
            )
        )

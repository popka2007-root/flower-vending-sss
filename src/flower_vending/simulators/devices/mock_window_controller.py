"""Deterministic mock delivery window controller."""

from __future__ import annotations

from flower_vending.devices.contracts import (
    DeviceCommandPolicy,
    DeviceOperationalState,
    WindowPosition,
    WindowStatus,
)
from flower_vending.devices.exceptions import DeviceAdapterError
from flower_vending.devices.interfaces import WindowController
from flower_vending.simulators.devices.base import MockManagedDevice
from flower_vending.simulators.faults import SimulatorFaultCode


class MockWindowController(MockManagedDevice, WindowController):
    def __init__(
        self,
        name: str = "mock_window_controller",
        *,
        command_policy: DeviceCommandPolicy | None = None,
    ) -> None:
        super().__init__(name, command_policy=command_policy)
        self._status = WindowStatus(
            controller_name=name, position=WindowPosition.CLOSED, locked=False
        )

    async def open_window(self, correlation_id: str | None = None) -> None:
        async def operation() -> None:
            await self._consume_policy_fault(
                "open_window",
                SimulatorFaultCode.COMMAND_TIMEOUT,
                SimulatorFaultCode.TRANSIENT_COMMAND_FAILURE,
                SimulatorFaultCode.AMBIGUOUS_PHYSICAL_RESULT,
                correlation_id=correlation_id,
                idempotency_key=correlation_id,
            )
            plan = self.injector.consume(SimulatorFaultCode.WINDOW_FAULT)
            if plan is not None:
                self._activate_fault(
                    code=plan.code.value,
                    message=plan.message or "window fault",
                    **plan.details,
                )
                raise DeviceAdapterError(plan.message or "window fault")
            self._status = WindowStatus(
                controller_name=self.name, position=WindowPosition.OPEN, locked=False
            )
            self._heartbeat(
                state=DeviceOperationalState.READY, position=self._status.position.value
            )

        await self._run_command(
            "open_window",
            operation,
            correlation_id=correlation_id,
            idempotency_key=correlation_id,
        )

    async def close_window(self, correlation_id: str | None = None) -> None:
        async def operation() -> None:
            await self._consume_policy_fault(
                "close_window",
                SimulatorFaultCode.COMMAND_TIMEOUT,
                SimulatorFaultCode.TRANSIENT_COMMAND_FAILURE,
                SimulatorFaultCode.AMBIGUOUS_PHYSICAL_RESULT,
                correlation_id=correlation_id,
                idempotency_key=correlation_id,
            )
            plan = self.injector.consume(SimulatorFaultCode.WINDOW_FAULT)
            if plan is not None:
                self._activate_fault(
                    code=plan.code.value,
                    message=plan.message or "window fault",
                    **plan.details,
                )
                raise DeviceAdapterError(plan.message or "window fault")
            self._status = WindowStatus(
                controller_name=self.name, position=WindowPosition.CLOSED, locked=False
            )
            self._heartbeat(
                state=DeviceOperationalState.READY, position=self._status.position.value
            )

        await self._run_command(
            "close_window",
            operation,
            correlation_id=correlation_id,
            idempotency_key=correlation_id,
        )

    async def get_window_status(self) -> WindowStatus:
        return self._status

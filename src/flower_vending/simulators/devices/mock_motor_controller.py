"""Deterministic mock motor controller."""

from __future__ import annotations

from flower_vending.devices.contracts import DeviceCommandPolicy, DeviceOperationalState
from flower_vending.devices.exceptions import DeviceAdapterError
from flower_vending.devices.interfaces import MotorController
from flower_vending.simulators.devices.base import MockManagedDevice
from flower_vending.simulators.faults import SimulatorFaultCode


class MockMotorController(MockManagedDevice, MotorController):
    def __init__(
        self,
        name: str = "mock_motor",
        *,
        command_policy: DeviceCommandPolicy | None = None,
    ) -> None:
        super().__init__(name, command_policy=command_policy)
        self.vend_history: list[str] = []

    async def home(self, correlation_id: str | None = None) -> None:
        async def operation() -> None:
            await self._consume_policy_fault(
                "home",
                SimulatorFaultCode.COMMAND_TIMEOUT,
                SimulatorFaultCode.TRANSIENT_COMMAND_FAILURE,
                SimulatorFaultCode.AMBIGUOUS_PHYSICAL_RESULT,
                correlation_id=correlation_id,
                idempotency_key=correlation_id,
            )
            self._heartbeat(state=DeviceOperationalState.READY, action="home")

        await self._run_command(
            "home",
            operation,
            correlation_id=correlation_id,
            idempotency_key=correlation_id,
        )

    async def vend_slot(self, slot_id: str, correlation_id: str | None = None) -> None:
        idempotency_key = correlation_id or f"vend:{slot_id}"

        async def operation() -> None:
            await self._consume_policy_fault(
                "vend_slot",
                SimulatorFaultCode.COMMAND_TIMEOUT,
                SimulatorFaultCode.TRANSIENT_COMMAND_FAILURE,
                SimulatorFaultCode.AMBIGUOUS_PHYSICAL_RESULT,
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
            )
            plan = self.injector.consume(SimulatorFaultCode.MOTOR_FAULT)
            if plan is not None:
                self._activate_fault(
                    code=plan.code.value,
                    message=plan.message or "motor fault",
                    **plan.details,
                )
                raise DeviceAdapterError(plan.message or "motor fault")
            power_loss = self.injector.consume(SimulatorFaultCode.POWER_LOSS_DURING_MOTION)
            if power_loss is not None:
                self.vend_history.append(slot_id)
                self._heartbeat(
                    state=DeviceOperationalState.RECOVERY_PENDING,
                    last_slot=slot_id,
                    ambiguous_vend=True,
                )
                self._activate_fault(
                    code=power_loss.code.value,
                    message=power_loss.message or "power loss during motor motion",
                    critical=True,
                    ambiguous_vend=True,
                )
                raise DeviceAdapterError(power_loss.message or "power loss during motor motion")
            self.vend_history.append(slot_id)
            self._heartbeat(state=DeviceOperationalState.READY, last_slot=slot_id)

        await self._run_command(
            "vend_slot",
            operation,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
        )

    async def start_motion(self) -> None:
        self._heartbeat(state=DeviceOperationalState.READY, action="start_motion")

    async def stop_motion(self) -> None:
        self._heartbeat(state=DeviceOperationalState.DEGRADED, action="stop_motion")

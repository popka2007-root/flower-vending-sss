"""Deterministic mock watchdog adapter."""

from __future__ import annotations

from flower_vending.devices.contracts import DeviceCommandPolicy, DeviceOperationalState
from flower_vending.devices.exceptions import DeviceAdapterError
from flower_vending.devices.interfaces import WatchdogAdapter
from flower_vending.simulators.devices.base import MockManagedDevice
from flower_vending.simulators.faults import SimulatorFaultCode


class MockWatchdogAdapter(MockManagedDevice, WatchdogAdapter):
    def __init__(
        self,
        name: str = "mock_watchdog",
        *,
        command_policy: DeviceCommandPolicy | None = None,
    ) -> None:
        super().__init__(name, command_policy=command_policy)
        self._armed_timeout_s: float | None = None

    async def arm(self, timeout_s: float) -> None:
        async def operation() -> None:
            await self._consume_policy_fault(
                "arm",
                SimulatorFaultCode.COMMAND_TIMEOUT,
                SimulatorFaultCode.TRANSIENT_COMMAND_FAILURE,
            )
            plan = self.injector.consume(SimulatorFaultCode.WATCHDOG_FAULT)
            if plan is not None:
                self._activate_fault(
                    code=plan.code.value,
                    message=plan.message or "watchdog fault",
                    **plan.details,
                )
                raise DeviceAdapterError(plan.message or "watchdog fault")
            self._armed_timeout_s = timeout_s
            self._heartbeat(state=DeviceOperationalState.READY, armed_timeout_s=timeout_s)

        await self._run_command("arm", operation, idempotency_key=f"arm:{timeout_s}")

    async def kick(self) -> None:
        async def operation() -> None:
            await self._consume_policy_fault(
                "kick",
                SimulatorFaultCode.COMMAND_TIMEOUT,
                SimulatorFaultCode.TRANSIENT_COMMAND_FAILURE,
            )
            self._heartbeat(
                state=DeviceOperationalState.READY, armed_timeout_s=self._armed_timeout_s
            )

        await self._run_command("kick", operation)

    async def disarm(self) -> None:
        async def operation() -> None:
            self._armed_timeout_s = None
            self._heartbeat(state=DeviceOperationalState.DISABLED, armed_timeout_s=None)

        await self._run_command(
            "disarm",
            operation,
            idempotency_key="disarm",
            success_state=DeviceOperationalState.DISABLED,
        )

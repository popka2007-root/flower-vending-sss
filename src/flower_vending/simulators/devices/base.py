"""Base classes for deterministic simulator devices."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import replace
from typing import Any, TypeVar

from flower_vending.devices.command_policy import DeviceCommandRunner
from flower_vending.devices.contracts import (
    DeviceCommandPolicy,
    DeviceFault,
    DeviceFaultCode,
    DeviceHealth,
    DeviceOperationalState,
    utc_now,
)
from flower_vending.devices.exceptions import (
    AmbiguousDeviceResultError,
    DeviceCommandError,
    DeviceCommandTimeoutError,
)
from flower_vending.devices.interfaces import ManagedDevice
from flower_vending.simulators.faults import FaultInjectionPlan, FaultInjector, SimulatorFaultCode

T = TypeVar("T")


class MockManagedDevice(ManagedDevice):
    """Common lifecycle and health behavior for simulator devices."""

    def __init__(
        self,
        name: str,
        *,
        injector: FaultInjector | None = None,
        command_policy: DeviceCommandPolicy | None = None,
    ) -> None:
        self._name = name
        self._injector = injector or FaultInjector()
        self._command_policy = command_policy or DeviceCommandPolicy()
        self._command_runner = DeviceCommandRunner(
            device_name=name,
            default_policy=self._command_policy,
            activate_fault=self._activate_fault,
            heartbeat=self._heartbeat,
        )
        self._started = False
        self._health = DeviceHealth(name=name, state=DeviceOperationalState.UNKNOWN)

    @property
    def name(self) -> str:
        return self._name

    @property
    def injector(self) -> FaultInjector:
        return self._injector

    @property
    def command_policy(self) -> DeviceCommandPolicy:
        return self._command_policy

    async def start(self) -> None:
        self._started = True
        self._health = replace(
            self._health,
            state=DeviceOperationalState.READY,
            last_heartbeat_at=utc_now(),
            faults=(),
        )

    async def stop(self) -> None:
        self._started = False
        self._health = replace(
            self._health,
            state=DeviceOperationalState.DISABLED,
            last_heartbeat_at=utc_now(),
        )

    async def get_health(self) -> DeviceHealth:
        return self._health

    def inject_fault(
        self,
        code: SimulatorFaultCode,
        *,
        remaining_hits: int = 1,
        message: str | None = None,
        critical: bool = True,
        **details: Any,
    ) -> None:
        self._injector.add(
            FaultInjectionPlan(
                code=code,
                remaining_hits=remaining_hits,
                message=message,
                critical=critical,
                details=details,
            )
        )

    def clear_faults(self) -> None:
        self._injector.clear()
        self._health = replace(self._health, faults=(), state=DeviceOperationalState.READY)

    def _activate_fault(
        self, code: str, message: str, *, critical: bool = True, **details: Any
    ) -> None:
        self._health = DeviceHealth(
            name=self.name,
            state=DeviceOperationalState.FAULT if critical else DeviceOperationalState.DEGRADED,
            last_heartbeat_at=utc_now(),
            faults=(DeviceFault(code=code, message=message, critical=critical, details=details),),
            details=details,
        )

    def _heartbeat(self, *, state: DeviceOperationalState | None = None, **details: Any) -> None:
        next_state = self._health.state if state is None else state
        self._health = DeviceHealth(
            name=self.name,
            state=next_state,
            last_heartbeat_at=utc_now(),
            faults=self._health.faults,
            details=details or self._health.details,
        )

    async def _run_command(
        self,
        command_name: str,
        operation: Callable[[], Awaitable[T]],
        *,
        correlation_id: str | None = None,
        idempotency_key: str | None = None,
        command_policy: DeviceCommandPolicy | None = None,
        **kwargs: Any,
    ) -> T:
        return await self._command_runner.run(
            command_name,
            operation,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            policy=command_policy,
            **kwargs,
        )

    async def _consume_policy_fault(
        self,
        command_name: str,
        *codes: SimulatorFaultCode,
        correlation_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> FaultInjectionPlan | None:
        for code in codes:
            plan = self.injector.consume(code)
            if plan is None:
                continue
            delay_s = float(plan.details.get("delay_s", 0.0))
            if delay_s > 0:
                await asyncio.sleep(delay_s)
            if plan.code is SimulatorFaultCode.COMMAND_TIMEOUT:
                raise DeviceCommandTimeoutError(
                    plan.message or f"{command_name} timed out",
                    correlation_id=correlation_id,
                    idempotency_key=idempotency_key,
                )
            if plan.code is SimulatorFaultCode.TRANSIENT_COMMAND_FAILURE:
                raise DeviceCommandError(
                    plan.message or f"{command_name} transient command failure",
                    fault_code=DeviceFaultCode.TRANSIENT_COMMAND_FAILURE.value,
                    correlation_id=correlation_id,
                    idempotency_key=idempotency_key,
                    retryable=True,
                )
            if plan.code is SimulatorFaultCode.AMBIGUOUS_PHYSICAL_RESULT:
                raise AmbiguousDeviceResultError(
                    plan.message or f"{command_name} physical result is ambiguous",
                    correlation_id=correlation_id,
                    idempotency_key=idempotency_key,
                )
            return plan
        return None

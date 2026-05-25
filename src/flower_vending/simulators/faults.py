"""Deterministic fault-injection primitives for simulator devices."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class SimulatorFaultCode(StrEnum):
    COMMAND_TIMEOUT = "command_timeout"
    TRANSIENT_COMMAND_FAILURE = "transient_command_failure"
    AMBIGUOUS_PHYSICAL_RESULT = "ambiguous_physical_result"
    VALIDATOR_UNAVAILABLE = "validator_unavailable"
    BILL_JAM = "bill_jam"
    BILL_REJECTED = "bill_rejected"
    PAYOUT_UNAVAILABLE = "payout_unavailable"
    PARTIAL_PAYOUT = "partial_payout"
    MOTOR_FAULT = "motor_fault"
    WINDOW_FAULT = "window_fault"
    WATCHDOG_FAULT = "watchdog_fault"
    POWER_LOSS_DURING_MOTION = "power_loss_during_motion"


@dataclass(slots=True)
class FaultInjectionPlan:
    code: SimulatorFaultCode
    remaining_hits: int = 1
    message: str | None = None
    critical: bool = True
    details: dict[str, Any] = field(default_factory=dict)

    def consume(self) -> bool:
        if self.remaining_hits == 0:
            return False
        self.remaining_hits -= 1
        return True

    @property
    def exhausted(self) -> bool:
        return self.remaining_hits == 0


class FaultInjector:
    """Stores deterministic fault plans consumed by simulator devices."""

    def __init__(self) -> None:
        self._plans: dict[SimulatorFaultCode, list[FaultInjectionPlan]] = {}

    def add(self, plan: FaultInjectionPlan) -> None:
        self._plans.setdefault(plan.code, []).append(plan)

    def clear(self, code: SimulatorFaultCode | None = None) -> None:
        if code is None:
            self._plans.clear()
            return
        self._plans.pop(code, None)

    def has(self, code: SimulatorFaultCode) -> bool:
        return bool(self._plans.get(code))

    def consume(self, code: SimulatorFaultCode) -> FaultInjectionPlan | None:
        plans = self._plans.get(code)
        if not plans:
            return None
        plan = plans[0]
        if not plan.consume():
            return None
        if plan.exhausted:
            plans.pop(0)
        if not plans:
            self._plans.pop(code, None)
        return plan

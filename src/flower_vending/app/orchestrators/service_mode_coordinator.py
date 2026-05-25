"""Service-mode orchestration for technician workflows."""

from __future__ import annotations

import hashlib
import time

from flower_vending.app.event_bus import EventBus
from flower_vending.app.fsm import MachineState, StateMachineEngine
from flower_vending.app.services.machine_status_service import MachineStatusService
from flower_vending.domain.commands.service_commands import EnterServiceMode, LockPurchaseButton
from flower_vending.domain.events.machine_events import machine_event
from flower_vending.domain.exceptions import FlowerVendingError


_MAX_ATTEMPTS = 5
_LOCKOUT_DURATION_S = 30.0


class ServiceModeLockedError(FlowerVendingError):
    pass


def _now() -> float:
    return time.monotonic()


def _hash_pin(pin: str) -> str:
    return hashlib.sha256(pin.encode()).hexdigest()


class ServiceModeCoordinator:
    def __init__(
        self,
        *,
        event_bus: EventBus,
        fsm: StateMachineEngine,
        machine_status_service: MachineStatusService,
        service_pin: str = "0000",
    ) -> None:
        self._event_bus = event_bus
        self._fsm = fsm
        self._machine_status_service = machine_status_service
        self._service_pin_hash = _hash_pin(service_pin)
        self._purchase_locked = False
        self._failed_attempts = 0
        self._first_failed_at = 0.0

    @property
    def purchase_locked(self) -> bool:
        return self._purchase_locked

    async def enter_service_mode(self, command: EnterServiceMode) -> str:
        now = _now()
        if self._failed_attempts >= _MAX_ATTEMPTS:
            if now - self._first_failed_at < _LOCKOUT_DURATION_S:
                remaining = int(_LOCKOUT_DURATION_S - (now - self._first_failed_at))
                raise ServiceModeLockedError(f"service mode locked; try again in {remaining}s")
            self._failed_attempts = 0
        if _hash_pin(command.pin) != self._service_pin_hash:
            self._failed_attempts += 1
            if self._failed_attempts == 1:
                self._first_failed_at = now
            if self._failed_attempts >= _MAX_ATTEMPTS:
                raise ServiceModeLockedError(
                    f"service mode locked for {int(_LOCKOUT_DURATION_S)}s after {self._failed_attempts} failed attempts"
                )
            raise ValueError("Invalid service PIN")
        self._failed_attempts = 0
        if self._fsm.can_transition(MachineState.SERVICE_MODE):
            self._fsm.transition(MachineState.SERVICE_MODE, command.reason)
        else:
            self._fsm.force_state(MachineState.SERVICE_MODE, command.reason)
        self._machine_status_service.set_service_mode(True)
        self._machine_status_service.set_machine_state(self._fsm.current_state)
        await self._event_bus.publish(
            machine_event(
                "service_mode_entered",
                correlation_id=command.correlation_id,
                operator_id=command.operator_id,
                reason=command.reason,
            )
        )
        return self._fsm.current_state.value

    async def exit_service_mode(
        self,
        *,
        correlation_id: str,
        reason: str = "service_mode_exit",
        operator_id: str | None = None,
    ) -> str:
        self._machine_status_service.set_service_mode(False)
        self._purchase_locked = False
        if self._fsm.can_transition(MachineState.IDLE):
            self._fsm.transition(MachineState.IDLE, reason)
        else:
            self._fsm.force_state(MachineState.IDLE, reason)
        self._machine_status_service.set_machine_state(self._fsm.current_state)
        await self._event_bus.publish(
            machine_event(
                "service_mode_exited",
                correlation_id=correlation_id,
                operator_id=operator_id,
                reason=reason,
            )
        )
        return self._fsm.current_state.value

    async def lock_purchase_button(self, command: LockPurchaseButton) -> bool:
        self._purchase_locked = command.locked
        self._machine_status_service.set_machine_state(self._fsm.current_state)
        await self._event_bus.publish(
            machine_event(
                "purchase_button_locked" if command.locked else "purchase_button_unlocked",
                correlation_id=command.correlation_id,
                operator_id=command.operator_id,
            )
        )
        return self._purchase_locked

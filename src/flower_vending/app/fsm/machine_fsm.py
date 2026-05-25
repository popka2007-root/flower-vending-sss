"""FSM engine for the vending machine runtime."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone

from flower_vending.app.fsm.states import MachineState
from flower_vending.app.fsm.transitions import ALLOWED_TRANSITIONS
from flower_vending.domain.exceptions import InvariantViolationError


def _ts() -> datetime:
    return datetime.now(tz=timezone.utc)


StateTransitionListener = Callable[["StateTransitionRecord"], None]


@dataclass(frozen=True, slots=True)
class StateTransitionRecord:
    previous_state: MachineState
    new_state: MachineState
    reason: str
    occurred_at: datetime = field(default_factory=_ts)


logger = logging.getLogger(__name__)


class StateMachineEngine:
    def __init__(self, initial_state: MachineState = MachineState.BOOT) -> None:
        self._state = initial_state
        self._history: list[StateTransitionRecord] = []
        self._listeners: list[StateTransitionListener] = []

    @property
    def current_state(self) -> MachineState:
        return self._state

    @property
    def history(self) -> tuple[StateTransitionRecord, ...]:
        return tuple(self._history)

    def subscribe(self, listener: StateTransitionListener) -> None:
        self._listeners.append(listener)

    def can_transition(self, target_state: MachineState) -> bool:
        return target_state in ALLOWED_TRANSITIONS.get(self._state, set())

    def transition(self, target_state: MachineState, reason: str) -> StateTransitionRecord:
        if target_state == self._state:
            return StateTransitionRecord(self._state, target_state, reason)
        if not self.can_transition(target_state):
            raise InvariantViolationError(
                f"transition {self._state.value} -> {target_state.value} is not allowed"
            )
        record = StateTransitionRecord(self._state, target_state, reason)
        self._history.append(record)
        self._state = target_state
        self._notify(record)
        return record

    def force_state(self, target_state: MachineState, reason: str) -> StateTransitionRecord:
        """Force a state for controlled recovery or bootstrap scenarios."""
        logger.warning(
            "force_state: %s -> %s, reason=%s", self._state.value, target_state.value, reason
        )
        record = StateTransitionRecord(self._state, target_state, reason)
        self._history.append(record)
        self._state = target_state
        self._notify(record)
        return record

    def _notify(self, record: StateTransitionRecord) -> None:
        for listener in tuple(self._listeners):
            listener(record)

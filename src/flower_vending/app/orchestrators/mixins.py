"""Mixins for orchestrators."""

from __future__ import annotations

from flower_vending.app.journal import JournalOutcome
from typing import TYPE_CHECKING
from flower_vending.domain.entities import Transaction

if TYPE_CHECKING:
    from flower_vending.app.journal import ApplicationJournal
    from flower_vending.app.fsm import StateMachineEngine


class TransactionJournalingMixin:
    """Mixin to provide common transaction journaling methods."""

    _journal: ApplicationJournal
    _fsm: StateMachineEngine

    def _record_intent(
        self,
        transaction: Transaction,
        *,
        action_name: str,
        logical_step: str,
        **payload: object,
    ) -> None:
        self._journal.record_intent(
            action_name=action_name,
            correlation_id=transaction.correlation_id.value,
            transaction_id=transaction.transaction_id.value,
            logical_step=logical_step,
            machine_state=self._fsm.current_state.value,
            transaction_status=transaction.status.value,
            payload=dict(payload),
        )

    def _record_outcome(
        self,
        transaction: Transaction,
        *,
        action_name: str,
        logical_step: str,
        outcome: JournalOutcome,
        **payload: object,
    ) -> None:
        self._journal.record_outcome(
            action_name=action_name,
            outcome=outcome,
            correlation_id=transaction.correlation_id.value,
            transaction_id=transaction.transaction_id.value,
            logical_step=logical_step,
            machine_state=self._fsm.current_state.value,
            transaction_status=transaction.status.value,
            payload=dict(payload),
        )

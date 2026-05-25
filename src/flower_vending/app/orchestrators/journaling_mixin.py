from typing import Protocol
from flower_vending.domain.entities import Transaction
from flower_vending.app.journal import ApplicationJournal, JournalOutcome
from flower_vending.app.fsm import StateMachineEngine

class JournalingMixinProtocol(Protocol):
    _journal: ApplicationJournal
    _fsm: StateMachineEngine

class JournalingMixin:
    def _record_intent(
        self: JournalingMixinProtocol,
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
        self: JournalingMixinProtocol,
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

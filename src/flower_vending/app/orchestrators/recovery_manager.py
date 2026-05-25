"""Recovery orchestration for unresolved transactions."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

from flower_vending.app.event_bus import EventBus
from flower_vending.app.fsm import MachineState, StateMachineEngine
from flower_vending.app.journal import (
    ApplicationJournal,
    ApplicationJournalRecord,
    NoopApplicationJournal,
)
from flower_vending.app.orchestrators.transaction_coordinator import TransactionCoordinator
from flower_vending.app.services.machine_status_service import MachineStatusService
from flower_vending.domain.entities import (
    PaymentStatus,
    PayoutStatus,
    Transaction,
    TransactionStatus,
)
from flower_vending.domain.events.machine_events import machine_event
from flower_vending.domain.exceptions import ManualInterventionRequiredError


_logger = logging.getLogger(__name__)

IntentClassification = Literal["manual_review_required", "cancel_safe"]


@dataclass(frozen=True, slots=True)
class RecoveryPlan:
    transaction_id: str
    action: str
    reason: str
    operator_required: bool
    intent_classification: IntentClassification | None = None


_INTENT_CLASSIFICATION: dict[str, IntentClassification] = {
    "motor_vend_requested": "manual_review_required",
    "window_open_requested": "manual_review_required",
    "window_close_requested": "manual_review_required",
    "refund_dispense_requested": "manual_review_required",
    "change_dispense_requested": "manual_review_required",
    "inventory_decrement": "manual_review_required",
    "acceptance_disable_requested": "cancel_safe",
}


def classify_intent(action_name: str) -> IntentClassification:
    return _INTENT_CLASSIFICATION.get(action_name, "cancel_safe")


class RecoveryManager:
    def __init__(
        self,
        *,
        transaction_coordinator: TransactionCoordinator,
        event_bus: EventBus,
        fsm: StateMachineEngine,
        machine_status_service: MachineStatusService,
        journal: ApplicationJournal | None = None,
    ) -> None:
        self._transaction_coordinator = transaction_coordinator
        self._event_bus = event_bus
        self._fsm = fsm
        self._machine_status_service = machine_status_service
        self._journal = journal or NoopApplicationJournal()

    def assess(self, transaction: Transaction) -> RecoveryPlan:
        if transaction.status in {TransactionStatus.COMPLETED, TransactionStatus.CANCELLED}:
            return RecoveryPlan(
                transaction.transaction_id.value, "none", "transaction_terminal", False
            )
        if transaction.status is TransactionStatus.PICKUP_TIMED_OUT:
            return RecoveryPlan(
                transaction.transaction_id.value, "manual_review", "pickup_timeout", True
            )
        if transaction.status in {TransactionStatus.AMBIGUOUS, TransactionStatus.FAULTED}:
            return RecoveryPlan(
                transaction.transaction_id.value, "manual_review", "ambiguous_side_effect", True
            )
        if transaction.payment_status is PaymentStatus.CONFIRMED and transaction.payout_status in {
            PayoutStatus.PARTIAL,
            PayoutStatus.AMBIGUOUS,
            PayoutStatus.FAILED,
        }:
            return RecoveryPlan(
                transaction.transaction_id.value, "manual_review", "payout_unresolved", True
            )
        if transaction.payment_status is PaymentStatus.CONFIRMED:
            return RecoveryPlan(
                transaction.transaction_id.value,
                "pending_review",
                "confirmed_payment_replay_needed",
                True,
            )
        return RecoveryPlan(
            transaction.transaction_id.value, "cancel_safe", "payment_not_confirmed", False
        )

    async def detect_unresolved_intents(self, correlation_id: str) -> tuple[RecoveryPlan, ...]:
        plans: list[RecoveryPlan] = []
        for intent in self._journal.unresolved_intents():
            plan = self._mark_unresolved_intent(intent)
            if plan is None:
                continue
            plans.append(plan)
            _logger.warning(
                "unresolved_intent_detected action=%s transaction_id=%s classification=%s",
                intent.entry_name,
                plan.transaction_id,
                plan.intent_classification,
            )
            await self._event_bus.publish(
                machine_event(
                    "unresolved_intent_detected",
                    correlation_id=correlation_id,
                    transaction_id=plan.transaction_id,
                    action=plan.action,
                    reason=plan.reason,
                    intent_classification=plan.intent_classification,
                    intent_name=intent.entry_name,
                    logical_step=intent.payload.get("logical_step"),
                )
            )
            if plan.operator_required:
                await self._event_bus.publish(
                    machine_event(
                        "manual_review_required",
                        correlation_id=correlation_id,
                        transaction_id=plan.transaction_id,
                        action=plan.action,
                        reason=plan.reason,
                        intent_classification=plan.intent_classification,
                    )
                )
        if plans:
            if self._fsm.can_transition(MachineState.RECOVERY_PENDING):
                self._fsm.transition(
                    MachineState.RECOVERY_PENDING, "unresolved_intent_recovery_required"
                )
            else:
                self._fsm.force_state(
                    MachineState.RECOVERY_PENDING, "unresolved_intent_recovery_required"
                )
            self._machine_status_service.set_machine_state(self._fsm.current_state)
            self._machine_status_service.block_sales("recovery_pending")

        orphaned = self._journal.orphaned_outcomes()
        for record in orphaned:
            _logger.warning(
                "orphaned_outcome_detected action=%s transaction_id=%s",
                record.entry_name,
                record.transaction_id,
            )
            await self._event_bus.publish(
                machine_event(
                    "orphaned_outcome_detected",
                    correlation_id=correlation_id,
                    transaction_id=record.transaction_id,
                    action=record.entry_name,
                )
            )

        return tuple(plans)

    async def recover_transaction(self, transaction_id: str, correlation_id: str) -> RecoveryPlan:
        transaction = self._transaction_coordinator.require(transaction_id)
        plan = self.assess(transaction)
        if self._fsm.can_transition(MachineState.RECOVERY_PENDING):
            self._fsm.transition(MachineState.RECOVERY_PENDING, "recovery_started")
        else:
            self._fsm.force_state(MachineState.RECOVERY_PENDING, "recovery_started_forced")
        self._machine_status_service.set_machine_state(self._fsm.current_state)
        self._machine_status_service.block_sales("recovery_pending")
        await self._event_bus.publish(
            machine_event(
                "recovery_started",
                correlation_id=correlation_id,
                transaction_id=transaction_id,
                action=plan.action,
                reason=plan.reason,
                intent_classification=plan.intent_classification,
            )
        )
        if plan.operator_required:
            await self._event_bus.publish(
                machine_event(
                    "manual_review_required",
                    correlation_id=correlation_id,
                    transaction_id=transaction_id,
                    action=plan.action,
                    reason=plan.reason,
                    intent_classification=plan.intent_classification,
                )
            )
            _logger.warning(
                "recovery_manual_review_required transaction_id=%s action=%s reason=%s classification=%s",
                transaction_id,
                plan.action,
                plan.reason,
                plan.intent_classification,
            )
            raise ManualInterventionRequiredError(plan.reason)
        if plan.action == "cancel_safe" or plan.intent_classification == "cancel_safe":
            transaction.cancel()
            self._transaction_coordinator.clear_active(transaction_id)
            self._machine_status_service.set_active_transaction(None)
            self._machine_status_service.unblock_sales("recovery_pending")
            self._fsm.transition(MachineState.IDLE, "recovery_completed")
            self._machine_status_service.set_machine_state(self._fsm.current_state)
            await self._event_bus.publish(
                machine_event(
                    "recovery_completed",
                    correlation_id=correlation_id,
                    transaction_id=transaction_id,
                    action=plan.action,
                    intent_classification=plan.intent_classification,
                )
            )
        return plan

    def _mark_unresolved_intent(self, intent: ApplicationJournalRecord) -> RecoveryPlan | None:
        if intent.transaction_id is None:
            return None
        transaction = self._transaction_coordinator.get(intent.transaction_id)
        if transaction is None:
            return None
        classification = classify_intent(intent.entry_name)
        if classification == "manual_review_required":
            transaction.mark_ambiguous()
            return RecoveryPlan(
                transaction_id=intent.transaction_id,
                action="manual_review",
                reason=f"unresolved_intent:{intent.entry_name}",
                operator_required=True,
                intent_classification=classification,
            )
        transaction.mark_recovery_pending()
        return RecoveryPlan(
            transaction_id=intent.transaction_id,
            action="recovery_pending",
            reason=f"unresolved_intent:{intent.entry_name}",
            operator_required=False,
            intent_classification=classification,
        )

"""Payment orchestration for cash sales."""

from __future__ import annotations

from flower_vending.app.event_bus import EventBus
from flower_vending.app.fsm import MachineState, StateMachineEngine
from flower_vending.app.journal import ApplicationJournal, JournalOutcome, NoopApplicationJournal
from flower_vending.app.orchestrators.transaction_coordinator import TransactionCoordinator
from flower_vending.app.services.machine_status_service import MachineStatusService
from flower_vending.devices.contracts import BillValidatorEvent, BillValidatorEventType
from flower_vending.devices.interfaces import BillValidator
from flower_vending.domain.aggregates import PurchaseTransactionAggregate
from flower_vending.app.orchestrators.journaling_mixin import JournalingMixin
from flower_vending.domain.entities import PaymentStatus, Transaction
from flower_vending.domain.events.device_events import device_event
from flower_vending.domain.events.payment_events import payment_event
from flower_vending.domain.exceptions import ChangeUnavailableError, ValidatorUnavailableError
from flower_vending.payments.change_manager import ChangeManager


class PaymentCoordinator(JournalingMixin):
    def __init__(
        self,
        *,
        validator: BillValidator,
        change_manager: ChangeManager,
        transaction_coordinator: TransactionCoordinator,
        event_bus: EventBus,
        fsm: StateMachineEngine,
        machine_status_service: MachineStatusService,
        journal: ApplicationJournal | None = None,
    ) -> None:
        self._validator = validator
        self._change_manager = change_manager
        self._transaction_coordinator = transaction_coordinator
        self._event_bus = event_bus
        self._fsm = fsm
        self._machine_status_service = machine_status_service
        self._journal = journal or NoopApplicationJournal()

    async def start_cash_session(self, transaction_id: str, correlation_id: str) -> Transaction:
        self._machine_status_service.ensure_sales_allowed()
        transaction = self._transaction_coordinator.require(transaction_id)
        assessment = await self._change_manager.assess_sale(transaction)

        with self._journal.atomic_transaction():
            self._machine_status_service.set_exact_change_only(assessment.exact_change_only)
            if not assessment.sale_supported:
                raise ChangeUnavailableError("cash sale is unsafe because change cannot be guaranteed")
            if assessment.plan:
                reserve = await self._change_manager.reserve_for_transaction(
                    transaction_id=transaction.transaction_id.value,
                    plan=assessment.plan,
                )
                transaction.attach_change_reserve(reserve)
            session = PurchaseTransactionAggregate(transaction).start_cash_session()
            self._fsm.transition(MachineState.ACCEPTING_CASH, "cash_session_started")
            self._machine_status_service.set_machine_state(self._fsm.current_state)
            self._record_intent(
                transaction,
                action_name="acceptance_enable_requested",
                logical_step="start_cash_session.enable_acceptance",
            )

        if assessment.plan and transaction.change_reserve:
            await self._event_bus.publish(
                payment_event(
                    "change_reserve_created",
                    correlation_id=correlation_id,
                    transaction_id=transaction.transaction_id.value,
                    reserved_minor_units=transaction.change_reserve.reserved_total.minor_units,
                )
            )
        try:
            await self._validator.enable_acceptance(correlation_id=correlation_id)
        except Exception as exc:
            transaction.mark_faulted()
            self._machine_status_service.block_sales("validator_fault")
            self._fsm.transition(MachineState.FAULT, "validator_unavailable")
            self._machine_status_service.set_machine_state(self._fsm.current_state)
            self._record_outcome(
                transaction,
                action_name="acceptance_enable_requested",
                logical_step="start_cash_session.enable_acceptance",
                outcome=JournalOutcome.AMBIGUOUS,
                error=exc.__class__.__name__,
            )
            raise ValidatorUnavailableError("validator could not be enabled") from exc
        self._record_outcome(
            transaction,
            action_name="acceptance_enable_requested",
            logical_step="start_cash_session.enable_acceptance",
            outcome=JournalOutcome.SUCCEEDED,
        )
        await self._event_bus.publish(
            payment_event(
                "cash_session_started",
                correlation_id=correlation_id,
                transaction_id=transaction.transaction_id.value,
                accepted_minor_units=session.accepted_amount.minor_units,
            )
        )
        return transaction

    async def process_validator_event(self, event: BillValidatorEvent) -> Transaction | None:
        transaction = self._transaction_coordinator.active()
        correlation_id = event.correlation_id or (transaction.correlation_id.value if transaction else "machine")
        await self._event_bus.publish(
            device_event(
                event.event_type.value,
                correlation_id=correlation_id,
                transaction_id=transaction.transaction_id.value if transaction else None,
                bill_minor_units=event.bill_value.minor_units if event.bill_value else None,
                details=dict(event.details),
            )
        )
        if transaction is None:
            return None
        if transaction._cancelled:
            return None
        if event.event_type is BillValidatorEventType.VALIDATOR_FAULT:
            transaction.mark_faulted()
            self._machine_status_service.block_sales("validator_fault")
            self._fsm.transition(MachineState.FAULT, "validator_fault")
            self._machine_status_service.set_machine_state(self._fsm.current_state)
            raise ValidatorUnavailableError(f"validator fault for transaction {transaction.transaction_id.value}")
        if event.event_type is BillValidatorEventType.BILL_STACKED:
            if event.bill_value is None:
                raise ValueError("bill_stacked requires bill_value")
            transaction.record_stacked_cash(event.bill_value.minor_units)
            await self._event_bus.publish(
                payment_event(
                    "cash_amount_updated",
                    correlation_id=transaction.correlation_id.value,
                    transaction_id=transaction.transaction_id.value,
                    accepted_minor_units=transaction.accepted_amount.minor_units,
                    remaining_minor_units=max(
                        0,
                        transaction.price.minor_units - transaction.accepted_amount.minor_units,
                    ),
                )
            )
            if transaction.accepted_amount >= transaction.price:
                await self.complete_payment(transaction.transaction_id.value)
        return transaction

    async def complete_payment(self, transaction_id: str) -> Transaction:
        transaction = self._transaction_coordinator.require(transaction_id)
        with self._journal.atomic_transaction():
            transaction.confirm_payment()
            self._record_intent(
                transaction,
                action_name="acceptance_disable_requested",
                logical_step="complete_payment.disable_acceptance",
            )
        try:
            await self._validator.disable_acceptance(correlation_id=transaction.correlation_id.value)
        except Exception as exc:
            transaction.mark_ambiguous()
            self._enter_recovery_pending("validator_disable_recovery_required")
            self._record_outcome(
                transaction,
                action_name="acceptance_disable_requested",
                logical_step="complete_payment.disable_acceptance",
                outcome=JournalOutcome.AMBIGUOUS,
                error=exc.__class__.__name__,
            )
            raise
        with self._journal.atomic_transaction():
            self._record_outcome(
                transaction,
                action_name="acceptance_disable_requested",
                logical_step="complete_payment.disable_acceptance",
                outcome=JournalOutcome.SUCCEEDED,
            )
            self._fsm.transition(MachineState.PAYMENT_ACCEPTED, "payment_accepted")
            self._machine_status_service.set_machine_state(self._fsm.current_state)
        refund_dispensed = False
        try:
            await self._change_manager.finalize_reserve(transaction)
            if transaction.change_due.minor_units > 0:
                transaction.mark_change_pending()
                self._fsm.transition(MachineState.DISPENSING_CHANGE, "change_dispense_requested")
                self._machine_status_service.set_machine_state(self._fsm.current_state)
                self._record_intent(
                    transaction,
                    action_name="change_dispense_requested",
                    logical_step="complete_payment.dispense_change",
                    change_due_minor_units=transaction.change_due.minor_units,
                )
                await self._event_bus.publish(
                    payment_event(
                        "change_dispense_requested",
                        correlation_id=transaction.correlation_id.value,
                        transaction_id=transaction.transaction_id.value,
                        change_due_minor_units=transaction.change_due.minor_units,
                    )
                )
                try:
                    await self._change_manager.dispense(transaction)
                except Exception as exc:
                    self._record_outcome(
                        transaction,
                        action_name="change_dispense_requested",
                        logical_step="complete_payment.dispense_change",
                        outcome=JournalOutcome.AMBIGUOUS,
                        error=exc.__class__.__name__,
                    )
                    raise
                self._record_outcome(
                    transaction,
                    action_name="change_dispense_requested",
                    logical_step="complete_payment.dispense_change",
                    outcome=JournalOutcome.SUCCEEDED,
                    change_due_minor_units=transaction.change_due.minor_units,
                )
                await self._event_bus.publish(
                    payment_event(
                        "change_dispensed",
                        correlation_id=transaction.correlation_id.value,
                        transaction_id=transaction.transaction_id.value,
                        change_due_minor_units=transaction.change_due.minor_units,
                    )
                )
        except Exception:
            try:
                await self._change_manager.dispense_refund(
                    transaction_id=transaction.transaction_id.value,
                    correlation_id=transaction.correlation_id.value,
                    amount_minor_units=transaction.accepted_amount.minor_units,
                    currency=transaction.price.currency.code,
                )
            except Exception:
                transaction.mark_ambiguous()
                if self._fsm.can_transition(MachineState.MANUAL_REVIEW):
                    self._fsm.transition(MachineState.MANUAL_REVIEW, "change_failed_refund_failed")
                else:
                    self._fsm.force_state(MachineState.MANUAL_REVIEW, "change_failed_refund_failed")
                self._machine_status_service.set_machine_state(self._fsm.current_state)
                await self._event_bus.publish(
                    payment_event(
                        "change_failed",
                        correlation_id=transaction.correlation_id.value,
                        transaction_id=transaction.transaction_id.value,
                        change_due_minor_units=transaction.change_due.minor_units,
                    )
                )
                await self._event_bus.publish(
                    payment_event(
                        "manual_review_required",
                        correlation_id=transaction.correlation_id.value,
                        transaction_id=transaction.transaction_id.value,
                        action="change_failed",
                        reason="change payout did not complete and refund also failed; operator review required",
                    )
                )
                raise
            refund_dispensed = True
        await self._event_bus.publish(
            payment_event(
                "payment_confirmed",
                correlation_id=transaction.correlation_id.value,
                transaction_id=transaction.transaction_id.value,
                accepted_minor_units=transaction.accepted_amount.minor_units,
                change_due_minor_units=transaction.change_due.minor_units,
            )
        )
        if not refund_dispensed:
            await self._event_bus.publish(
                payment_event(
                    "vend_authorized",
                    correlation_id=transaction.correlation_id.value,
                    transaction_id=transaction.transaction_id.value,
                    slot_id=transaction.slot_id.value,
                )
            )
        return transaction

    async def cancel_purchase(self, transaction_id: str, correlation_id: str) -> Transaction:
        transaction = self._transaction_coordinator.require(transaction_id)
        with self._journal.atomic_transaction():
            self._record_intent(
                transaction,
                action_name="acceptance_disable_requested",
                logical_step="cancel_purchase.disable_acceptance",
            )
        try:
            await self._validator.disable_acceptance(correlation_id=correlation_id)
        except Exception as exc:
            transaction.mark_ambiguous()
            self._enter_recovery_pending("validator_disable_recovery_required")
            self._record_outcome(
                transaction,
                action_name="acceptance_disable_requested",
                logical_step="cancel_purchase.disable_acceptance",
                outcome=JournalOutcome.AMBIGUOUS,
                error=exc.__class__.__name__,
            )
            raise
        with self._journal.atomic_transaction():
            self._record_outcome(
                transaction,
                action_name="acceptance_disable_requested",
                logical_step="cancel_purchase.disable_acceptance",
                outcome=JournalOutcome.SUCCEEDED,
            )
        if (
            transaction.payment_status is not PaymentStatus.CONFIRMED
            and transaction.accepted_amount.minor_units > 0
        ):
            await self._refund_cancelled_cash(transaction, correlation_id)
        if transaction.change_reserve is not None:
            await self._change_manager.inventory.release(transaction.change_reserve)
            transaction.change_reserve = None
        with self._journal.atomic_transaction():
            transaction.cancel()
            self._fsm.transition(MachineState.CANCELLED, "purchase_cancelled")
            self._machine_status_service.set_machine_state(self._fsm.current_state)
            self._transaction_coordinator.clear_active(transaction_id)
            self._machine_status_service.set_active_transaction(None)
        await self._event_bus.publish(
            payment_event(
                "transaction_cancelled",
                correlation_id=correlation_id,
                transaction_id=transaction.transaction_id.value,
            )
        )
        self._transaction_coordinator.clear_active(transaction_id)
        self._machine_status_service.set_active_transaction(None)
        return transaction

    async def _refund_cancelled_cash(self, transaction: Transaction, correlation_id: str) -> None:
        if transaction.change_reserve is not None:
            await self._change_manager.inventory.release(transaction.change_reserve)
            transaction.change_reserve = None
        if self._fsm.can_transition(MachineState.REFUND):
            self._fsm.transition(MachineState.REFUND, "refund_requested")
            self._machine_status_service.set_machine_state(self._fsm.current_state)
        await self._event_bus.publish(
            payment_event(
                "refund_requested",
                correlation_id=correlation_id,
                transaction_id=transaction.transaction_id.value,
                refund_minor_units=transaction.accepted_amount.minor_units,
            )
        )
        self._record_intent(
            transaction,
            action_name="refund_dispense_requested",
            logical_step="cancel_purchase.dispense_refund",
            refund_minor_units=transaction.accepted_amount.minor_units,
        )
        try:
            await self._change_manager.dispense_refund(
                transaction_id=transaction.transaction_id.value,
                correlation_id=correlation_id,
                amount_minor_units=transaction.accepted_amount.minor_units,
                currency=transaction.price.currency.code,
            )
        except Exception:
            transaction.mark_ambiguous()
            if self._fsm.can_transition(MachineState.MANUAL_REVIEW):
                self._fsm.transition(MachineState.MANUAL_REVIEW, "refund_failed")
            else:
                self._fsm.force_state(MachineState.MANUAL_REVIEW, "refund_failed")
            self._machine_status_service.set_machine_state(self._fsm.current_state)
            self._record_outcome(
                transaction,
                action_name="refund_dispense_requested",
                logical_step="cancel_purchase.dispense_refund",
                outcome=JournalOutcome.AMBIGUOUS,
                refund_minor_units=transaction.accepted_amount.minor_units,
            )
            await self._event_bus.publish(
                payment_event(
                    "refund_failed",
                    correlation_id=correlation_id,
                    transaction_id=transaction.transaction_id.value,
                    refund_minor_units=transaction.accepted_amount.minor_units,
                )
            )
            await self._event_bus.publish(
                payment_event(
                    "manual_review_required",
                    correlation_id=correlation_id,
                    transaction_id=transaction.transaction_id.value,
                    action="refund_failed",
                    reason="refund payout did not complete; operator review required",
                )
            )
            raise
        if self._fsm.current_state is MachineState.REFUND:
            self._fsm.transition(MachineState.CANCELLED, "refund_dispensed")
            self._machine_status_service.set_machine_state(self._fsm.current_state)
        self._record_outcome(
            transaction,
            action_name="refund_dispense_requested",
            logical_step="cancel_purchase.dispense_refund",
            outcome=JournalOutcome.SUCCEEDED,
            refund_minor_units=transaction.accepted_amount.minor_units,
        )
        await self._event_bus.publish(
            payment_event(
                "refund_dispensed",
                correlation_id=correlation_id,
                transaction_id=transaction.transaction_id.value,
                refund_minor_units=transaction.accepted_amount.minor_units,
            )
        )

    def _enter_recovery_pending(self, reason: str) -> None:
        if self._fsm.can_transition(MachineState.RECOVERY_PENDING):
            self._fsm.transition(MachineState.RECOVERY_PENDING, reason)
        else:
            self._fsm.force_state(MachineState.RECOVERY_PENDING, reason)
        self._machine_status_service.set_machine_state(self._fsm.current_state)



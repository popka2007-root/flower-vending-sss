"""Pickup timeout supervision for simulator-safe delivery windows."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from flower_vending.app.event_bus import EventBus
from flower_vending.app.fsm import MachineState, StateMachineEngine
from flower_vending.app.journal import ApplicationJournal, JournalOutcome, NoopApplicationJournal
from flower_vending.app.orchestrators.transaction_coordinator import TransactionCoordinator
from flower_vending.app.services.machine_status_service import MachineStatusService
from flower_vending.devices.interfaces import WindowController
from flower_vending.domain.entities import Transaction, TransactionStatus
from flower_vending.domain.events import DomainEvent
from flower_vending.domain.events.machine_events import machine_event
from flower_vending.domain.events.vending_events import vending_event


from flower_vending.app.orchestrators.mixins import TransactionJournalingMixin

class PickupTimeoutCoordinator(TransactionJournalingMixin):
    def __init__(
        self,
        *,
        transaction_coordinator: TransactionCoordinator,
        window_controller: WindowController,
        event_bus: EventBus,
        fsm: StateMachineEngine,
        machine_status_service: MachineStatusService,
        pickup_timeout_s: float,
        journal: ApplicationJournal | None = None,
    ) -> None:
        self._transaction_coordinator = transaction_coordinator
        self._window_controller = window_controller
        self._event_bus = event_bus
        self._fsm = fsm
        self._machine_status_service = machine_status_service
        self._pickup_timeout_s = max(0.0, pickup_timeout_s)
        self._journal = journal or NoopApplicationJournal()
        self._deadlines: dict[str, datetime] = {}
        self._handling: set[str] = set()
        self._lock = asyncio.Lock()

    @property
    def pickup_timeout_s(self) -> float:
        return self._pickup_timeout_s

    async def handle_delivery_window_opened(self, event: DomainEvent) -> None:
        if event.transaction_id is None:
            return
        async with self._lock:
            transaction = self._transaction_coordinator.get(event.transaction_id)
            if transaction is None:
                return
            self._arm_waiting_transaction(transaction)

    async def handle_pickup_finished(self, event: DomainEvent) -> None:
        if event.transaction_id is None:
            return
        async with self._lock:
            self._deadlines.pop(event.transaction_id, None)

    async def poll_once(self, *, correlation_id: str = "pickup-timeout-supervisor") -> None:
        expired = await self._collect_expired(correlation_id=correlation_id)
        for transaction_id, timeout_correlation_id in expired:
            await self._handle_timeout(
                transaction_id,
                correlation_id=timeout_correlation_id,
                forced=False,
            )

    async def force_timeout_now(self, *, correlation_id: str) -> str:
        async with self._lock:
            transaction = self._first_waiting_transaction()
            if transaction is None:
                raise RuntimeError("no transaction is waiting for customer pickup")
            transaction_id = transaction.transaction_id.value
        await self._handle_timeout(transaction_id, correlation_id=correlation_id, forced=True)
        return transaction_id

    def deadline_for(self, transaction_id: str) -> datetime | None:
        return self._deadlines.get(transaction_id)

    def remaining_seconds(self, transaction_id: str) -> float | None:
        deadline = self.deadline_for(transaction_id)
        if deadline is None:
            return None
        remaining = (deadline - self._now()).total_seconds()
        return max(0.0, remaining)

    async def _collect_expired(self, *, correlation_id: str) -> list[tuple[str, str]]:
        now = self._now()
        expired: list[tuple[str, str]] = []
        async with self._lock:
            self._sync_waiting_transactions()
            for transaction_id, deadline in list(self._deadlines.items()):
                if deadline > now or transaction_id in self._handling:
                    continue
                transaction = self._transaction_coordinator.get(transaction_id)
                expired.append(
                    (
                        transaction_id,
                        transaction.correlation_id.value if transaction is not None else correlation_id,
                    )
                )
        return expired

    async def _handle_timeout(self, transaction_id: str, *, correlation_id: str, forced: bool) -> None:
        async with self._lock:
            if transaction_id in self._handling:
                return
            self._deadlines.pop(transaction_id, None)
            self._handling.add(transaction_id)
        try:
            transaction = self._transaction_coordinator.get(transaction_id)
            if transaction is None or transaction.status is not TransactionStatus.WAITING_FOR_CUSTOMER_PICKUP:
                return
            await self._event_bus.publish(
                vending_event(
                    "pickup_timeout_elapsed",
                    correlation_id=correlation_id,
                    transaction_id=transaction.transaction_id.value,
                    timeout_s=self._pickup_timeout_s,
                    forced=forced,
                    deadline_at=self._deadline_for_transaction(transaction).isoformat(),
                )
            )
            if self._fsm.current_state == MachineState.WAITING_FOR_CUSTOMER_PICKUP:
                self._fsm.transition(MachineState.CLOSING_DELIVERY_WINDOW, "pickup_timeout_elapsed")
                self._machine_status_service.set_machine_state(self._fsm.current_state)
            self._record_intent(
                transaction,
                action_name="window_close_requested",
                logical_step="pickup_timeout.close_window",
                forced=forced,
            )
            try:
                await self._window_controller.close_window(correlation_id=correlation_id)
            except Exception as exc:
                transaction.mark_faulted()
                self._record_outcome(
                    transaction,
                    action_name="window_close_requested",
                    logical_step="pickup_timeout.close_window",
                    outcome=JournalOutcome.AMBIGUOUS,
                    forced=forced,
                    error=exc.__class__.__name__,
                )
                if self._fsm.can_transition(MachineState.FAULT):
                    self._fsm.transition(MachineState.FAULT, "pickup_timeout_window_close_failed")
                else:
                    self._fsm.force_state(MachineState.FAULT, "pickup_timeout_window_close_failed")
                self._machine_status_service.set_machine_state(self._fsm.current_state)
                self._machine_status_service.block_sales("delivery_window_fault")
                await self._event_bus.publish(
                    vending_event(
                        "pickup_timeout_window_close_failed",
                        correlation_id=correlation_id,
                        transaction_id=transaction.transaction_id.value,
                        error=exc.__class__.__name__,
                    )
                )
                await self._event_bus.publish(
                    machine_event(
                        "machine_faulted",
                        correlation_id=correlation_id,
                        faults=("delivery_window_fault",),
                        transaction_id=transaction.transaction_id.value,
                    )
                )
                return
            self._record_outcome(
                transaction,
                action_name="window_close_requested",
                logical_step="pickup_timeout.close_window",
                outcome=JournalOutcome.SUCCEEDED,
                forced=forced,
            )
            transaction.mark_pickup_timed_out_window_closed()
            if self._fsm.current_state == MachineState.CLOSING_DELIVERY_WINDOW:
                self._fsm.transition(MachineState.RECOVERY_PENDING, "pickup_timeout_manual_review_required")
            elif self._fsm.can_transition(MachineState.RECOVERY_PENDING):
                self._fsm.transition(MachineState.RECOVERY_PENDING, "pickup_timeout_manual_review_required")
            else:
                self._fsm.force_state(MachineState.RECOVERY_PENDING, "pickup_timeout_manual_review_required")
            self._machine_status_service.set_machine_state(self._fsm.current_state)
            self._machine_status_service.block_sales("recovery_pending")
            await self._event_bus.publish(
                vending_event(
                    "pickup_timeout_window_closed",
                    correlation_id=correlation_id,
                    transaction_id=transaction.transaction_id.value,
                )
            )
            await self._event_bus.publish(
                machine_event(
                    "manual_review_required",
                    correlation_id=correlation_id,
                    transaction_id=transaction.transaction_id.value,
                    action="pickup_timeout",
                    reason="pickup_not_confirmed_before_deadline",
                )
            )
        finally:
            async with self._lock:
                self._handling.discard(transaction_id)
                self._deadlines.pop(transaction_id, None)

    def _sync_waiting_transactions(self) -> None:
        waiting_ids: set[str] = set()
        active = self._transaction_coordinator.active()
        candidates = [*self._transaction_coordinator.unresolved_transactions()]
        if active is not None and active not in candidates:
            candidates.append(active)
        for transaction in candidates:
            if transaction.status is not TransactionStatus.WAITING_FOR_CUSTOMER_PICKUP:
                continue
            waiting_ids.add(transaction.transaction_id.value)
            self._arm_waiting_transaction(transaction)
        for transaction_id in tuple(self._deadlines):
            if transaction_id not in waiting_ids:
                self._deadlines.pop(transaction_id, None)

    def _arm_waiting_transaction(self, transaction: Transaction) -> None:
        if transaction.status is not TransactionStatus.WAITING_FOR_CUSTOMER_PICKUP:
            self._deadlines.pop(transaction.transaction_id.value, None)
            return
        self._deadlines.setdefault(
            transaction.transaction_id.value,
            self._deadline_for_transaction(transaction),
        )

    def _first_waiting_transaction(self) -> Transaction | None:
        active = self._transaction_coordinator.active()
        if active is not None and active.status is TransactionStatus.WAITING_FOR_CUSTOMER_PICKUP:
            return active
        for transaction in self._transaction_coordinator.unresolved_transactions():
            if transaction.status is TransactionStatus.WAITING_FOR_CUSTOMER_PICKUP:
                return transaction
        return None

    def _deadline_for_transaction(self, transaction: Transaction) -> datetime:
        return transaction.updated_at + timedelta(seconds=self._pickup_timeout_s)

    def _now(self) -> datetime:
        return datetime.now(tz=timezone.utc)

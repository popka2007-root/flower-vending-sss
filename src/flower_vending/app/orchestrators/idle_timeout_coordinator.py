"""Idle-timeout supervision for abandoned customer sessions."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from flower_vending.app.event_bus import EventBus
from flower_vending.app.fsm import MachineState, StateMachineEngine
from flower_vending.app.journal import ApplicationJournal, NoopApplicationJournal
from flower_vending.app.orchestrators.payment_coordinator import PaymentCoordinator
from flower_vending.app.orchestrators.transaction_coordinator import TransactionCoordinator
from flower_vending.app.services.machine_status_service import MachineStatusService
from flower_vending.domain.entities import PaymentStatus, TransactionStatus
from flower_vending.domain.events.machine_events import machine_event


_logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


class IdleTimeoutCoordinator:
    def __init__(
        self,
        *,
        payment_coordinator: PaymentCoordinator,
        transaction_coordinator: TransactionCoordinator,
        event_bus: EventBus,
        fsm: StateMachineEngine,
        machine_status_service: MachineStatusService,
        idle_timeout_s: float = 120.0,
        journal: ApplicationJournal | None = None,
    ) -> None:
        self._payment_coordinator = payment_coordinator
        self._transaction_coordinator = transaction_coordinator
        self._event_bus = event_bus
        self._fsm = fsm
        self._machine_status_service = machine_status_service
        self._idle_timeout_s = max(0.0, idle_timeout_s)
        self._journal = journal or NoopApplicationJournal()
        self._last_activity_at: datetime | None = None
        self._active_transaction_id: str | None = None

    @property
    def timeout_s(self) -> float:
        return self._idle_timeout_s

    def touch(self, transaction_id: str | None = None) -> None:
        self._last_activity_at = _utc_now()
        if transaction_id is not None:
            self._active_transaction_id = transaction_id
        else:
            active = self._transaction_coordinator.active()
            self._active_transaction_id = active.transaction_id.value if active is not None else None

    async def poll_once(self, *, correlation_id: str = "idle-timeout-supervisor") -> None:
        if self._idle_timeout_s <= 0:
            return
        if self._last_activity_at is None:
            return
        elapsed = (_utc_now() - self._last_activity_at).total_seconds()
        if elapsed < self._idle_timeout_s:
            return

        tx_id: str | None = None
        active = self._transaction_coordinator.active()
        if active is not None and active.payment_status is not PaymentStatus.CONFIRMED:
            cancelable_states = {
                TransactionStatus.CREATED,
                TransactionStatus.CHECKING_AVAILABILITY,
                TransactionStatus.CHECKING_CHANGE,
                TransactionStatus.WAITING_FOR_PAYMENT,
                TransactionStatus.ACCEPTING_CASH,
            }
            if active.status in cancelable_states:
                tx_id = active.transaction_id.value

        if tx_id is None:
            if self._active_transaction_id is not None:
                tx_id = self._active_transaction_id
            else:
                self._last_activity_at = None
                return

        _logger.warning(
            "idle_timeout_triggered",
            extra={"transaction_id": tx_id, "elapsed_s": elapsed},
        )
        try:
            await self._payment_coordinator.cancel_purchase(
                transaction_id=tx_id,
                correlation_id=correlation_id,
            )
        except Exception as exc:
            _logger.error(
                "idle_timeout_cancel_failed",
                extra={"transaction_id": tx_id, "error": str(exc)},
            )
            return

        if self._fsm.current_state not in {MachineState.IDLE, MachineState.CANCELLED}:
            self._fsm.force_state(MachineState.IDLE, "idle_timeout_cancelled")
            self._machine_status_service.set_machine_state(self._fsm.current_state)

        await self._event_bus.publish(
            machine_event(
                "idle_timeout_elapsed",
                correlation_id=correlation_id,
                transaction_id=tx_id,
                elapsed_s=elapsed,
            )
        )
        self._last_activity_at = None

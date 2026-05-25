from __future__ import annotations

import unittest
from collections.abc import Callable

from tests._support import make_temp_simulator_runtime, workspace_temp_dir

from flower_vending.app.fsm import MachineState
from flower_vending.domain.commands.purchase_commands import StartPurchase
from flower_vending.domain.entities import (
    DeliveryStatus,
    DispenseStatus,
    PaymentSession,
    PaymentStatus,
    PayoutStatus,
    RecoveryStatus,
    Transaction,
    TransactionStatus,
)
from flower_vending.domain.value_objects import Amount
from flower_vending.runtime.bootstrap import SimulatorRuntimeEnvironment


CrashSeeder = Callable[[SimulatorRuntimeEnvironment, Transaction], None]
RestartAssertion = Callable[[SimulatorRuntimeEnvironment, str], None]


_SIMPLE_SEEDS: list[tuple[str, CrashSeeder]] = [
    (
        "cash_accepted_payment_not_complete",
        lambda _env, tx: _seed_cash_accepted(tx),
    ),
    (
        "payment_confirmed_change_pending",
        lambda _env, tx: _seed_change_pending(tx),
    ),
    (
        "window_opened_pickup_not_confirmed",
        lambda _env, tx: _seed_window_opened(tx),
    ),
]

_INTENT_SEEDS: list[tuple[str, CrashSeeder, RestartAssertion]] = [
    (
        "change_intent_without_outcome",
        lambda env, tx: _seed_change_intent(env, tx),
        lambda env, tid: _assert_manual_review(env, tid, 1),
    ),
    (
        "vend_motor_intent_without_outcome",
        lambda env, tx: _seed_motor_intent(env, tx),
        lambda env, tid: _assert_manual_review(env, tid, 1),
    ),
    (
        "recovery_pending_transaction",
        lambda _env, tx: _seed_recovery_pending(tx),
        lambda env, tid: _assert_recovery_pending(env, tid),
    ),
]


def _seed_cash_accepted(tx: Transaction) -> None:
    session = PaymentSession(transaction_id=tx.transaction_id.value)
    session.start_acceptance()
    session.add_stacked_bill(100)
    tx.attach_payment_session(session)
    tx.accepted_amount = session.accepted_amount
    tx.status = TransactionStatus.ACCEPTING_CASH
    tx.payment_status = PaymentStatus.ACCEPTING


def _seed_change_pending(tx: Transaction) -> None:
    tx.accepted_amount = Amount(tx.price.minor_units + 100, tx.price.currency)
    tx.change_due = Amount(100, tx.price.currency)
    tx.status = TransactionStatus.DISPENSING_CHANGE
    tx.payment_status = PaymentStatus.CONFIRMED
    tx.payout_status = PayoutStatus.PENDING


def _seed_window_opened(tx: Transaction) -> None:
    tx.accepted_amount = tx.price
    tx.change_due = Amount.zero()
    tx.status = TransactionStatus.WAITING_FOR_CUSTOMER_PICKUP
    tx.payment_status = PaymentStatus.CONFIRMED
    tx.payout_status = PayoutStatus.NOT_REQUIRED
    tx.dispense_status = DispenseStatus.DISPENSED
    tx.delivery_status = DeliveryStatus.WINDOW_OPENED


def _seed_change_intent(env: SimulatorRuntimeEnvironment, tx: Transaction) -> None:
    _seed_change_pending(tx)
    env.repositories.journal.record_intent(
        action_name="change_dispense_requested",
        correlation_id=tx.correlation_id.value,
        transaction_id=tx.transaction_id.value,
        logical_step="complete_payment.dispense_change",
        machine_state=MachineState.DISPENSING_CHANGE.value,
        transaction_status=tx.status.value,
        payload={"change_due_minor_units": tx.change_due.minor_units},
    )


def _seed_motor_intent(env: SimulatorRuntimeEnvironment, tx: Transaction) -> None:
    tx.accepted_amount = tx.price
    tx.change_due = Amount.zero()
    tx.status = TransactionStatus.DISPENSING_PRODUCT
    tx.payment_status = PaymentStatus.CONFIRMED
    tx.payout_status = PayoutStatus.NOT_REQUIRED
    tx.dispense_status = DispenseStatus.AUTHORIZED
    env.repositories.journal.record_intent(
        action_name="motor_vend_requested",
        correlation_id=tx.correlation_id.value,
        transaction_id=tx.transaction_id.value,
        logical_step="handle_vend_authorized.vend_motor",
        machine_state=MachineState.DISPENSING_PRODUCT.value,
        transaction_status=tx.status.value,
        payload={"slot_id": tx.slot_id.value},
    )


def _seed_recovery_pending(tx: Transaction) -> None:
    tx.accepted_amount = tx.price
    tx.change_due = Amount.zero()
    tx.status = TransactionStatus.AMBIGUOUS
    tx.payment_status = PaymentStatus.CONFIRMED
    tx.recovery_status = RecoveryStatus.PENDING


def _assert_manual_review(env: SimulatorRuntimeEnvironment, tid: str, expected_intents: int) -> None:
    tx = env.core.transaction_coordinator.require(tid)
    assert tx.status == TransactionStatus.AMBIGUOUS
    assert tx.recovery_status == RecoveryStatus.MANUAL_REVIEW
    assert len(env.repositories.journal.unresolved_intents()) == expected_intents


def _assert_recovery_pending(env: SimulatorRuntimeEnvironment, tid: str) -> None:
    tx = env.core.transaction_coordinator.require(tid)
    assert tx.recovery_status == RecoveryStatus.PENDING


class CrashRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_restart_blocks_sales(self) -> None:
        for label, seed in _SIMPLE_SEEDS:
            with self.subTest(scenario=label):
                await self._run_restart_test(seed, None)

    async def test_restart_intent_requires_review(self) -> None:
        for label, seed, extra in _INTENT_SEEDS:
            with self.subTest(scenario=label):
                await self._run_restart_test(seed, extra)

    async def _run_restart_test(
        self, seed: CrashSeeder, extra: RestartAssertion | None
    ) -> None:
        with workspace_temp_dir(prefix="restart-crash-") as tmp:
            runtime = make_temp_simulator_runtime(tmp)
            env = await runtime.build()
            await env.start()
            try:
                tid = await _start_transaction(env)
                tx = env.core.transaction_coordinator.require(tid)
                seed(env, tx)
                tx.touch()
                env.repositories.transactions.save(tx)
            finally:
                await env.stop()

            restarted = await runtime.build()
            await restarted.start()
            try:
                _assert_recovery_state(restarted, tid)
                if extra is not None:
                    extra(restarted, tid)
            finally:
                await restarted.stop()


async def _start_transaction(env: SimulatorRuntimeEnvironment) -> str:
    item = env.config.catalog.items[0]
    tid = await env.core.command_bus.dispatch(
        StartPurchase(
            correlation_id="restart-crash-window",
            product_id=item.product_id,
            slot_id=item.slot_id,
            price_minor_units=item.price_minor_units,
            currency=env.config.machine.currency,
        )
    )
    env.repositories.transactions.save(env.core.transaction_coordinator.require(tid))
    return tid


def _assert_recovery_state(env: SimulatorRuntimeEnvironment, tid: str) -> None:
    report = env.diagnostics_report()
    machine = report["machine"]
    assert machine["machine_state"] in {MachineState.RECOVERY_PENDING.value, MachineState.OUT_OF_SERVICE.value}
    assert "recovery_pending" in machine["sale_blockers"]
    assert machine["active_transaction_id"] == tid
    assert tid in report["unresolved_transaction_ids"]
    assert not machine["allow_cash_sales"]
    assert not machine["allow_vending"]

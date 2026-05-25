from __future__ import annotations

import unittest
from pathlib import Path

import yaml

from tests._support import ROOT, workspace_temp_dir

from flower_vending.app.journal import JournalOutcome
from flower_vending.domain.commands.purchase_commands import StartPurchase
from flower_vending.domain.entities import RecoveryStatus, TransactionStatus
from flower_vending.domain.events.payment_events import payment_event
from flower_vending.domain.exceptions import SaleBlockedError
from flower_vending.infrastructure.persistence.journal import SQLiteTransactionJournal
from flower_vending.infrastructure.persistence.sqlite import (
    SQLiteDatabase,
    TransactionRepository,
    ensure_sqlite_schema,
)
from flower_vending.runtime.bootstrap import build_simulator_environment
from flower_vending.simulators.faults import SimulatorFaultCode
from flower_vending.simulators.harness import SimulationHarness


def _make_temp_config(tmp: Path) -> Path:
    payload = yaml.safe_load(
        (ROOT / "config" / "examples" / "machine.simulator.yaml").read_text(encoding="utf-8")
    )
    payload["persistence"]["sqlite_path"] = str(tmp / "runtime.db")
    payload["logging"]["directory"] = str(tmp / "log")
    path = tmp / "runtime.yaml"
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


class RecoveryAndPersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_reboot_mid_transaction_leaves_durable_recovery_evidence(self) -> None:
        with workspace_temp_dir(prefix="recovery-") as tmp:
            db_path = tmp / "recovery.db"

            harness = SimulationHarness.build()
            await harness.start()
            try:
                transaction_id = await harness.start_purchase(
                    correlation_id="reboot-mid-transaction"
                )
                transaction = harness.core.transaction_coordinator.require(transaction_id)
                transaction.status = TransactionStatus.WAITING_FOR_PAYMENT

                db = SQLiteDatabase(db_path)
                try:
                    ensure_sqlite_schema(db)
                    transaction_repo = TransactionRepository(db)
                    journal = SQLiteTransactionJournal(db)
                    transaction_repo.save(transaction)
                    journal.append_intent(
                        intent_name="start_purchase",
                        correlation_id="reboot-mid-transaction",
                        transaction_id=transaction_id,
                        machine_state="WAITING_FOR_PAYMENT",
                        transaction_status=transaction.status.value,
                        product_id=transaction.product_id.value,
                        slot_id=transaction.slot_id.value,
                    )
                    journal.append_event(
                        payment_event(
                            "purchase_started",
                            correlation_id="reboot-mid-transaction",
                            transaction_id=transaction_id,
                            product_id=transaction.product_id.value,
                            slot_id=transaction.slot_id.value,
                        ),
                        machine_state="WAITING_FOR_PAYMENT",
                        transaction_status=transaction.status.value,
                    )
                finally:
                    db.close()
            finally:
                await harness.stop()

            rebooted_db = SQLiteDatabase(db_path)
            try:
                transaction_repo = TransactionRepository(rebooted_db)
                journal = SQLiteTransactionJournal(rebooted_db)
                loaded_transaction = transaction_repo.get(transaction_id)
                self.assertIsNotNone(loaded_transaction)
                assert loaded_transaction is not None
                self.assertEqual(loaded_transaction.status.value, "waiting_for_payment")
                self.assertIn(transaction_id, journal.unresolved_transaction_ids())
                self.assertEqual(len(journal.read_for_transaction(transaction_id)), 2)
            finally:
                rebooted_db.close()

    async def test_sqlite_journal_reports_intent_without_outcome(self) -> None:
        with workspace_temp_dir(prefix="intent-journal-") as tmp:
            db = SQLiteDatabase(tmp / "intent.db")
            try:
                ensure_sqlite_schema(db)
                harness = SimulationHarness.build()
                await harness.start()
                try:
                    transaction_id = await harness.start_purchase(correlation_id="intent-only")
                    transaction = harness.core.transaction_coordinator.require(transaction_id)
                    TransactionRepository(db).save(transaction)
                    journal = SQLiteTransactionJournal(db)

                    intent_row_id = journal.record_intent(
                        action_name="motor_vend_requested",
                        correlation_id="intent-only",
                        transaction_id=transaction_id,
                        logical_step="handle_vend_authorized.vend_motor",
                        machine_state="DISPENSING_PRODUCT",
                        transaction_status="dispensing_product",
                        payload={"slot_id": transaction.slot_id.value},
                    )

                    unresolved = journal.unresolved_intents()
                    self.assertEqual(len(unresolved), 1)
                    self.assertEqual(unresolved[0].entry_name, "motor_vend_requested")
                    self.assertIn(transaction_id, unresolved[0].idempotency_key or "")
                    self.assertIn(
                        "handle_vend_authorized.vend_motor", unresolved[0].idempotency_key or ""
                    )
                    self.assertGreater(intent_row_id, 0)

                    journal.record_outcome(
                        action_name="motor_vend_requested",
                        outcome=JournalOutcome.SUCCEEDED,
                        correlation_id="intent-only",
                        transaction_id=transaction_id,
                        logical_step="handle_vend_authorized.vend_motor",
                        machine_state="OPENING_DELIVERY_WINDOW",
                        transaction_status="opening_delivery_window",
                        payload={"slot_id": transaction.slot_id.value},
                    )

                    self.assertEqual(journal.unresolved_intents(), ())
                finally:
                    await harness.stop()
            finally:
                db.close()

    async def test_restart_blocks_sales_when_intent_has_no_outcome(self) -> None:
        with workspace_temp_dir(prefix="intent-restart-") as tmp:
            config_path = _make_temp_config(tmp)
            environment = await build_simulator_environment(
                config_path=config_path,
                prepare_directories=True,
            )
            await environment.start()
            try:
                item = environment.config.catalog.items[0]
                transaction_id = await environment.core.command_bus.dispatch(
                    StartPurchase(
                        correlation_id="intent-restart",
                        product_id=item.product_id,
                        slot_id=item.slot_id,
                        price_minor_units=item.price_minor_units,
                        currency=environment.config.machine.currency,
                    )
                )
                transaction = environment.core.transaction_coordinator.require(transaction_id)
                transaction.status = TransactionStatus.COMPLETED
                transaction.recovery_status = RecoveryStatus.NONE
                environment.repositories.transactions.save(transaction)
                environment.repositories.journal.record_intent(
                    action_name="motor_vend_requested",
                    correlation_id="intent-restart",
                    transaction_id=transaction_id,
                    logical_step="handle_vend_authorized.vend_motor",
                    machine_state="DISPENSING_PRODUCT",
                    transaction_status="dispensing_product",
                    payload={"slot_id": transaction.slot_id.value},
                )
            finally:
                await environment.stop()

            restarted = await build_simulator_environment(
                config_path=config_path,
                prepare_directories=True,
            )
            await restarted.start()
            try:
                transaction = restarted.core.transaction_coordinator.require(transaction_id)
                self.assertEqual(restarted.core.fsm.current_state.value, "RECOVERY_PENDING")
                self.assertIn(
                    "recovery_pending",
                    restarted.core.machine_status_service.runtime.status.sale_blockers,
                )
                self.assertEqual(transaction.status.value, "ambiguous")
                self.assertEqual(transaction.recovery_status, RecoveryStatus.MANUAL_REVIEW)
                self.assertEqual(len(restarted.repositories.journal.unresolved_intents()), 1)
                item = restarted.config.catalog.items[0]
                with self.assertRaises(SaleBlockedError):
                    await restarted.core.command_bus.dispatch(
                        StartPurchase(
                            correlation_id="blocked-after-restart",
                            product_id=item.product_id,
                            slot_id=item.slot_id,
                            price_minor_units=item.price_minor_units,
                            currency=restarted.config.machine.currency,
                        )
                    )
            finally:
                await restarted.stop()

    async def test_recovery_manager_marks_partial_payout_for_manual_review(self) -> None:
        harness = SimulationHarness.build(
            price_minor_units=300,
            change_inventory={100: 2},
            accepted_bill_denominations=(500,),
        )
        await harness.start()
        try:
            transaction_id = await harness.start_purchase(correlation_id="recovery-partial")
            await harness.accept_cash(transaction_id, correlation_id="recovery-partial")
            harness.change_dispenser.inject_fault(
                SimulatorFaultCode.PARTIAL_PAYOUT,
                message="simulated partial payout",
            )
            with self.assertRaises(Exception):
                await harness.insert_bill(500, correlation_id="recovery-partial")

            transaction = harness.core.transaction_coordinator.require(transaction_id)
            plan = harness.core.recovery_manager.assess(transaction)
            self.assertEqual(plan.action, "manual_review")
            self.assertTrue(plan.operator_required)
            self.assertEqual(plan.reason, "ambiguous_side_effect")
        finally:
            await harness.stop()


if __name__ == "__main__":
    unittest.main()

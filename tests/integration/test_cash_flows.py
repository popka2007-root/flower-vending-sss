from __future__ import annotations

import unittest

from tests._support import AsyncHarnessTestCase

from flower_vending.devices.exceptions import DeviceAdapterError
from flower_vending.domain.commands.purchase_commands import CancelPurchase
from flower_vending.domain.entities.transaction import TransactionStatus
from flower_vending.domain.exceptions import ChangeUnavailableError, SaleBlockedError
from flower_vending.simulators.faults import SimulatorFaultCode


class CashFlowIntegrationTests(AsyncHarnessTestCase):
    async def test_exact_change_only_flag_is_set_when_safe_change_is_unavailable(self) -> None:
        harness = await self.create_harness(
            price_minor_units=300,
            change_inventory={100: 1},
            accepted_bill_denominations=(500,),
        )

        transaction_id = await harness.start_purchase(correlation_id="exact-change")
        with self.assertRaises(ChangeUnavailableError):
            await harness.accept_cash(transaction_id, correlation_id="exact-change")

        status = harness.core.machine_status_service.runtime.status
        self.assertTrue(status.exact_change_only)
        self.assertEqual(status.machine_state, "WAITING_FOR_PAYMENT")

    async def test_multi_note_overpay_is_blocked_when_change_cannot_be_guaranteed(self) -> None:
        harness = await self.create_harness(
            price_minor_units=300,
            change_inventory={100: 2},
            accepted_bill_denominations=(100, 500),
        )

        transaction_id = await harness.start_purchase(correlation_id="multi-note-overpay")
        with self.assertRaises(ChangeUnavailableError):
            await harness.accept_cash(transaction_id, correlation_id="multi-note-overpay")

        status = harness.core.machine_status_service.runtime.status
        self.assertTrue(status.exact_change_only)
        self.assertEqual(status.machine_state, "WAITING_FOR_PAYMENT")

    async def test_payment_cancelled_returns_machine_to_idle(self) -> None:
        harness = await self.create_harness()

        transaction_id = await harness.start_purchase(correlation_id="cancel")
        await harness.accept_cash(transaction_id, correlation_id="cancel")
        await harness.core.command_bus.dispatch(
            CancelPurchase(correlation_id="cancel", transaction_id=transaction_id)
        )

        transaction = harness.core.transaction_coordinator.require(transaction_id)
        self.assertEqual(transaction.status, TransactionStatus.CANCELLED)
        self.assertEqual(harness.core.fsm.current_state.value, "IDLE")
        self.assertIsNone(harness.core.transaction_coordinator.active())

    async def test_payment_cancelled_after_cash_refunds_before_cancel(self) -> None:
        harness = await self.create_harness(
            price_minor_units=300,
            change_inventory={100: 5},
            accepted_bill_denominations=(100, 500),
        )

        transaction_id = await harness.start_purchase(correlation_id="cancel-after-cash")
        await harness.accept_cash(transaction_id, correlation_id="cancel-after-cash")
        await harness.insert_bill(100, correlation_id="cancel-after-cash")
        await harness.core.command_bus.dispatch(
            CancelPurchase(correlation_id="cancel-after-cash", transaction_id=transaction_id)
        )

        transaction = harness.core.transaction_coordinator.require(transaction_id)
        inventory = harness.money_inventory.accounting_counts_by_denomination
        self.assertEqual(transaction.status, TransactionStatus.CANCELLED)
        self.assertIn("refund_dispensed", harness.recorder.event_types)
        self.assertEqual(inventory[100], 4)
        self.assertEqual(harness.core.fsm.current_state.value, "IDLE")

    async def test_bill_rejected_does_not_increment_accepted_amount(self) -> None:
        harness = await self.create_harness()

        transaction_id = await harness.start_purchase(correlation_id="bill-rejected")
        await harness.accept_cash(transaction_id, correlation_id="bill-rejected")
        harness.validator.inject_fault(
            SimulatorFaultCode.BILL_REJECTED,
            message="simulated bill rejection",
            critical=False,
        )

        await harness.insert_bill(500, correlation_id="bill-rejected")

        transaction = harness.core.transaction_coordinator.require(transaction_id)
        self.assertEqual(transaction.accepted_amount.minor_units, 0)
        self.assertEqual(transaction.status.value, "accepting_cash")
        self.assertIn("bill_rejected", harness.recorder.event_types)

    async def test_partial_payout_transitions_to_manual_review(self) -> None:
        harness = await self.create_harness(
            price_minor_units=300,
            change_inventory={100: 2},
            accepted_bill_denominations=(500,),
        )

        transaction_id = await harness.start_purchase(correlation_id="partial-payout")
        await harness.accept_cash(transaction_id, correlation_id="partial-payout")
        harness.change_dispenser.inject_fault(
            SimulatorFaultCode.PARTIAL_PAYOUT,
            message="simulated partial payout",
        )

        with self.assertRaises(ChangeUnavailableError):
            await harness.insert_bill(500, correlation_id="partial-payout")

        transaction = harness.core.transaction_coordinator.require(transaction_id)
        self.assertEqual(transaction.status.value, "ambiguous")
        self.assertEqual(harness.core.fsm.current_state.value, "MANUAL_REVIEW")
        self.assertIn("change_failed", harness.recorder.event_types)
        self.assertIn("manual_review_required", harness.recorder.event_types)

    async def test_motor_fault_transitions_to_fault(self) -> None:
        harness = await self.create_harness()

        transaction_id = await harness.start_purchase(correlation_id="motor-fault")
        await harness.accept_cash(transaction_id, correlation_id="motor-fault")
        harness.motor_controller.inject_fault(
            SimulatorFaultCode.MOTOR_FAULT,
            message="simulated vend motor fault",
        )

        with self.assertRaises(DeviceAdapterError):
            await harness.insert_bill(500, correlation_id="motor-fault")

        transaction = harness.core.transaction_coordinator.require(transaction_id)
        self.assertEqual(transaction.status.value, "faulted")
        self.assertEqual(harness.core.fsm.current_state.value, "FAULT")
        self.assertEqual(harness.motor_controller.vend_history, [])

    async def test_service_door_open_blocks_sale(self) -> None:
        harness = await self.create_harness(service_door_open=True)

        with self.assertRaises(SaleBlockedError):
            await harness.start_purchase(correlation_id="door-open")

        self.assertIn("service_door_open", harness.core.machine_status_service.runtime.status.sale_blockers)

    async def test_critical_temperature_blocks_sale(self) -> None:
        harness = await self.create_harness(temperature_celsius=9.5)

        with self.assertRaises(SaleBlockedError):
            await harness.start_purchase(correlation_id="critical-temp")

        self.assertIn("critical_temperature", harness.core.machine_status_service.runtime.status.sale_blockers)


if __name__ == "__main__":
    unittest.main()

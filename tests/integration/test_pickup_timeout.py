from __future__ import annotations

import unittest

from flower_vending.app.fsm import MachineState
from flower_vending.devices.contracts import WindowPosition
from flower_vending.domain.entities import TransactionStatus
from flower_vending.simulators.faults import SimulatorFaultCode
from flower_vending.simulators.harness import SimulationHarness
from flower_vending.simulators.scenarios.customer_flows import run_pickup_timeout_scenario


class PickupTimeoutIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_pickup_timeout_closes_window_in_simulator(self) -> None:
        harness = SimulationHarness.build(pickup_timeout_s=0.05)
        await harness.start()
        try:
            transaction_id = await harness.start_purchase(correlation_id="pickup_timeout")
            await harness.accept_cash(transaction_id, correlation_id="pickup_timeout")
            await harness.insert_bill(500, correlation_id="pickup_timeout")
            await harness.wait_for_runtime_processing(timeout_s=0.2)

            transaction = harness.core.transaction_coordinator.require(transaction_id)
            window_status = await harness.window_controller.get_window_status()

            self.assertEqual(window_status.position, WindowPosition.CLOSED)
            self.assertEqual(harness.core.fsm.current_state, MachineState.RECOVERY_PENDING)
            self.assertEqual(transaction.status, TransactionStatus.PICKUP_TIMED_OUT)
            self.assertIn("pickup_timeout_elapsed", harness.recorder.event_types)
            self.assertIn("pickup_timeout_window_closed", harness.recorder.event_types)
        finally:
            await harness.stop()

    async def test_confirm_pickup_cancels_timeout(self) -> None:
        harness = SimulationHarness.build(pickup_timeout_s=2.0)
        await harness.start()
        try:
            transaction_id = await harness.start_purchase(correlation_id="confirm_pickup")
            await harness.accept_cash(transaction_id, correlation_id="confirm_pickup")
            await harness.insert_bill(500, correlation_id="confirm_pickup")
            await harness.confirm_pickup(transaction_id, correlation_id="confirm_pickup")
            await harness.wait_for_runtime_processing(timeout_s=0.15)

            transaction = harness.core.transaction_coordinator.require(transaction_id)
            window_status = await harness.window_controller.get_window_status()

            self.assertEqual(window_status.position, WindowPosition.CLOSED)
            self.assertEqual(harness.core.fsm.current_state, MachineState.IDLE)
            self.assertEqual(transaction.status, TransactionStatus.COMPLETED)
            self.assertNotIn("pickup_timeout_elapsed", harness.recorder.event_types)
            self.assertIsNone(harness.core.pickup_timeout_coordinator.deadline_for(transaction_id))
        finally:
            await harness.stop()

    async def test_window_close_failure_faults_transaction(self) -> None:
        harness = SimulationHarness.build(pickup_timeout_s=2.0)
        await harness.start()
        try:
            transaction_id = await harness.start_purchase(correlation_id="window_fault")
            await harness.accept_cash(transaction_id, correlation_id="window_fault")
            await harness.insert_bill(500, correlation_id="window_fault")
            harness.window_controller.inject_fault(
                SimulatorFaultCode.WINDOW_FAULT,
                message="close failed",
            )

            await harness.core.pickup_timeout_coordinator.force_timeout_now(
                correlation_id="window_fault"
            )

            transaction = harness.core.transaction_coordinator.require(transaction_id)
            window_status = await harness.window_controller.get_window_status()

            self.assertEqual(window_status.position, WindowPosition.OPEN)
            self.assertEqual(harness.core.fsm.current_state, MachineState.FAULT)
            self.assertEqual(transaction.status, TransactionStatus.FAULTED)
            self.assertIn("pickup_timeout_window_close_failed", harness.recorder.event_types)
        finally:
            await harness.stop()

    async def test_restart_during_waiting_for_pickup_preserves_timeout_need(self) -> None:
        first = SimulationHarness.build(pickup_timeout_s=2.0)
        await first.start()
        try:
            transaction_id = await first.start_purchase(correlation_id="restart_waiting")
            await first.accept_cash(transaction_id, correlation_id="restart_waiting")
            await first.insert_bill(500, correlation_id="restart_waiting")
            transaction = first.core.transaction_coordinator.require(transaction_id)
            self.assertEqual(transaction.status, TransactionStatus.WAITING_FOR_CUSTOMER_PICKUP)
        finally:
            await first.stop()

        restarted = SimulationHarness.build(pickup_timeout_s=0.05)
        restarted.core.transaction_coordinator.restore_transactions(
            [transaction],
            active_transaction_id=transaction.transaction_id.value,
        )
        restarted.core.machine_status_service.set_active_transaction(
            transaction.transaction_id.value
        )
        restarted.core.fsm.force_state(
            MachineState.WAITING_FOR_CUSTOMER_PICKUP,
            "test_restored_waiting_pickup",
        )
        restarted.core.machine_status_service.set_machine_state(restarted.core.fsm.current_state)
        await restarted.start()
        try:
            await restarted.wait_for_runtime_processing(timeout_s=0.2)

            restored_transaction = restarted.core.transaction_coordinator.require(transaction_id)
            self.assertEqual(restarted.core.fsm.current_state, MachineState.RECOVERY_PENDING)
            self.assertEqual(restored_transaction.status, TransactionStatus.PICKUP_TIMED_OUT)
            self.assertIn("pickup_timeout_elapsed", restarted.recorder.event_types)
        finally:
            await restarted.stop()

    async def test_pickup_timeout_scenario_reports_recovery(self) -> None:
        result = await run_pickup_timeout_scenario()
        self.assertTrue(result.success)
        self.assertEqual(result.machine_state, "RECOVERY_PENDING")
        self.assertEqual(result.transaction_status, "pickup_timed_out")


if __name__ == "__main__":
    unittest.main()

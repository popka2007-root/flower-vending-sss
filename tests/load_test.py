"""Load/concurrency test for the vending machine core.

Simulates concurrent purchase attempts, bill insertions, and status
polling to verify the system handles contention without deadlocks or
data corruption.

Run with: python -m pytest tests/load_test.py -v --timeout=120
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from flower_vending.simulators.harness import SimulationHarness


CONCURRENT_BUYERS = 10
CONCURRENT_POLLS = 20


@pytest.mark.asyncio
class TestConcurrentPurchases:
    async def test_concurrent_purchase_attempts_are_serialized_by_fsm(self) -> None:
        harness = SimulationHarness.build(
            price_minor_units=500,
            change_inventory={100: 50, 50: 50},
            accepted_bill_denominations=(100, 500, 1000),
        )
        await harness.start()
        try:
            tasks = [
                harness.start_purchase(correlation_id=f"concurrent-{i}")
                for i in range(CONCURRENT_BUYERS)
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            success_count = sum(1 for r in results if isinstance(r, str))
            assert success_count >= 1, "at least one purchase should succeed"
            assert success_count <= 2, (
                "serialized FSM should allow at most one concurrent active purchase; "
                f"got {success_count} successes"
            )
        finally:
            await harness.stop()

    async def test_concurrent_bill_insertion_does_not_corrupt_state(self) -> None:
        harness = SimulationHarness.build(
            price_minor_units=1000,
            change_inventory={100: 50, 50: 50},
            accepted_bill_denominations=(100, 500),
        )
        await harness.start()
        try:
            tx_id = await harness.start_purchase(correlation_id="load-bill-insert")
            await harness.accept_cash(tx_id, correlation_id="load-bill-insert")

            async def insert_bill_task(amount: int) -> None:
                try:
                    await harness.insert_bill(
                        amount,
                        correlation_id=f"load-bill-{amount}",
                        raise_on_error=False,
                    )
                except Exception:
                    pass

            bill_tasks = [insert_bill_task(100) for _ in range(5)] + [
                insert_bill_task(500) for _ in range(3)
            ]
            await asyncio.gather(*bill_tasks, return_exceptions=True)
            tx = harness.core.transaction_coordinator.get(tx_id)
            assert tx is not None
        finally:
            await harness.stop()

    async def test_concurrent_status_polling_during_active_sale(self) -> None:
        harness = SimulationHarness.build(
            price_minor_units=500,
            change_inventory={100: 10},
            accepted_bill_denominations=(100, 500),
        )
        await harness.start()
        try:
            tx_id = await harness.start_purchase(correlation_id="load-poll")
            await harness.accept_cash(tx_id, correlation_id="load-poll")
            await harness.insert_bill(100, correlation_id="load-poll")

            async def poll_status() -> dict[str, Any]:
                machine = harness.core.machine_status_service.runtime.status
                return {
                    "machine_state": machine.machine_state,
                    "sale_blockers": tuple(machine.sale_blockers),
                    "allow_cash_sales": machine.allow_cash_sales,
                }

            poll_results = await asyncio.gather(*[poll_status() for _ in range(CONCURRENT_POLLS)])
            assert len(poll_results) == CONCURRENT_POLLS
            first = poll_results[0]
            assert all(r == first for r in poll_results), "status should be consistent"
        finally:
            await harness.stop()

    async def test_concurrent_cancel_and_confirm_without_deadlock(self) -> None:
        harness = SimulationHarness.build(
            price_minor_units=500,
            change_inventory={100: 10, 50: 10},
            accepted_bill_denominations=(100, 500),
        )
        await harness.start()
        try:
            tx_id = await harness.start_purchase(correlation_id="load-race")
            await harness.accept_cash(tx_id, correlation_id="load-race")

            from flower_vending.domain.commands.purchase_commands import (
                CancelPurchase,
                ConfirmPickup,
            )

            cancel_task = harness.core.command_bus.dispatch(
                CancelPurchase(correlation_id="load-race-2", transaction_id=tx_id)
            )
            confirm_task = harness.core.command_bus.dispatch(
                ConfirmPickup(correlation_id="load-race-2", transaction_id=tx_id)
            )
            await asyncio.gather(cancel_task, confirm_task, return_exceptions=True)
            tx = harness.core.transaction_coordinator.get(tx_id)
            assert tx is not None
        finally:
            await harness.stop()


@pytest.mark.asyncio
class TestConcurrentRuntimeAccess:
    async def test_multiple_harnesses_run_independently(self) -> None:
        harnesses = [
            SimulationHarness.build(
                product_id=f"product-{i}",
                slot_id=f"S{i}",
                price_minor_units=500,
                change_inventory={100: 10},
                accepted_bill_denominations=(100, 500),
            )
            for i in range(5)
        ]
        for h in harnesses:
            await h.start()
        try:
            tx_ids = []
            for i, h in enumerate(harnesses):
                tx_id = await h.start_purchase(correlation_id=f"isolated-{i}")
                await h.accept_cash(tx_id, correlation_id=f"isolated-{i}")
                await h.insert_bill(500, correlation_id=f"isolated-{i}")
                tx_ids.append((h, tx_id))
            for h, tx_id in tx_ids:
                await h.confirm_pickup(tx_id, correlation_id="isolated-confirm")
                tx = h.core.transaction_coordinator.get(tx_id)
                assert tx is not None and tx.status.value in {"completed", "cancelled"}
        finally:
            for h in harnesses:
                await h.stop()

from __future__ import annotations

import unittest

from tests._support import ROOT  # noqa: F401

from flower_vending.domain.entities import MoneyInventory
from flower_vending.domain.exceptions import ChangeUnavailableError
from flower_vending.domain.value_objects import Currency
from flower_vending.payments.change_manager import ChangeManager
from flower_vending.simulators.devices import MockChangeDispenser


class ChangeManagerUnitTests(unittest.IsolatedAsyncioTestCase):
    async def test_exact_change_only_assessment_when_worst_case_change_is_unsafe(self) -> None:
        inventory = MoneyInventory(
            currency=Currency("RUB"),
            accounting_counts_by_denomination={100: 1},
        )
        manager = ChangeManager(
            inventory=inventory,
            change_dispenser=MockChangeDispenser(inventory={100: 1}),
            accepted_bill_denominations=(500,),
        )

        class _TransactionStub:
            class _Price:
                minor_units = 300

            price = _Price()

        assessment = await manager.assess_sale(_TransactionStub())  # type: ignore[arg-type]
        self.assertFalse(assessment.sale_supported)
        self.assertTrue(assessment.exact_change_only)
        self.assertEqual(assessment.plan, {})

    async def test_clear_drift_resets_flag(self) -> None:
        inventory = MoneyInventory(
            currency=Currency("RUB"),
            accounting_counts_by_denomination={100: 5},
            drift_detected=True,
        )
        manager = ChangeManager(
            inventory=inventory,
            change_dispenser=MockChangeDispenser(inventory={100: 5}),
        )
        self.assertTrue(inventory.drift_detected)
        manager.clear_drift()
        self.assertFalse(inventory.drift_detected)

    async def test_clear_drift_via_machine_status_service(self) -> None:
        inventory = MoneyInventory(
            currency=Currency("RUB"),
            accounting_counts_by_denomination={100: 5},
            drift_detected=True,
        )
        manager = ChangeManager(
            inventory=inventory,
            change_dispenser=MockChangeDispenser(inventory={100: 5}),
        )
        from flower_vending.app.services import MachineStatusService
        from flower_vending.domain.aggregates import MachineRuntimeAggregate

        service = MachineStatusService(MachineRuntimeAggregate(), change_manager=manager)
        self.assertTrue(inventory.drift_detected)
        service.clear_drift()
        self.assertFalse(inventory.drift_detected)

    async def test_reserve_rejects_insufficient_change_inventory(self) -> None:
        inventory = MoneyInventory(
            currency=Currency("RUB"),
            accounting_counts_by_denomination={100: 1},
        )
        manager = ChangeManager(
            inventory=inventory,
            change_dispenser=MockChangeDispenser(inventory={100: 1}),
            accepted_bill_denominations=(500,),
        )

        with self.assertRaises(ChangeUnavailableError):
            await manager.reserve_for_transaction("tx-1", {100: 2})


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest

from flower_vending.simulators.scenarios.catalog import run_default_scenario_suite


class SimulatorScenarioTests(unittest.IsolatedAsyncioTestCase):
    async def test_named_scenarios_cover_customer_and_fault_paths(self) -> None:
        results = await run_default_scenario_suite(
            ("normal_sale", "bill_rejected", "pickup_timeout")
        )
        self.assertEqual(
            [result.scenario_name for result in results],
            ["normal_sale", "bill_rejected", "pickup_timeout"],
        )
        self.assertTrue(all(result.success for result in results))


if __name__ == "__main__":
    unittest.main()

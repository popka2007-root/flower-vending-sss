from __future__ import annotations

import unittest
from pathlib import Path

import yaml

from tests._support import ROOT, workspace_temp_dir

from flower_vending.domain.entities import Product, Slot
from flower_vending.domain.value_objects import Amount, Currency, ProductId, SlotId
from flower_vending.infrastructure.persistence.sqlite import (
    ProductRepository,
    SQLiteDatabase,
    SlotRepository,
    ensure_sqlite_schema,
)
from flower_vending.runtime.bootstrap import build_simulator_environment


class RuntimeModeIntegrationTests(unittest.IsolatedAsyncioTestCase):
    def _make_temp_config(self, tmp: Path) -> Path:
        payload = yaml.safe_load(
            (ROOT / "config" / "examples" / "machine.simulator.yaml").read_text(encoding="utf-8")
        )
        payload["persistence"]["sqlite_path"] = str(tmp / "runtime.db")
        payload["logging"]["directory"] = str(tmp / "log")
        path = tmp / "runtime.yaml"
        path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
        return path

    async def test_startup_flow_reaches_idle_and_creates_runtime_artifacts(self) -> None:
        with workspace_temp_dir(prefix="runtime-") as tmp:
            environment = await build_simulator_environment(
                config_path=self._make_temp_config(tmp),
                prepare_directories=True,
            )
            await environment.start()
            try:
                report = environment.diagnostics_report()
                self.assertEqual(report["machine"]["machine_state"], "IDLE")
                self.assertTrue((tmp / "log").exists())
                self.assertTrue((tmp / "runtime.db").exists())
            finally:
                await environment.stop()

    async def test_diagnostics_mode_surfaces_recent_events(self) -> None:
        with workspace_temp_dir(prefix="runtime-") as tmp:
            environment = await build_simulator_environment(
                config_path=self._make_temp_config(tmp),
                prepare_directories=True,
            )
            await environment.start()
            try:
                await environment.simulator_controls.execute_action(
                    "open_service_door",
                    correlation_id=environment.ui_facade.new_correlation_id(),
                )
                report = environment.diagnostics_report()
                self.assertTrue(
                    any(
                        item["event_type"] == "service_door_opened"
                        for item in report["recent_events"]
                    )
                )
            finally:
                await environment.stop()

    async def test_service_mode_report_reflects_applied_fault_actions(self) -> None:
        with workspace_temp_dir(prefix="runtime-") as tmp:
            environment = await build_simulator_environment(
                config_path=self._make_temp_config(tmp),
                prepare_directories=True,
            )
            await environment.start()
            try:
                await environment.simulator_controls.execute_action(
                    "inject_motor_fault",
                    correlation_id=environment.ui_facade.new_correlation_id(),
                )
                report = await environment.service_report(operator_id="svc-tech")
                self.assertEqual(report["operator_id"], "svc-tech")
                self.assertEqual(report["machine_state"], "SERVICE_MODE")
                self.assertTrue(
                    any(
                        item["event_type"] == "simulator_action_applied"
                        for item in report["recent_events"]
                    )
                )
            finally:
                await environment.stop()

    async def test_legacy_demo_catalog_is_replaced_with_storefront_catalog(self) -> None:
        with workspace_temp_dir(prefix="runtime-") as tmp:
            config_path = self._make_temp_config(tmp)
            database = SQLiteDatabase(tmp / "runtime.db")
            ensure_sqlite_schema(database)
            products = ProductRepository(database)
            slots = SlotRepository(database)
            products.save(
                Product(
                    product_id=ProductId("rose_red"),
                    name="rose_red",
                    display_name="Red Roses",
                    price=Amount(500, Currency("RUB")),
                    category="flowers",
                    metadata={},
                )
            )
            slots.save(
                Slot(
                    slot_id=SlotId("A1"),
                    product_id=ProductId("rose_red"),
                    capacity=8,
                    quantity=4,
                )
            )
            database.close()

            environment = await build_simulator_environment(
                config_path=config_path,
                prepare_directories=True,
            )
            await environment.start()
            try:
                entries = environment.ui_facade.catalog_entries()
                self.assertTrue(
                    any(entry.display_name == "Розы Эквадор 7 шт." for entry in entries)
                )
                self.assertFalse(any(entry.display_name == "Red Roses" for entry in entries))
            finally:
                await environment.stop()


if __name__ == "__main__":
    unittest.main()

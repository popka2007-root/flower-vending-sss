from __future__ import annotations

import unittest
from pathlib import Path

import yaml

from tests._support import ROOT, workspace_temp_dir

from flower_vending.runtime.bootstrap import validate_config_file


class ConfigValidationTests(unittest.TestCase):
    def test_simulator_config_is_valid(self) -> None:
        _, _, report = validate_config_file(ROOT / "config" / "examples" / "machine.simulator.yaml")
        self.assertTrue(report.valid)
        self.assertEqual(report.messages, ())

    def test_invalid_scenario_is_reported(self) -> None:
        source = ROOT / "config" / "examples" / "machine.simulator.yaml"
        payload = yaml.safe_load(source.read_text(encoding="utf-8"))
        payload["simulator"]["scenario_suite"] = ["normal_sale", "missing_scenario"]

        with workspace_temp_dir(prefix="config-") as tmp:
            config_path = Path(tmp) / "invalid.yaml"
            config_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
            _, _, report = validate_config_file(config_path)

        self.assertFalse(report.valid)
        self.assertTrue(any(message.code == "unknown_scenario" for message in report.messages))

    def test_windows_config_reports_hardware_confirmation_warnings(self) -> None:
        _, _, report = validate_config_file(ROOT / "config" / "examples" / "machine.windows.yaml")
        self.assertTrue(report.valid)
        self.assertTrue(
            any(message.code == "hardware_confirmation_required" for message in report.messages)
        )
        self.assertTrue(any(message.code == "simulator_disabled" for message in report.messages))


if __name__ == "__main__":
    unittest.main()

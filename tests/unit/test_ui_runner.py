from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from tests._support import ROOT, workspace_temp_dir

from flower_vending.runtime.ui_runner import reset_simulator_state


class UiRunnerTests(unittest.TestCase):
    def _make_config(self, tmp: Path) -> Path:
        payload = yaml.safe_load(
            (ROOT / "config" / "examples" / "machine.simulator.yaml").read_text(encoding="utf-8")
        )
        payload["persistence"]["sqlite_path"] = str(
            tmp / "var" / "data" / "flower_vending_simulator.db"
        )
        payload["logging"]["directory"] = str(tmp / "var" / "log")
        config_path = tmp / "runtime.yaml"
        config_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
        return config_path

    def test_reset_simulator_state_removes_sqlite_sidecars(self) -> None:
        with workspace_temp_dir(prefix="ui-reset-") as tmp:
            config_path = self._make_config(tmp)
            database_path = tmp / "var" / "data" / "flower_vending_simulator.db"
            database_path.parent.mkdir(parents=True, exist_ok=True)
            for suffix in ("", "-wal", "-shm", "-journal"):
                database_path.with_name(database_path.name + suffix).write_text(
                    "state", encoding="utf-8"
                )

            with patch.dict(os.environ, {"FLOWER_VENDING_STATE_ROOT": str(tmp)}):
                removed = reset_simulator_state(config_path=str(config_path))

            self.assertEqual(len(removed), 4)
            for path in removed:
                self.assertFalse(path.exists())

    def test_reset_simulator_state_refuses_paths_outside_state_root(self) -> None:
        with workspace_temp_dir(prefix="ui-reset-") as tmp:
            config_path = self._make_config(tmp)
            with patch.dict(os.environ, {"FLOWER_VENDING_STATE_ROOT": str(tmp / "safe-state")}):
                with self.assertRaisesRegex(RuntimeError, "outside runtime state root"):
                    reset_simulator_state(config_path=str(config_path))


if __name__ == "__main__":
    unittest.main()

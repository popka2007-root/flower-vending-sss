"""Shared helpers for stdlib test execution."""

from __future__ import annotations

import sys
import tempfile
import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict, Unpack

import yaml


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


from flower_vending.runtime.bootstrap import (  # noqa: E402
    SimulatorRuntimeEnvironment,
    build_simulator_environment,
)
from flower_vending.simulators.harness import SimulationHarness  # noqa: E402
from flower_vending.app.journal import ApplicationJournal  # noqa: E402


class HarnessBuildKwargs(TypedDict, total=False):
    product_id: str
    slot_id: str
    price_minor_units: int
    currency_code: str
    slot_quantity: int
    change_inventory: dict[int, int] | None
    accepted_bill_denominations: tuple[int, ...]
    inventory_presence: bool
    inventory_confidence: float
    temperature_celsius: float
    service_door_open: bool
    journal: ApplicationJournal | None


class AsyncHarnessTestCase(unittest.IsolatedAsyncioTestCase):
    async def create_harness(self, **kwargs: Unpack[HarnessBuildKwargs]) -> SimulationHarness:
        harness = SimulationHarness.build(**kwargs)
        await harness.start()
        self.addAsyncCleanup(harness.stop)
        return harness


@contextmanager
def workspace_temp_dir(prefix: str = "tmp") -> Iterator[Path]:
    root = ROOT / "var" / "tmp"
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=prefix, dir=root) as tmp:
        yield Path(tmp)


@dataclass(frozen=True, slots=True)
class TempSimulatorRuntime:
    root: Path
    config_path: Path
    sqlite_path: Path
    log_dir: Path

    async def build(self) -> SimulatorRuntimeEnvironment:
        return await build_simulator_environment(
            config_path=self.config_path,
            prepare_directories=True,
        )


def make_temp_simulator_runtime(tmp: Path, *, sqlite_name: str = "runtime.db") -> TempSimulatorRuntime:
    payload = yaml.safe_load(
        (ROOT / "config" / "examples" / "machine.simulator.yaml").read_text(encoding="utf-8")
    )
    sqlite_path = tmp / sqlite_name
    log_dir = tmp / "log"
    payload["persistence"]["sqlite_path"] = str(sqlite_path)
    payload["logging"]["directory"] = str(log_dir)
    config_path = tmp / "runtime.yaml"
    config_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return TempSimulatorRuntime(
        root=tmp,
        config_path=config_path,
        sqlite_path=sqlite_path,
        log_dir=log_dir,
    )

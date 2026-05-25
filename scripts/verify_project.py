"""Run the simulator-safe verification suite for the flower vending project."""

from __future__ import annotations

import asyncio
import subprocess
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
CONFIG_MATRIX = (
    "config/examples/machine.simulator.yaml",
    "config/examples/machine.windows.yaml",
    "config/examples/machine.linux.yaml",
    "config/targets/machine.debian13-target.yaml",
)
CLI_HELP_COMMANDS = (
    (),
    ("validate-config",),
    ("diagnostics",),
    ("status",),
    ("events",),
    ("service",),
    ("simulator-runtime",),
    ("simulator-ui",),
    ("dbv300sd-serial-smoke",),
)


def _prepare_import_path() -> None:
    for path in (ROOT, SRC):
        path_text = str(path)
        if path_text not in sys.path:
            sys.path.insert(0, path_text)


def _run_command(label: str, command: list[str]) -> bool:
    print(f"\n== {label} ==")
    print(" ".join(command))
    result = subprocess.run(command, cwd=ROOT, check=False)
    if result.returncode == 0:
        print(f"PASS: {label}")
        return True
    print(f"FAIL: {label} exited with {result.returncode}")
    return False


def _run_config_matrix() -> bool:
    success = True
    print("\n== config validation matrix ==")
    for config_path in CONFIG_MATRIX:
        command = [
            sys.executable,
            "-m",
            "flower_vending",
            "validate-config",
            "--config",
            config_path,
            "--json",
        ]
        success &= _run_command(f"validate {config_path}", command)
    return success


def _run_cli_help_smoke() -> bool:
    success = True
    print("\n== CLI help smoke checks ==")
    for command_args in CLI_HELP_COMMANDS:
        label = " ".join(("python -m flower_vending", *command_args, "--help"))
        success &= _run_command(
            label,
            [sys.executable, "-m", "flower_vending", *command_args, "--help"],
        )
    return success


async def _scenario_service_door_blocks_sale() -> None:
    from tests._support import SimulationHarness
    from flower_vending.domain.exceptions import SaleBlockedError

    harness = SimulationHarness.build(service_door_open=True)
    await harness.start()
    try:
        try:
            await harness.start_purchase(correlation_id="verify-door-open")
        except SaleBlockedError:
            return
        raise AssertionError("sale started while service door was open")
    finally:
        await harness.stop()


async def _scenario_validator_loop_processes_bill() -> None:
    from tests._support import SimulationHarness

    harness = SimulationHarness.build()
    await harness.start()
    try:
        transaction_id = await harness.start_purchase(correlation_id="verify-validator-loop")
        await harness.accept_cash(transaction_id, correlation_id="verify-validator-loop")
        await harness.validator.simulate_insert_bill(500, correlation_id="verify-validator-loop")
        await harness.wait_for_runtime_processing()
        transaction = harness.core.transaction_coordinator.require(transaction_id)
        if transaction.accepted_amount.minor_units != 500:
            raise AssertionError("validator event loop did not process the inserted bill")
        if transaction.status.value != "waiting_for_customer_pickup":
            raise AssertionError(f"unexpected transaction status: {transaction.status.value}")
    finally:
        await harness.stop()


async def _scenario_multi_note_unsafe_change_is_blocked() -> None:
    from tests._support import SimulationHarness
    from flower_vending.domain.exceptions import ChangeUnavailableError

    harness = SimulationHarness.build(
        price_minor_units=300,
        change_inventory={100: 2},
        accepted_bill_denominations=(100, 500),
    )
    await harness.start()
    try:
        transaction_id = await harness.start_purchase(correlation_id="verify-multi-note")
        try:
            await harness.accept_cash(transaction_id, correlation_id="verify-multi-note")
        except ChangeUnavailableError:
            return
        raise AssertionError("cash session started although multi-note overpay was unsafe")
    finally:
        await harness.stop()


async def _scenario_cancel_after_cash_refunds() -> None:
    from tests._support import SimulationHarness
    from flower_vending.domain.commands.purchase_commands import CancelPurchase

    harness = SimulationHarness.build(
        price_minor_units=300,
        change_inventory={100: 5},
        accepted_bill_denominations=(100, 500),
    )
    await harness.start()
    try:
        transaction_id = await harness.start_purchase(correlation_id="verify-refund")
        await harness.accept_cash(transaction_id, correlation_id="verify-refund")
        await harness.insert_bill(100, correlation_id="verify-refund")
        await harness.core.command_bus.dispatch(
            CancelPurchase(correlation_id="verify-refund", transaction_id=transaction_id)
        )
        transaction = harness.core.transaction_coordinator.require(transaction_id)
        inventory = await harness.change_dispenser.get_accounting_inventory()
        if transaction.status.value != "cancelled":
            raise AssertionError(f"unexpected transaction status: {transaction.status.value}")
        if inventory.get(100) != 4:
            raise AssertionError(f"refund did not consume one 100-unit payout: {inventory}")
    finally:
        await harness.stop()


async def _run_runtime_scenarios() -> bool:
    scenarios: tuple[tuple[str, Callable[[], Awaitable[None]]], ...] = (
        ("service door blocks sale on startup health check", _scenario_service_door_blocks_sale),
        (
            "validator background loop processes inserted bill",
            _scenario_validator_loop_processes_bill,
        ),
        ("unsafe multi-note change path is blocked", _scenario_multi_note_unsafe_change_is_blocked),
        ("cancel after accepted cash dispenses refund", _scenario_cancel_after_cash_refunds),
    )
    print("\n== Focused runtime scenarios ==")
    success = True
    for name, scenario in scenarios:
        try:
            await scenario()
        except Exception as exc:
            success = False
            print(f"FAIL: {name}: {exc}")
        else:
            print(f"PASS: {name}")
    return success


def main() -> int:
    _prepare_import_path()
    checks_ok = True
    checks_ok &= _run_command(
        "validate simulator config",
        [
            sys.executable,
            "-m",
            "flower_vending",
            "validate-config",
            "--config",
            "config/examples/machine.simulator.yaml",
            "--prepare",
        ],
    )
    checks_ok &= _run_config_matrix()
    checks_ok &= _run_command(
        "compile source and tests",
        [sys.executable, "-m", "compileall", "-q", "src", "tests"],
    )
    checks_ok &= _run_cli_help_smoke()
    checks_ok &= _run_command(
        "repository hygiene check",
        [sys.executable, "scripts/check_repository_hygiene.py"],
    )
    checks_ok &= _run_command(
        "UI smoke check",
        [sys.executable, "scripts/ui_smoke_check.py"],
    )
    checks_ok &= _run_command(
        "pytest test suite",
        [sys.executable, "-m", "pytest", "-q"],
    )
    checks_ok &= _run_command(
        "diagnostics mode smoke test",
        [
            sys.executable,
            "-m",
            "flower_vending",
            "diagnostics",
            "--config",
            "config/examples/machine.simulator.yaml",
        ],
    )
    checks_ok &= asyncio.run(_run_runtime_scenarios())
    if checks_ok:
        print("\nVerification finished successfully.")
        return 0
    print("\nVerification failed. See the failing section above.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

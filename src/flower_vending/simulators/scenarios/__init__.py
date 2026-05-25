"""Deterministic simulator scenarios."""

from flower_vending.simulators.scenarios.catalog import (
    SCENARIO_REGISTRY,
    run_default_scenario_suite,
)
from flower_vending.simulators.scenarios.customer_flows import run_happy_path_scenario
from flower_vending.simulators.scenarios.fault_flows import (
    run_bill_jam_scenario,
    run_critical_temperature_scenario,
    run_door_open_scenario,
    run_inventory_mismatch_scenario,
    run_motor_fault_scenario,
    run_partial_payout_scenario,
    run_validator_unavailable_scenario,
)

__all__ = [
    "SCENARIO_REGISTRY",
    "run_default_scenario_suite",
    "run_happy_path_scenario",
    "run_validator_unavailable_scenario",
    "run_bill_jam_scenario",
    "run_partial_payout_scenario",
    "run_motor_fault_scenario",
    "run_door_open_scenario",
    "run_critical_temperature_scenario",
    "run_inventory_mismatch_scenario",
]

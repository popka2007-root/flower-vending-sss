"""Fault-injection scenarios for deterministic simulator runs."""

from __future__ import annotations

from flower_vending.devices.exceptions import DeviceAdapterError
from flower_vending.domain.exceptions import (
    InventoryMismatchError,
    PartialPayoutError,
    SaleBlockedError,
    ValidatorUnavailableError,
)
from flower_vending.simulators.faults import SimulatorFaultCode
from flower_vending.simulators.harness import SimulationHarness
from flower_vending.simulators.scenario_result import ScenarioResult


async def run_validator_unavailable_scenario() -> ScenarioResult:
    harness = SimulationHarness.build()
    await harness.start()
    try:
        transaction_id = await harness.start_purchase(correlation_id="validator_unavailable")
        harness.validator.inject_fault(
            SimulatorFaultCode.VALIDATOR_UNAVAILABLE,
            message="simulated validator startup failure",
        )
        try:
            await harness.accept_cash(transaction_id, correlation_id="validator_unavailable")
        except ValidatorUnavailableError as exc:
            return harness.scenario_result(
                scenario_name="validator_unavailable",
                success=harness.core.fsm.current_state.value == "FAULT",
                errors=[str(exc)],
                notes=["validator rejected transition into accepting state"],
            )
        return harness.scenario_result(
            scenario_name="validator_unavailable",
            success=False,
            errors=["expected ValidatorUnavailableError was not raised"],
        )
    finally:
        await harness.stop()


async def run_bill_rejected_scenario() -> ScenarioResult:
    harness = SimulationHarness.build()
    await harness.start()
    try:
        transaction_id = await harness.start_purchase(correlation_id="bill_rejected")
        await harness.accept_cash(transaction_id, correlation_id="bill_rejected")
        harness.validator.inject_fault(
            SimulatorFaultCode.BILL_REJECTED,
            message="simulated bill rejection",
            critical=False,
        )
        await harness.insert_bill(500, correlation_id="bill_rejected")
        transaction = harness.core.transaction_coordinator.require(transaction_id)
        return harness.scenario_result(
            scenario_name="bill_rejected",
            success=transaction.accepted_amount.minor_units == 0,
            notes=["validator rejected the bill without incrementing accepted amount"],
        )
    finally:
        await harness.stop()


async def run_bill_jam_scenario() -> ScenarioResult:
    harness = SimulationHarness.build()
    await harness.start()
    try:
        transaction_id = await harness.start_purchase(correlation_id="bill_jam")
        await harness.accept_cash(transaction_id, correlation_id="bill_jam")
        harness.validator.inject_fault(
            SimulatorFaultCode.BILL_JAM,
            message="simulated bill path jam",
        )
        try:
            await harness.insert_bill(500, correlation_id="bill_jam")
        except ValidatorUnavailableError as exc:
            return harness.scenario_result(
                scenario_name="bill_jam",
                success=harness.core.fsm.current_state.value == "FAULT",
                errors=[str(exc)],
                notes=["validator fault event escalated from bill jam"],
            )
        return harness.scenario_result(
            scenario_name="bill_jam",
            success=False,
            errors=["expected ValidatorUnavailableError was not raised"],
        )
    finally:
        await harness.stop()


async def run_partial_payout_scenario() -> ScenarioResult:
    harness = SimulationHarness.build(
        price_minor_units=300,
        change_inventory={100: 2},
        accepted_bill_denominations=(500,),
    )
    await harness.start()
    try:
        transaction_id = await harness.start_purchase(correlation_id="partial_payout")
        await harness.accept_cash(transaction_id, correlation_id="partial_payout")
        harness.change_dispenser.inject_fault(
            SimulatorFaultCode.PARTIAL_PAYOUT,
            message="simulated partial payout",
        )
        try:
            await harness.insert_bill(500, correlation_id="partial_payout")
        except PartialPayoutError as exc:
            transaction = harness.core.transaction_coordinator.require(transaction_id)
            return harness.scenario_result(
                scenario_name="partial_payout",
                success=(
                    harness.core.fsm.current_state.value == "RECOVERY_PENDING"
                    and transaction.status.value == "ambiguous"
                ),
                errors=[str(exc)],
                notes=["cash accepted but payout remained ambiguous and vend stayed blocked"],
            )
        return harness.scenario_result(
            scenario_name="partial_payout",
            success=False,
            errors=["expected PartialPayoutError was not raised"],
        )
    finally:
        await harness.stop()


async def run_product_vend_failure_scenario() -> ScenarioResult:
    harness = SimulationHarness.build()
    await harness.start()
    try:
        transaction_id = await harness.start_purchase(correlation_id="product_vend_failure")
        await harness.accept_cash(transaction_id, correlation_id="product_vend_failure")
        harness.motor_controller.inject_fault(
            SimulatorFaultCode.MOTOR_FAULT,
            message="simulated vend motor fault",
        )
        try:
            await harness.insert_bill(500, correlation_id="product_vend_failure")
        except DeviceAdapterError as exc:
            transaction = harness.core.transaction_coordinator.require(transaction_id)
            return harness.scenario_result(
                scenario_name="product_vend_failure",
                success=(
                    harness.core.fsm.current_state.value == "FAULT"
                    and transaction.status.value == "faulted"
                ),
                errors=[str(exc)],
                notes=["payment was confirmed but product vend failed before pickup"],
            )
        return harness.scenario_result(
            scenario_name="product_vend_failure",
            success=False,
            errors=["expected DeviceAdapterError was not raised"],
        )
    finally:
        await harness.stop()


async def run_motor_fault_scenario() -> ScenarioResult:
    return await run_product_vend_failure_scenario()


async def run_door_open_scenario() -> ScenarioResult:
    harness = SimulationHarness.build(service_door_open=True)
    await harness.start()
    try:
        await harness.poll_health()
        try:
            await harness.start_purchase(correlation_id="door_open")
        except SaleBlockedError as exc:
            return harness.scenario_result(
                scenario_name="door_open",
                success="service_door_open"
                in harness.core.machine_status_service.runtime.status.sale_blockers,
                errors=[str(exc)],
                notes=["health monitor blocked new sales while service door remained open"],
            )
        return harness.scenario_result(
            scenario_name="door_open",
            success=False,
            errors=["expected SaleBlockedError was not raised"],
        )
    finally:
        await harness.stop()


async def run_critical_temperature_scenario() -> ScenarioResult:
    harness = SimulationHarness.build(temperature_celsius=9.5)
    await harness.start()
    try:
        await harness.poll_health()
        try:
            await harness.start_purchase(correlation_id="critical_temperature")
        except SaleBlockedError as exc:
            return harness.scenario_result(
                scenario_name="critical_temperature",
                success="critical_temperature"
                in harness.core.machine_status_service.runtime.status.sale_blockers,
                errors=[str(exc)],
                notes=["health monitor blocked new sales at critical chamber temperature"],
            )
        return harness.scenario_result(
            scenario_name="critical_temperature",
            success=False,
            errors=["expected SaleBlockedError was not raised"],
        )
    finally:
        await harness.stop()


async def run_inventory_mismatch_scenario() -> ScenarioResult:
    harness = SimulationHarness.build(inventory_presence=False, inventory_confidence=1.0)
    await harness.start()
    try:
        try:
            await harness.start_purchase(correlation_id="inventory_mismatch")
        except InventoryMismatchError as exc:
            return harness.scenario_result(
                scenario_name="inventory_mismatch",
                success=True,
                errors=[str(exc)],
                notes=[
                    "physical slot sensor contradicted accounting inventory before payment started"
                ],
            )
        return harness.scenario_result(
            scenario_name="inventory_mismatch",
            success=False,
            errors=["expected InventoryMismatchError was not raised"],
        )
    finally:
        await harness.stop()

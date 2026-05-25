from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any, cast

import pytest

from flower_vending.app.fsm import MachineState
from flower_vending.simulators.harness import SimulationHarness
from flower_vending.ui.facade import UiApplicationFacade


class _FakeDatabase:
    @contextmanager
    def transaction(self) -> Any:
        yield object()


class _FakeTransactionRepository:
    def __init__(self) -> None:
        self.saved: list[Any] = []

    def save(self, transaction: Any, _connection: Any = None) -> None:
        del _connection
        self.saved.append(transaction)


class _FakeMachineStatusRepository:
    def __init__(self) -> None:
        self.saved: list[tuple[Any, str]] = []

    def save(self, status: Any, *, machine_id: str, _connection: Any = None) -> None:
        del _connection
        self.saved.append((status, machine_id))


@pytest.mark.asyncio
async def test_clear_simulator_recovery_state_resolves_persisted_restricted_state() -> None:
    harness = SimulationHarness.build()
    await harness.start()
    try:
        tx_id = await harness.start_purchase(correlation_id="ui-reset")
        tx = harness.core.transaction_coordinator.require(tx_id)
        tx.mark_ambiguous()
        harness.core.machine_status_service.set_active_transaction(tx_id)
        harness.core.machine_status_service.block_sales("recovery_pending")
        harness.core.fsm.force_state(MachineState.RECOVERY_PENDING, "test_restricted_state")
        harness.core.machine_status_service.set_machine_state(harness.core.fsm.current_state)

        tx_repo = _FakeTransactionRepository()
        machine_repo = _FakeMachineStatusRepository()
        repositories = cast(
            Any,
            SimpleNamespace(
                database=_FakeDatabase(),
                transactions=tx_repo,
                machine_status=machine_repo,
            ),
        )
        facade = UiApplicationFacade(
            harness.core,
            simulator_controls=cast(Any, object()),  # non-None enables simulator-only reset path
            repositories=repositories,
            machine_id="sim-test-machine",
        )

        cleared = facade.clear_simulator_recovery_state()

        assert cleared is True
        assert tx.status.value == "cancelled"
        assert tx.recovery_status.value == "none"
        assert harness.core.transaction_coordinator.active() is None
        assert harness.core.machine_status_service.runtime.status.active_transaction_id is None
        assert (
            "recovery_pending"
            not in harness.core.machine_status_service.runtime.status.sale_blockers
        )
        assert harness.core.fsm.current_state is MachineState.IDLE
        assert len(tx_repo.saved) == 1
        assert machine_repo.saved[-1][1] == "sim-test-machine"
    finally:
        await harness.stop()

"""Machine status projection service."""

from __future__ import annotations

from flower_vending.app.fsm.states import MachineState
from flower_vending.domain.aggregates import MachineRuntimeAggregate
from flower_vending.domain.exceptions import SaleBlockedError
from flower_vending.payments.change_manager import ChangeManager


class MachineStatusService:
    def __init__(self, runtime: MachineRuntimeAggregate, change_manager: ChangeManager | None = None) -> None:
        self._runtime = runtime
        self._change_manager = change_manager

    @property
    def runtime(self) -> MachineRuntimeAggregate:
        return self._runtime

    def set_machine_state(self, machine_state: MachineState) -> None:
        self._runtime.status.machine_state = machine_state.value
        self._runtime.status.refresh_permissions()

    def set_active_transaction(self, transaction_id: str | None) -> None:
        self._runtime.status.active_transaction_id = transaction_id
        self._runtime.status.refresh_permissions()

    def set_service_mode(self, enabled: bool) -> None:
        self._runtime.status.service_mode = enabled
        self._runtime.status.refresh_permissions()

    def set_exact_change_only(self, enabled: bool) -> None:
        self._runtime.status.exact_change_only = enabled
        self._runtime.status.refresh_permissions()

    def block_sales(self, reason: str) -> None:
        self._runtime.block_sales(reason)

    def unblock_sales(self, reason: str) -> None:
        self._runtime.unblock_sales(reason)

    def sales_allowed(self) -> bool:
        return self._runtime.status.allow_cash_sales and not self._runtime.status.sale_blockers

    def clear_drift(self) -> None:
        if self._change_manager is not None:
            self._change_manager.clear_drift()

    def ensure_sales_allowed(self) -> None:
        if not self.sales_allowed():
            blockers = ", ".join(sorted(self._runtime.status.sale_blockers)) or "unknown_blocker"
            raise SaleBlockedError(f"sales are blocked: {blockers}")

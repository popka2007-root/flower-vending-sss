"""Machine status projection entity."""

from __future__ import annotations

from dataclasses import dataclass, field


UNSAFE_MACHINE_STATES = {
    "BOOT",
    "SELF_TEST",
    "OUT_OF_SERVICE",
    "FAULT",
    "SERVICE_MODE",
    "RECOVERY_PENDING",
    "REFUND",
    "MANUAL_REVIEW",
}


@dataclass(slots=True)
class MachineStatus:
    machine_state: str = "BOOT"
    service_mode: bool = False
    exact_change_only: bool = False
    sale_blockers: set[str] = field(default_factory=set)
    warnings: set[str] = field(default_factory=set)
    active_transaction_id: str | None = None
    allow_cash_sales: bool = False
    allow_vending: bool = False

    def refresh_permissions(self) -> None:
        blocked = (
            bool(self.sale_blockers)
            or self.service_mode
            or self.machine_state in UNSAFE_MACHINE_STATES
        )
        self.allow_cash_sales = not blocked
        self.allow_vending = not blocked

    def block(self, reason: str) -> None:
        self.sale_blockers.add(reason)
        self.refresh_permissions()

    def unblock(self, reason: str) -> None:
        self.sale_blockers.discard(reason)
        self.refresh_permissions()

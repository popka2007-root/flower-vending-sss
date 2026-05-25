"""Service-mode command models."""

from __future__ import annotations

from dataclasses import dataclass

from flower_vending.domain.commands import Command


@dataclass(frozen=True, slots=True)
class EnterServiceMode(Command):
    operator_id: str
    pin: str = ""
    reason: str = "manual_service"


@dataclass(frozen=True, slots=True)
class LockPurchaseButton(Command):
    operator_id: str
    locked: bool = True


@dataclass(frozen=True, slots=True)
class ToggleProductCommand(Command):
    product_id: str
    enabled: bool
    operator_id: str


@dataclass(frozen=True, slots=True)
class ReconcileCashInventory(Command):
    operator_id: str
    counts_by_denomination: dict[int, int]

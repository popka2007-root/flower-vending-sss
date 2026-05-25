"""Payment terminal configuration models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class PaymentTerminalConfig:
    enabled: bool = False
    driver: str = "mock"
    device_name: str = "payment_terminal"
    port: str = ""
    baudrate: int = 9600
    timeout_s: float = 30.0
    settings: dict[str, Any] = field(default_factory=dict)

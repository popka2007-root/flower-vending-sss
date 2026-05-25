"""Payment terminal interfaces for card acquiring integration."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


class PaymentMethod(StrEnum):
    CARD = "card"
    CASH = "cash"
    QR = "qr"
    SBP = "sbp"


class PaymentStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DECLINED = "declined"
    CANCELLED = "cancelled"
    ERROR = "error"
    TIMEOUT = "timeout"


class TerminalState(StrEnum):
    IDLE = "idle"
    WAITING_CARD = "waiting_card"
    PROCESSING = "processing"
    COMPLETED = "completed"
    ERROR = "error"
    OUT_OF_ORDER = "out_of_order"


@dataclass(frozen=True, slots=True)
class PaymentRequest:
    transaction_id: str
    amount_minor: int
    currency: str = "RUB"
    description: str = ""
    correlation_id: str | None = None

    @property
    def amount_rub(self) -> float:
        return self.amount_minor / 100.0


@dataclass(frozen=True, slots=True)
class PaymentResult:
    transaction_id: str
    status: PaymentStatus
    payment_method: PaymentMethod = PaymentMethod.CARD
    authorization_code: str | None = None
    card_last_digits: str | None = None
    provider: str | None = None
    occurred_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    details: dict[str, Any] = field(default_factory=dict)


class PaymentTerminal(ABC):
    """Contract for payment terminal (card, QR, SBP) adapters."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    async def get_state(self) -> TerminalState: ...

    @abstractmethod
    async def start_payment(self, request: PaymentRequest) -> PaymentResult: ...

    @abstractmethod
    async def cancel_payment(self, transaction_id: str) -> bool: ...

    @abstractmethod
    async def get_health(self) -> dict[str, Any]: ...

"""Payment session entity."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import StrEnum

from flower_vending.domain.exceptions import PaymentCancelledError
from flower_vending.domain.value_objects import Amount


def _ts() -> datetime:
    return datetime.now(tz=timezone.utc)


class PaymentSessionStatus(StrEnum):
    CREATED = "created"
    ACCEPTING = "accepting"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


@dataclass(slots=True)
class PaymentSession:
    transaction_id: str
    status: PaymentSessionStatus = PaymentSessionStatus.CREATED
    accepted_amount: Amount = field(default_factory=Amount.zero)
    accepted_bills: list[int] = field(default_factory=list)
    validator_enabled: bool = False
    started_at: datetime = field(default_factory=_ts)
    expires_at: datetime = field(default_factory=lambda: _ts() + timedelta(minutes=3))
    cancel_requested: bool = False

    def start_acceptance(self) -> None:
        self.status = PaymentSessionStatus.ACCEPTING
        self.validator_enabled = True

    def add_stacked_bill(self, bill_minor_units: int) -> None:
        if self.status == PaymentSessionStatus.CANCELLED:
            raise PaymentCancelledError("payment session has been cancelled")
        self.accepted_bills.append(bill_minor_units)
        self.accepted_amount = Amount(
            self.accepted_amount.minor_units + bill_minor_units, self.accepted_amount.currency
        )

    def cancel(self) -> None:
        self.status = PaymentSessionStatus.CANCELLED
        self.cancel_requested = True
        self.validator_enabled = False

    def complete(self) -> None:
        self.status = PaymentSessionStatus.COMPLETED
        self.validator_enabled = False

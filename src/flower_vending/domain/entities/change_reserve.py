"""Change reserve entity."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum

from flower_vending.domain.value_objects import Amount, Currency


def _ts() -> datetime:
    return datetime.now(tz=timezone.utc)


class ChangeReserveStatus(StrEnum):
    ACTIVE = "active"
    RELEASED = "released"
    CONSUMED = "consumed"
    AMBIGUOUS = "ambiguous"


@dataclass(slots=True)
class ChangeReserve:
    transaction_id: str
    reserved_counts_by_denomination: dict[int, int]
    currency: Currency = field(default_factory=Currency)
    status: ChangeReserveStatus = ChangeReserveStatus.ACTIVE
    created_at: datetime = field(default_factory=_ts)
    released_at: datetime | None = None

    @property
    def reserved_total(self) -> Amount:
        total = sum(
            denomination * count
            for denomination, count in self.reserved_counts_by_denomination.items()
        )
        return Amount(total, self.currency)

    def release(self) -> None:
        self.status = ChangeReserveStatus.RELEASED
        self.released_at = _ts()

    def consume(self) -> None:
        self.status = ChangeReserveStatus.CONSUMED

    def mark_ambiguous(self) -> None:
        self.status = ChangeReserveStatus.AMBIGUOUS

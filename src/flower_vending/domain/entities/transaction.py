"""Transaction entity and statuses."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum

from flower_vending.domain.entities.change_reserve import ChangeReserve
from flower_vending.domain.entities.payment_session import PaymentSession
from flower_vending.domain.exceptions import (
    InvariantViolationError,
    PaymentSessionUnavailableError,
)
from flower_vending.domain.value_objects import Amount, CorrelationId, ProductId, SlotId, TransactionId


def _ts() -> datetime:
    return datetime.now(tz=timezone.utc)


class TransactionStatus(StrEnum):
    CREATED = "created"
    CHECKING_AVAILABILITY = "checking_availability"
    CHECKING_CHANGE = "checking_change"
    WAITING_FOR_PAYMENT = "waiting_for_payment"
    ACCEPTING_CASH = "accepting_cash"
    PAYMENT_ACCEPTED = "payment_accepted"
    DISPENSING_CHANGE = "dispensing_change"
    DISPENSING_PRODUCT = "dispensing_product"
    OPENING_DELIVERY_WINDOW = "opening_delivery_window"
    WAITING_FOR_CUSTOMER_PICKUP = "waiting_for_customer_pickup"
    CLOSING_DELIVERY_WINDOW = "closing_delivery_window"
    PICKUP_TIMED_OUT = "pickup_timed_out"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAULTED = "faulted"
    AMBIGUOUS = "ambiguous"


class PaymentStatus(StrEnum):
    PENDING = "pending"
    ACCEPTING = "accepting"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class PayoutStatus(StrEnum):
    NOT_REQUIRED = "not_required"
    RESERVED = "reserved"
    PENDING = "pending"
    DISPENSED = "dispensed"
    PARTIAL = "partial"
    FAILED = "failed"
    AMBIGUOUS = "ambiguous"


class DispenseStatus(StrEnum):
    NOT_STARTED = "not_started"
    AUTHORIZED = "authorized"
    DISPENSED = "dispensed"
    FAILED = "failed"
    AMBIGUOUS = "ambiguous"


class DeliveryStatus(StrEnum):
    NOT_STARTED = "not_started"
    WINDOW_OPENED = "window_opened"
    PICKUP_CONFIRMED = "pickup_confirmed"
    WINDOW_CLOSED = "window_closed"


class RecoveryStatus(StrEnum):
    NONE = "none"
    PENDING = "pending"
    MANUAL_REVIEW = "manual_review"


@dataclass(slots=True)
class Transaction:
    transaction_id: TransactionId
    correlation_id: CorrelationId
    product_id: ProductId
    slot_id: SlotId
    price: Amount
    status: TransactionStatus = TransactionStatus.CREATED
    accepted_amount: Amount = field(default_factory=Amount.zero)
    change_due: Amount = field(default_factory=Amount.zero)
    payment_status: PaymentStatus = PaymentStatus.PENDING
    payout_status: PayoutStatus = PayoutStatus.NOT_REQUIRED
    dispense_status: DispenseStatus = DispenseStatus.NOT_STARTED
    delivery_status: DeliveryStatus = DeliveryStatus.NOT_STARTED
    recovery_status: RecoveryStatus = RecoveryStatus.NONE
    payment_session: PaymentSession | None = None
    change_reserve: ChangeReserve | None = None
    created_at: datetime = field(default_factory=_ts)
    updated_at: datetime = field(default_factory=_ts)
    _cancelled: bool = field(default=False, repr=False)

    def touch(self) -> None:
        self.updated_at = _ts()

    def attach_payment_session(self, session: PaymentSession) -> None:
        self.payment_session = session
        self.status = TransactionStatus.ACCEPTING_CASH
        self.payment_status = PaymentStatus.ACCEPTING
        self.touch()

    def attach_change_reserve(self, reserve: ChangeReserve) -> None:
        self.change_reserve = reserve
        self.payout_status = PayoutStatus.RESERVED
        self.touch()

    def record_stacked_cash(self, bill_minor_units: int) -> None:
        if self._cancelled:
            raise InvariantViolationError("cannot record cash on a cancelled transaction")
        if self.payment_session is None:
            raise PaymentSessionUnavailableError("no active payment session")
        self.payment_session.add_stacked_bill(bill_minor_units)
        self.accepted_amount = self.payment_session.accepted_amount
        self.touch()

    def confirm_payment(self) -> None:
        if self.accepted_amount < self.price:
            raise InvariantViolationError("cannot confirm payment below sale price")
        self.payment_status = PaymentStatus.CONFIRMED
        self.status = TransactionStatus.PAYMENT_ACCEPTED
        if self.payment_session is not None:
            self.payment_session.complete()
        overpay_minor = self.accepted_amount.minor_units - self.price.minor_units
        self.change_due = Amount(overpay_minor, self.price.currency)
        self.payout_status = (
            PayoutStatus.NOT_REQUIRED if self.change_due.is_zero() else self.payout_status
        )
        self.touch()

    def mark_change_pending(self) -> None:
        self.payout_status = PayoutStatus.PENDING
        self.status = TransactionStatus.DISPENSING_CHANGE
        self.touch()

    def mark_change_dispensed(self) -> None:
        self.payout_status = PayoutStatus.DISPENSED
        self.touch()

    def mark_change_partial(self) -> None:
        self.payout_status = PayoutStatus.PARTIAL
        self.status = TransactionStatus.AMBIGUOUS
        self.recovery_status = RecoveryStatus.PENDING
        self.touch()

    def authorize_vend(self) -> None:
        if self.payment_status is not PaymentStatus.CONFIRMED:
            raise InvariantViolationError("vend cannot be authorized before payment confirmation")
        if self.change_due.minor_units > 0 and self.payout_status is not PayoutStatus.DISPENSED:
            raise InvariantViolationError("vend cannot be authorized before change payout resolves")
        self.dispense_status = DispenseStatus.AUTHORIZED
        self.status = TransactionStatus.DISPENSING_PRODUCT
        self.touch()

    def mark_product_dispensed(self) -> None:
        self.dispense_status = DispenseStatus.DISPENSED
        self.status = TransactionStatus.OPENING_DELIVERY_WINDOW
        self.touch()

    def mark_window_opened(self) -> None:
        self.delivery_status = DeliveryStatus.WINDOW_OPENED
        self.status = TransactionStatus.WAITING_FOR_CUSTOMER_PICKUP
        self.touch()

    def confirm_pickup(self) -> None:
        self.delivery_status = DeliveryStatus.PICKUP_CONFIRMED
        self.status = TransactionStatus.CLOSING_DELIVERY_WINDOW
        self.touch()

    def mark_window_closed(self) -> None:
        self.delivery_status = DeliveryStatus.WINDOW_CLOSED
        self.status = TransactionStatus.COMPLETED
        self.touch()

    def mark_pickup_timed_out_window_closed(self) -> None:
        self.delivery_status = DeliveryStatus.WINDOW_CLOSED
        self.status = TransactionStatus.PICKUP_TIMED_OUT
        self.recovery_status = RecoveryStatus.MANUAL_REVIEW
        self.touch()

    def cancel(self) -> None:
        self._cancelled = True
        self.status = TransactionStatus.CANCELLED
        self.payment_status = PaymentStatus.CANCELLED
        if self.payment_session is not None:
            self.payment_session.cancel()
        self.touch()

    def mark_faulted(self) -> None:
        self.status = TransactionStatus.FAULTED
        self.recovery_status = RecoveryStatus.PENDING
        self.touch()

    def mark_recovery_pending(self) -> None:
        self.recovery_status = RecoveryStatus.PENDING
        self.touch()

    def mark_ambiguous(self) -> None:
        self.status = TransactionStatus.AMBIGUOUS
        self.recovery_status = RecoveryStatus.MANUAL_REVIEW
        self.touch()

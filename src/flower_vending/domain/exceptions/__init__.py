"""Domain exception hierarchy."""


class FlowerVendingError(RuntimeError):
    """Base domain/application error."""

    def __init__(self, message: str = "", *, user_message: str | None = None) -> None:
        super().__init__(message)
        self.user_message = user_message


class DomainValidationError(FlowerVendingError):
    """Raised when domain input data is invalid."""


class InvariantViolationError(FlowerVendingError):
    """Raised when a domain invariant would be broken."""


class IdempotencyViolationError(FlowerVendingError):
    """Raised when a duplicate action would cause a side effect twice."""


class ConcurrencyConflictError(FlowerVendingError):
    """Raised when state changed concurrently."""


class SaleBlockedError(FlowerVendingError):
    """Raised when machine policy blocks a sale."""

    def __init__(self, message: str = "") -> None:
        super().__init__(
            message,
            user_message="Продажи временно приостановлены. Попробуйте позже или обратитесь к администратору.",
        )


class ProductUnavailableError(FlowerVendingError):
    """Raised when the chosen product cannot be sold."""

    def __init__(self, message: str = "") -> None:
        super().__init__(
            message,
            user_message="К сожалению, этот букет только что купили. Взгляните на другие варианты!",
        )


class SlotUnavailableError(FlowerVendingError):
    """Raised when a slot cannot be vended from safely."""


class InventoryMismatchError(FlowerVendingError):
    """Raised when physical and accounting inventory diverge unsafely."""


class PaymentError(FlowerVendingError):
    """Base payment failure."""


class PaymentSessionUnavailableError(PaymentError):
    """Raised when payment session operations are requested without an active session."""


class PaymentCancelledError(PaymentError):
    """Raised when further payment work is requested after cancellation."""


class BillRejectedError(PaymentError):
    """Raised when a bill is rejected."""


class ValidatorUnavailableError(PaymentError):
    """Raised when the bill validator cannot be used safely."""
    def __init__(self, message: str = "") -> None:
        super().__init__(
            message,
            user_message="Приём наличных временно недоступен. Попробуйте оплату картой или повторите позже.",
        )


class ChangeUnavailableError(PaymentError):
    """Raised when safe change cannot be reserved or dispensed."""
    def __init__(self, message: str = "") -> None:
        super().__init__(
            message,
            user_message="Автомат не может выдать сдачу. Пожалуйста, приготовьте точную сумму или выберите другой товар.",
        )


class ExactChangeOnlyViolationError(PaymentError):
    """Raised when a payment would violate exact-change-only policy."""


class PartialPayoutError(PaymentError):
    """Raised when change payout completes only partially."""


class PayoutAmbiguousError(PaymentError):
    """Raised when payout result cannot be proven."""


class DeviceHealthError(FlowerVendingError):
    """Raised when a critical device is unhealthy."""


class ServiceDoorOpenError(DeviceHealthError):
    """Raised when service door is open during customer flow."""


class CriticalTemperatureError(DeviceHealthError):
    """Raised when temperature policy blocks sales."""


class MotorFaultError(DeviceHealthError):
    """Raised when vend mechanism is faulted."""


class DeliveryWindowFaultError(DeviceHealthError):
    """Raised when delivery window control faults."""


class WatchdogFaultError(DeviceHealthError):
    """Raised when watchdog integration fails."""


class RecoveryError(FlowerVendingError):
    """Base recovery error."""


class RecoveryPendingError(RecoveryError):
    """Raised when machine cannot safely leave recovery state."""


class AmbiguousTransactionStateError(RecoveryError):
    """Raised when a transaction outcome cannot be proven."""


class JournalConsistencyError(RecoveryError):
    """Raised when replayed journal facts conflict."""


class ManualInterventionRequiredError(RecoveryError):
    """Raised when operator review is required to proceed."""
    def __init__(self, message: str = "") -> None:
        super().__init__(
            message,
            user_message="Автомат на обслуживании. Пожалуйста, обратитесь к администратору. Приносим извинения!",
        )


class TransactionRecoveryError(RecoveryError):
    """Raised when a restored active transaction is missing from the transaction set."""

"""Transaction registry and coordination helper.

Thread-safety note: This coordinator runs inside a single asyncio event loop,
so coroutine interleaving only happens at await points. All current methods
are synchronous (no I/O) and thus naturally atomic within the loop.
If a future change adds async I/O to any method, add asyncio.Lock.
"""

from __future__ import annotations

from flower_vending.domain.entities import RecoveryStatus, Transaction, TransactionStatus
from flower_vending.domain.exceptions import ConcurrencyConflictError, TerminalLockedError, TransactionRecoveryError
from flower_vending.domain.value_objects import (
    Amount,
    CorrelationId,
    Currency,
    ProductId,
    SlotId,
    TransactionId,
)

# Defined terminal states that permit a new transaction to replace the active one.
# This prevents concurrency conflicts when confirm_pickup() or similar completes a
# transaction but clear_active() hasn't run yet.
_TERMINAL_STATUSES = {
    TransactionStatus.COMPLETED,
    TransactionStatus.CANCELLED,
    TransactionStatus.FAULTED,
    TransactionStatus.AMBIGUOUS,
    TransactionStatus.PICKUP_TIMED_OUT,
}


class TransactionCoordinator:
    def __init__(self) -> None:
        self._transactions: dict[str, Transaction] = {}
        self._active_transaction_id: str | None = None

    def _clear_active_if_terminal(self) -> None:
        if self._active_transaction_id is not None:
            existing = self._transactions.get(self._active_transaction_id)
            if existing is not None:
                if existing.status in {TransactionStatus.FAULTED, TransactionStatus.AMBIGUOUS}:
                    raise TerminalLockedError("terminal is locked due to an unresolved error state")
                elif existing.status in _TERMINAL_STATUSES:
                    self._active_transaction_id = None
                else:
                    raise ConcurrencyConflictError("a transaction is already active")
            else:
                raise ConcurrencyConflictError("a transaction is already active")

    def create_transaction(
        self,
        *,
        correlation_id: str,
        product_id: str,
        slot_id: str,
        price_minor_units: int,
        currency: str = "RUB",
    ) -> Transaction:
        self._ensure_can_create_new_transaction()
        transaction = Transaction(
            transaction_id=TransactionId.new(),
            correlation_id=CorrelationId(correlation_id),
            product_id=ProductId(product_id),
            slot_id=SlotId(slot_id),
            price=Amount(price_minor_units, Currency(currency)),
        )
        self._transactions[transaction.transaction_id.value] = transaction
        self._active_transaction_id = transaction.transaction_id.value
        return transaction

    def _ensure_can_create_new_transaction(self) -> None:
        # Check if existing active transaction is terminal before rejecting.
        # This closes the race window between mark_window_closed() and
        # clear_active() in VendingController.confirm_pickup() (see A4, E2).
        if self._active_transaction_id is not None:
            existing = self._transactions.get(self._active_transaction_id)
            if existing is not None:
                if existing.status in {TransactionStatus.FAULTED, TransactionStatus.AMBIGUOUS}:
                    raise TerminalLockedError("terminal is locked due to an unresolved error state")
                elif existing.status in _TERMINAL_STATUSES:
                    self._active_transaction_id = None
                else:
                    raise ConcurrencyConflictError("a transaction is already active")
            else:
                raise ConcurrencyConflictError("a transaction is already active")

    def get(self, transaction_id: str) -> Transaction | None:
        return self._transactions.get(transaction_id)

    def require(self, transaction_id: str) -> Transaction:
        transaction = self.get(transaction_id)
        if transaction is None:
            raise KeyError(f"unknown transaction: {transaction_id}")
        return transaction

    def active(self) -> Transaction | None:
        if self._active_transaction_id is None:
            return None
        return self._transactions.get(self._active_transaction_id)

    def restore_transactions(
        self,
        transactions: list[Transaction] | tuple[Transaction, ...],
        *,
        active_transaction_id: str | None = None,
    ) -> None:
        # Validate that the active_transaction_id exists in the restored set
        # to ensure consistency and prevent silent None returns from active().
        self._transactions = {
            transaction.transaction_id.value: transaction for transaction in transactions
        }
        if active_transaction_id is not None:
            self._validate_restored_active_transaction(active_transaction_id)
            self._active_transaction_id = active_transaction_id
            return
        for transaction in transactions:
            if transaction.status not in _TERMINAL_STATUSES:
                self._active_transaction_id = transaction.transaction_id.value
                return
        self._active_transaction_id = None

    def _validate_restored_active_transaction(self, active_transaction_id: str) -> None:
        if active_transaction_id not in self._transactions:
            raise TransactionRecoveryError(
                f"active_transaction_id {active_transaction_id} not found in restored set"
            )

    def clear_active(self, transaction_id: str) -> None:
        if self._active_transaction_id == transaction_id:
            self._active_transaction_id = None

    def unresolved_transactions(self) -> list[Transaction]:
        return [
            transaction
            for transaction in self._transactions.values()
            if transaction.recovery_status is not RecoveryStatus.NONE
            or transaction.status.value not in {"completed", "cancelled"}
        ]

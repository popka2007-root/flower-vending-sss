import pytest

from flower_vending.app.orchestrators.transaction_coordinator import TransactionCoordinator
from flower_vending.domain.entities import TransactionStatus
from flower_vending.domain.exceptions import ConcurrencyConflictError


@pytest.mark.parametrize(
    "non_terminal_status",
    [
        TransactionStatus.CREATED,
        TransactionStatus.PICKUP_TIMED_OUT,
    ],
)
def test_create_transaction_fails_if_active_not_terminal(non_terminal_status: TransactionStatus) -> None:
    coordinator = TransactionCoordinator()

    # Create an initial transaction
    txn1 = coordinator.create_transaction(
        correlation_id="corr-1",
        product_id="prod-1",
        slot_id="slot-1",
        price_minor_units=1000,
    )

    # Move it to a non-terminal state
    txn1.status = non_terminal_status

    # Attempt to create a second transaction should fail
    with pytest.raises(ConcurrencyConflictError, match="a transaction is already active"):
        coordinator.create_transaction(
            correlation_id="corr-2",
            product_id="prod-2",
            slot_id="slot-2",
            price_minor_units=2000,
        )


@pytest.mark.parametrize(
    "terminal_status",
    [
        TransactionStatus.COMPLETED,
        TransactionStatus.CANCELLED,
    ],
)
def test_create_transaction_succeeds_if_active_is_terminal(terminal_status: TransactionStatus) -> None:
    coordinator = TransactionCoordinator()

    # Create initial transaction
    txn1 = coordinator.create_transaction(
        correlation_id="corr-1",
        product_id="prod-1",
        slot_id="slot-1",
        price_minor_units=1000,
    )

    # Move it to a terminal state
    txn1.status = terminal_status

    # Ensure it's still tracked as active initially (clear_active hasn't been called)
    assert coordinator._active_transaction_id == txn1.transaction_id.value

    # Attempt to create a new transaction should succeed
    txn2 = coordinator.create_transaction(
        correlation_id="corr-2",
        product_id="prod-2",
        slot_id="slot-2",
        price_minor_units=2000,
    )

    # Active ID should now point to txn2
    assert coordinator._active_transaction_id == txn2.transaction_id.value
    assert coordinator.active() == txn2


@pytest.mark.parametrize(
    "locked_status",
    [
        TransactionStatus.FAULTED,
        TransactionStatus.AMBIGUOUS,
    ],
)
def test_create_transaction_raises_if_active_is_locked(locked_status: TransactionStatus) -> None:
    from flower_vending.domain.exceptions import TerminalLockedError
    coordinator = TransactionCoordinator()

    txn1 = coordinator.create_transaction(
        correlation_id="corr-1",
        product_id="prod-1",
        slot_id="slot-1",
        price_minor_units=1000,
    )

    txn1.status = locked_status

    with pytest.raises(TerminalLockedError):
        coordinator.create_transaction(
            correlation_id="corr-2",
            product_id="prod-2",
            slot_id="slot-2",
            price_minor_units=2000,
        )

def test_restore_transactions_valid_active_id() -> None:
    from flower_vending.domain.entities import Transaction, TransactionStatus
    from flower_vending.domain.value_objects import TransactionId, CorrelationId, ProductId, SlotId, Amount, Currency

    coordinator = TransactionCoordinator()

    txn_id = TransactionId.new()
    txn = Transaction(
        transaction_id=txn_id,
        correlation_id=CorrelationId("corr-1"),
        product_id=ProductId("prod-1"),
        slot_id=SlotId("slot-1"),
        price=Amount(1000, Currency("RUB")),
    )

    coordinator.restore_transactions([txn], active_transaction_id=txn_id.value)

    assert coordinator._active_transaction_id == txn_id.value
    assert coordinator.active() == txn

def test_restore_transactions_invalid_active_id() -> None:
    from flower_vending.domain.exceptions import TransactionRecoveryError
    from flower_vending.domain.entities import Transaction, TransactionStatus
    from flower_vending.domain.value_objects import TransactionId, CorrelationId, ProductId, SlotId, Amount, Currency

    coordinator = TransactionCoordinator()

    txn_id = TransactionId.new()
    txn = Transaction(
        transaction_id=txn_id,
        correlation_id=CorrelationId("corr-1"),
        product_id=ProductId("prod-1"),
        slot_id=SlotId("slot-1"),
        price=Amount(1000, Currency("RUB")),
    )

    with pytest.raises(TransactionRecoveryError, match="not found in restored set"):
        coordinator.restore_transactions([txn], active_transaction_id="non_existent_id")

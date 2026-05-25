import pytest

from flower_vending.app.orchestrators.transaction_coordinator import TransactionCoordinator
from flower_vending.domain.entities import TransactionStatus
from flower_vending.domain.exceptions import ConcurrencyConflictError


def test_create_transaction_fails_if_active_not_terminal():
    coordinator = TransactionCoordinator()

    # Create an initial transaction
    txn1 = coordinator.create_transaction(
        correlation_id="corr-1",
        product_id="prod-1",
        slot_id="slot-1",
        price_minor_units=1000,
    )

    # Its default status is CREATED (which is non-terminal)
    assert txn1.status == TransactionStatus.CREATED

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
        TransactionStatus.PICKUP_TIMED_OUT,
    ],
)
def test_create_transaction_succeeds_if_active_is_terminal(terminal_status):
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
def test_create_transaction_raises_if_active_is_locked(locked_status):
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

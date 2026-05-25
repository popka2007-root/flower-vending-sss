import pytest

from flower_vending.domain.entities.money_inventory import MoneyInventory
from flower_vending.domain.entities.change_reserve import ChangeReserve
from flower_vending.domain.exceptions import DomainValidationError, ChangeUnavailableError
from flower_vending.domain.value_objects import Currency


@pytest.fixture
def inventory() -> MoneyInventory:
    return MoneyInventory(
        currency=Currency("USD"),
        accounting_counts_by_denomination={10: 5, 5: 10, 1: 20},
        reserved_counts_by_denomination={10: 1, 5: 2},
    )


@pytest.mark.asyncio
async def test_reserve_with_negative_values_raises_error(inventory: MoneyInventory) -> None:
    plan = {10: -1, 5: 2}

    # Verify that an exception is raised
    with pytest.raises(DomainValidationError, match="reserve plan cannot contain negative values"):
        await inventory.reserve("txn-123", plan)

    # Verify state remains unchanged
    assert inventory.reserved_counts_by_denomination == {10: 1, 5: 2}
    assert inventory.accounting_counts_by_denomination == {10: 5, 5: 10, 1: 20}


@pytest.mark.asyncio
async def test_consume_with_negative_values_raises_error(inventory: MoneyInventory) -> None:
    reserve = ChangeReserve(
        transaction_id="txn-123",
        reserved_counts_by_denomination={10: -1},
        currency=Currency("USD"),
    )

    # Verify that an exception is raised
    with pytest.raises(DomainValidationError, match="consume plan cannot contain negative values"):
        await inventory.consume(reserve)

    # Verify state remains unchanged
    assert inventory.reserved_counts_by_denomination == {10: 1, 5: 2}
    assert inventory.accounting_counts_by_denomination == {10: 5, 5: 10, 1: 20}


@pytest.mark.asyncio
async def test_reserve_with_zero_values_succeeds(inventory: MoneyInventory) -> None:
    plan = {10: 0, 5: 0}

    reserve = await inventory.reserve("txn-123", plan)

    # Verify successful empty reserve
    assert reserve.reserved_counts_by_denomination == plan

    # State remains the same (no effective change)
    assert inventory.reserved_counts_by_denomination == {10: 1, 5: 2}


@pytest.mark.asyncio
async def test_reserve_with_insufficient_funds_raises_error(inventory: MoneyInventory) -> None:
    plan = {10: 10}  # We only have 5 total, and 1 is reserved (4 available)

    # Verify that an exception is raised
    with pytest.raises(ChangeUnavailableError, match="insufficient change inventory for requested reserve"):
        await inventory.reserve("txn-123", plan)

    # Verify state remains unchanged
    assert inventory.reserved_counts_by_denomination == {10: 1, 5: 2}


@pytest.mark.asyncio
async def test_consume_success(inventory: MoneyInventory) -> None:
    plan = {10: 1, 5: 2}
    reserve = await inventory.reserve("txn-123", plan)

    # Now we have 2 of 10s and 4 of 5s reserved.
    assert inventory.reserved_counts_by_denomination == {10: 2, 5: 4}

    await inventory.consume(reserve)

    # After consume, accounting counts drop, and reserved counts drop
    assert inventory.accounting_counts_by_denomination == {10: 4, 5: 8, 1: 20}
    assert inventory.reserved_counts_by_denomination == {10: 1, 5: 2}

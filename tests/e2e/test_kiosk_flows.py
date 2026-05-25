"""E2E-style kiosk flow tests using the presenter layer and runtime bootstrap.

These tests exercise the full UI-adjacent flow through KioskPresenter +
UiApplicationFacade + SimulationHarness without requiring a Qt display.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from flower_vending.domain.events import DomainEvent
from flower_vending.simulators.harness import SimulationHarness
from flower_vending.ui.navigation import ScreenId
from flower_vending.ui.presenters import KioskPresenter, ScreenRender

PresenterFixture = tuple[KioskPresenter, list[ScreenRender]]


@pytest.fixture
async def harness() -> AsyncIterator[SimulationHarness]:
    h = SimulationHarness.build()
    await h.start()
    yield h
    await h.stop()


@pytest.fixture
async def presenter(harness: SimulationHarness) -> PresenterFixture:
    from flower_vending.ui.facade import UiApplicationFacade

    facade = UiApplicationFacade(harness.core)
    p = KioskPresenter(facade)
    renders: list[ScreenRender] = []
    p.subscribe(lambda r: renders.append(r))
    await p.initialize()
    return p, renders


class TestKioskE2EFlows:
    async def test_home_to_catalog_navigation(
        self, harness: SimulationHarness, presenter: PresenterFixture
    ) -> None:
        p, renders = presenter
        render = await p.show_catalog()
        assert render.screen_id == ScreenId.CATALOG
        assert renders[-1].screen_id == ScreenId.CATALOG

    async def test_product_selection_and_details(
        self, harness: SimulationHarness, presenter: PresenterFixture
    ) -> None:
        p, _ = presenter
        entries = p._facade.catalog_entries()
        assert len(entries) > 0
        first = entries[0]
        render = await p.show_product_details(first.product_id, first.slot_id)
        assert render.screen_id == ScreenId.PRODUCT_DETAILS

    async def test_successful_purchase_flow(
        self, harness: SimulationHarness, presenter: PresenterFixture
    ) -> None:
        p, renders = presenter
        entries = p._facade.catalog_entries()
        first = entries[0]
        await p.show_product_details(first.product_id, first.slot_id)
        render = await p.start_checkout("cash")
        assert render.screen_id in {ScreenId.PAYMENT, ScreenId.NO_CHANGE}

    async def test_cancel_purchase_returns_to_home(
        self, harness: SimulationHarness, presenter: PresenterFixture
    ) -> None:
        p, renders = presenter
        entries = p._facade.catalog_entries()
        first = entries[0]
        await p.show_product_details(first.product_id, first.slot_id)
        await p.start_checkout("cash")
        render = await p.cancel_purchase()
        assert render.screen_id in {ScreenId.HOME, ScreenId.CATALOG}

    async def test_service_mode_entry_and_exit(
        self, harness: SimulationHarness, presenter: PresenterFixture
    ) -> None:
        p, renders = presenter
        render = await p.open_service_mode("test_operator", pin="0000")
        assert render.screen_id == ScreenId.SERVICE
        render = await p.exit_service_mode("test_operator")
        assert render.screen_id == ScreenId.HOME


@pytest.mark.asyncio
class TestKioskFullPurchases:
    async def test_complete_purchase_with_exact_change(self) -> None:
        harness = SimulationHarness.build(
            price_minor_units=500,
            change_inventory={100: 10, 50: 10},
            accepted_bill_denominations=(500, 1000),
        )
        await harness.start()
        try:
            tx_id = await harness.start_purchase(correlation_id="e2e-exact")
            await harness.accept_cash(tx_id, correlation_id="e2e-exact")
            await harness.insert_bill(500, correlation_id="e2e-exact")
            await asyncio.sleep(0.5)
            await harness.confirm_pickup(tx_id, correlation_id="e2e-exact")
            tx = harness.core.transaction_coordinator.get(tx_id)
            assert tx is not None, "transaction should exist after completion"
        finally:
            await harness.stop()

    async def test_cancel_before_payment_returns_cancelled(self) -> None:
        harness = SimulationHarness.build(
            price_minor_units=300,
            change_inventory={100: 5},
            accepted_bill_denominations=(100, 500),
        )
        await harness.start()
        try:
            tx_id = await harness.start_purchase(correlation_id="e2e-cancel")
            await harness.accept_cash(tx_id, correlation_id="e2e-cancel")
            await harness.insert_bill(100, correlation_id="e2e-cancel")
            from flower_vending.domain.commands.purchase_commands import CancelPurchase
            await harness.core.command_bus.dispatch(
                CancelPurchase(correlation_id="e2e-cancel", transaction_id=tx_id)
            )
            tx = harness.core.transaction_coordinator.get(tx_id)
            assert tx is not None
            assert tx.status.value == "cancelled"
        finally:
            await harness.stop()


    async def test_purchase_decrements_slot_quantity(self) -> None:
        harness = SimulationHarness.build(
            price_minor_units=500,
            change_inventory={100: 10},
            accepted_bill_denominations=(500,),
            slot_quantity=2,
        )
        await harness.start()
        try:
            slot = harness.core.inventory_service.get_slot(harness.slot_id)
            assert slot.quantity == 2

            tx_id = await harness.start_purchase(correlation_id="decr-1")
            await harness.accept_cash(tx_id, correlation_id="decr-1")
            await harness.insert_bill(500, correlation_id="decr-1")
            await harness.confirm_pickup(tx_id, correlation_id="decr-1")

            slot = harness.core.inventory_service.get_slot(harness.slot_id)
            assert slot.quantity == 1, f"expected 1, got {slot.quantity}"

            tx_id = await harness.start_purchase(correlation_id="decr-2")
            await harness.accept_cash(tx_id, correlation_id="decr-2")
            await harness.insert_bill(500, correlation_id="decr-2")
            await harness.confirm_pickup(tx_id, correlation_id="decr-2")

            slot = harness.core.inventory_service.get_slot(harness.slot_id)
            assert slot.quantity == 0, f"expected 0, got {slot.quantity}"

            from flower_vending.domain.exceptions import ProductUnavailableError
            from flower_vending.domain.commands.purchase_commands import StartPurchase
            with pytest.raises(ProductUnavailableError):
                await harness.core.command_bus.dispatch(
                    StartPurchase(
                        correlation_id="decr-3",
                        product_id=harness.product_id,
                        slot_id=harness.slot_id,
                        price_minor_units=500,
                    )
                )
        finally:
            await harness.stop()


@pytest.mark.asyncio
class TestKioskStatusScreens:
    async def test_refund_screen_via_refund_requested_event(self) -> None:
        harness = SimulationHarness.build()
        await harness.start()
        try:
            from flower_vending.ui.facade import UiApplicationFacade

            facade = UiApplicationFacade(harness.core)
            p = KioskPresenter(facade)
            renders: list[ScreenRender] = []
            p.subscribe(lambda r: renders.append(r))
            await p.initialize()

            event = DomainEvent(
                event_type="refund_requested",
                correlation_id="test",
                payload={"refund_minor_units": 50000},
            )
            await harness.core.event_bus.publish(event)
            assert len(renders) >= 2
            assert renders[-1].screen_id == ScreenId.REFUND
        finally:
            await harness.stop()

    async def test_manual_review_screen_via_refund_failed_event(self) -> None:
        harness = SimulationHarness.build()
        await harness.start()
        try:
            from flower_vending.ui.facade import UiApplicationFacade

            facade = UiApplicationFacade(harness.core)
            p = KioskPresenter(facade)
            renders: list[ScreenRender] = []
            p.subscribe(lambda r: renders.append(r))
            await p.initialize()

            event = DomainEvent(
                event_type="refund_failed",
                correlation_id="test",
            )
            await harness.core.event_bus.publish(event)
            assert renders[-1].screen_id == ScreenId.MANUAL_REVIEW
        finally:
            await harness.stop()

    async def test_error_screen_via_machine_faulted_event(self) -> None:
        harness = SimulationHarness.build()
        await harness.start()
        try:
            from flower_vending.ui.facade import UiApplicationFacade

            facade = UiApplicationFacade(harness.core)
            p = KioskPresenter(facade)
            renders: list[ScreenRender] = []
            p.subscribe(lambda r: renders.append(r))
            await p.initialize()

            event = DomainEvent(
                event_type="machine_faulted",
                correlation_id="test",
                payload={"faults": ["validator_fault", "motor_fault"]},
            )
            await harness.core.event_bus.publish(event)
            assert renders[-1].screen_id == ScreenId.ERROR
        finally:
            await harness.stop()

    async def test_sales_blocked_screen_via_critical_temperature_event(self) -> None:
        harness = SimulationHarness.build()
        await harness.start()
        try:
            from flower_vending.ui.facade import UiApplicationFacade

            facade = UiApplicationFacade(harness.core)
            p = KioskPresenter(facade)
            renders: list[ScreenRender] = []
            p.subscribe(lambda r: renders.append(r))
            await p.initialize()

            event = DomainEvent(
                event_type="critical_temperature_detected",
                correlation_id="test",
            )
            await harness.core.event_bus.publish(event)
            assert renders[-1].screen_id == ScreenId.SALES_BLOCKED
        finally:
            await harness.stop()

    async def test_exact_change_screen_when_machine_in_exact_change_only(self) -> None:
        harness = SimulationHarness.build()
        await harness.start()
        try:
            from flower_vending.ui.facade import UiApplicationFacade

            facade = UiApplicationFacade(harness.core)
            p = KioskPresenter(facade)
            renders: list[ScreenRender] = []
            p.subscribe(lambda r: renders.append(r))
            await p.initialize()

            harness.core.machine_status_service.set_exact_change_only(True)
            render = await p.show_home()
            assert render.screen_id == ScreenId.EXACT_CHANGE
            assert renders[-1].screen_id == ScreenId.EXACT_CHANGE
        finally:
            await harness.stop()

    async def test_sales_blocked_screen_renders_fallback_action(self) -> None:
        harness = SimulationHarness.build()
        await harness.start()
        try:
            from flower_vending.ui.facade import UiApplicationFacade

            facade = UiApplicationFacade(harness.core)
            p = KioskPresenter(facade)
            renders: list[ScreenRender] = []
            p.subscribe(lambda r: renders.append(r))
            await p.initialize()

            event = DomainEvent(
                event_type="critical_temperature_detected",
                correlation_id="test",
            )
            await harness.core.event_bus.publish(event)
            render = renders[-1]
            assert render.screen_id == ScreenId.SALES_BLOCKED
            model = render.model
            assert model.secondary_action is not None
            assert model.secondary_action.action_id == "open_service"
        finally:
            await harness.stop()

    async def test_error_screen_renders_fallback_actions(self) -> None:
        harness = SimulationHarness.build()
        await harness.start()
        try:
            from flower_vending.ui.facade import UiApplicationFacade

            facade = UiApplicationFacade(harness.core)
            p = KioskPresenter(facade)
            renders: list[ScreenRender] = []
            p.subscribe(lambda r: renders.append(r))
            await p.initialize()

            event = DomainEvent(
                event_type="machine_faulted",
                correlation_id="test",
                payload={"faults": ["device_fault"]},
            )
            await harness.core.event_bus.publish(event)
            render = renders[-1]
            assert render.screen_id == ScreenId.ERROR
            model = render.model
            assert model.primary_action is not None
            assert model.primary_action.action_id == "clear_restricted_state"
            assert model.secondary_action is not None
            assert model.secondary_action.action_id == "open_service"
        finally:
            await harness.stop()

    async def test_refund_screen_renders_fallback_action(self) -> None:
        harness = SimulationHarness.build()
        await harness.start()
        try:
            from flower_vending.ui.facade import UiApplicationFacade

            facade = UiApplicationFacade(harness.core)
            p = KioskPresenter(facade)
            renders: list[ScreenRender] = []
            p.subscribe(lambda r: renders.append(r))
            await p.initialize()

            event = DomainEvent(
                event_type="refund_requested",
                correlation_id="test",
                payload={"refund_minor_units": 25000},
            )
            await harness.core.event_bus.publish(event)
            render = renders[-1]
            assert render.screen_id == ScreenId.REFUND
            model = render.model
            assert model.secondary_action is not None
            assert model.secondary_action.action_id == "open_service"
        finally:
            await harness.stop()

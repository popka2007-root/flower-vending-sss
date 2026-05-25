"""Main Qt window for kiosk — pixel-perfect Figma-aligned."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication, QMainWindow, QStackedWidget

from flower_vending.ui.navigation import ScreenId
from flower_vending.ui.presenters import KioskPresenter, ScreenRender
from flower_vending.ui.theme import current_stylesheet

from flower_vending.ui.views.catalog_screen import CatalogScreenWidget
from flower_vending.ui.views.checkout_flow import CheckoutFlow
from flower_vending.ui.views.delivery_screen import DeliveryScreenWidget
from flower_vending.ui.views.status_screen import StatusScreenWidget
from flower_vending.ui.views.service_screen import ServiceScreenWidget
from flower_vending.ui.views.diagnostics_screen import DiagnosticsScreenWidget
from flower_vending.ui.views.pin_screen import PinScreenWidget
from flower_vending.ui.views.thank_you_screen import ThankYouScreenWidget
from flower_vending.ui.views.admin.admin_shell import AdminShell
from flower_vending.ui.views.admin.orders_tab import OrdersTab
from flower_vending.ui.views.admin.analytics_tab import AnalyticsTab
from flower_vending.ui.views.admin.catalog_tab import CatalogTab
from flower_vending.ui.views.admin.windows_tab import WindowsTab
from flower_vending.ui.views.admin.settings_tab import SettingsTab

logger = logging.getLogger("flower_vending.ui.window")


def _install_cyrillic_font() -> None:
    app = cast(QApplication | None, QApplication.instance())
    if app is None: return
    for p in (Path("C:/Windows/Fonts/arial.ttf"), Path("C:/Windows/Fonts/segoeui.ttf"),
              Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")):
        if p.exists():
            fid = QFontDatabase.addApplicationFont(str(p))
            fams = QFontDatabase.applicationFontFamilies(fid)
            if fams: app.setFont(QFont(fams[0])); return


class KioskMainWindow(QMainWindow):
    def __init__(self, presenter: KioskPresenter, *, window_title: str = "Flower Vending Kiosk",
                 service_visible: bool = False) -> None:
        super().__init__()
        _install_cyrillic_font()
        self._presenter = presenter
        self._presenter.subscribe(self.render_screen)
        self.setWindowTitle(window_title)
        self.resize(1280, 800); self.setMinimumSize(1024, 700)
        self._current_stylesheet = ""
        self._theme_timer = QTimer(self); self._theme_timer.setInterval(60_000)
        self._theme_timer.timeout.connect(self._check_and_update_theme)
        self._check_and_update_theme(); self._theme_timer.start()

        self._stack = QStackedWidget(); self.setCentralWidget(self._stack)

        self._catalog = CatalogScreenWidget()
        self._checkout = CheckoutFlow()
        self._status = StatusScreenWidget()
        self._delivery = DeliveryScreenWidget()
        self._service = ServiceScreenWidget()
        self._diagnostics = DiagnosticsScreenWidget()
        self._pin = PinScreenWidget()
        self._thanks = ThankYouScreenWidget()

        self._admin = AdminShell()
        self._orders_tab = OrdersTab(); self._analytics_tab = AnalyticsTab()
        self._catalog_tab = CatalogTab(); self._windows_tab = WindowsTab()
        self._settings_tab = SettingsTab()
        self._admin.add_tab(ScreenId.ADMIN_ORDERS.value, self._orders_tab)
        self._admin.add_tab(ScreenId.ADMIN_ANALYTICS.value, self._analytics_tab)
        self._admin.add_tab(ScreenId.ADMIN_CATALOG.value, self._catalog_tab)
        self._admin.add_tab(ScreenId.ADMIN_WINDOWS.value, self._windows_tab)
        self._admin.add_tab(ScreenId.ADMIN_SETTINGS.value, self._settings_tab)

        for w in (self._catalog, self._checkout, self._status, self._delivery,
                  self._service, self._diagnostics, self._pin, self._thanks, self._admin):
            self._stack.addWidget(w)

        self._screen_map = {
            ScreenId.HOME: self._catalog,
            ScreenId.CATALOG: self._catalog,
            ScreenId.PAYMENT: self._checkout,
            ScreenId.EXACT_CHANGE: self._status,
            ScreenId.NO_CHANGE: self._status,
            ScreenId.DISPENSING: self._delivery,
            ScreenId.PICKUP: self._delivery,
            ScreenId.REFUND: self._status,
            ScreenId.MANUAL_REVIEW: self._status,
            ScreenId.ERROR: self._status,
            ScreenId.SALES_BLOCKED: self._status,
            ScreenId.RESTRICTED: self._status,
            ScreenId.PIN: self._pin,
            ScreenId.THANK_YOU: self._thanks,
            ScreenId.SERVICE: self._service,
            ScreenId.DIAGNOSTICS: self._diagnostics,
            ScreenId.ADMIN: self._admin, ScreenId.ADMIN_ORDERS: self._admin,
            ScreenId.ADMIN_ANALYTICS: self._admin, ScreenId.ADMIN_CATALOG: self._admin,
            ScreenId.ADMIN_WINDOWS: self._admin, ScreenId.ADMIN_SETTINGS: self._admin,
        }

        self._wire()

    def _wire(self) -> None:
        c = self._catalog
        c.service_requested.connect(lambda: self._run(self._presenter.show_pin_screen()))
        c.checkout_requested.connect(self._on_checkout)
        self._checkout.back_requested.connect(lambda: self._run(self._presenter.show_catalog()))
        self._checkout.pay_confirmed.connect(self._on_pay)
        self._checkout.finish_requested.connect(lambda: (self._catalog.get_cart().clear(), self._run(self._presenter.show_home())))
        self._pin.pin_accepted.connect(lambda pin: self._run(self._presenter.open_service_mode(pin=pin)))
        self._pin.pin_cancelled.connect(lambda: self._run(self._presenter.back()))
        self._status.primary_action_requested.connect(self._handle)
        self._status.secondary_action_requested.connect(self._handle)
        self._delivery.primary_action_requested.connect(self._handle)
        self._service.action_requested.connect(self._handle)
        self._diagnostics.back_requested.connect(lambda: self._run(self._presenter.back()))
        self._diagnostics.recover_requested.connect(lambda tid: self._run(self._presenter.recover_transaction(tid)))
        self._thanks.buy_again.connect(lambda: self._run(self._presenter.show_catalog()))
        self._admin.nav_clicked.connect(self._admin.show_tab)
        self._admin.nav_clicked.connect(lambda sid: self._run(self._presenter.handle_action(sid)))
        self._admin.exit_requested.connect(lambda: self._run(self._presenter.exit_service_mode()))
        for tab in [self._orders_tab, self._analytics_tab, self._catalog_tab, self._windows_tab, self._settings_tab]:
            tab.action_requested.connect(self._handle)

    def _on_checkout(self) -> None:
        cart = self._catalog.get_cart()
        items = [f"{i.title} × {i.quantity}" for i in cart.items]
        self._checkout.set_order_items(items)
        self._checkout.set_cart_total(cart.total_minor)
        self._checkout.reset()
        # Render checkout overlay directly; transaction starts on pay_confirmed.
        self._stack.setCurrentWidget(self._checkout)

    def _on_pay(self, method: str) -> None:
        cart = self._catalog.get_cart()
        self._run(self._presenter.checkout_cart(
            [(i.product_id, i.slot_id) for i in cart.items],
            cart.total_minor
        ))

    async def bootstrap(self) -> ScreenRender:
        return await self._presenter.initialize()

    def handle_inactivity_timeout(self) -> None:
        self._run(self._presenter.show_home())

    def render_screen(self, render: ScreenRender) -> None:
        sid = render.screen_id
        admin_screens = {ScreenId.ADMIN, ScreenId.ADMIN_ORDERS, ScreenId.ADMIN_ANALYTICS,
                         ScreenId.ADMIN_CATALOG, ScreenId.ADMIN_WINDOWS, ScreenId.ADMIN_SETTINGS}

        if sid in admin_screens:
            tab_map = {ScreenId.ADMIN_ORDERS: self._orders_tab, ScreenId.ADMIN_ANALYTICS: self._analytics_tab,
                       ScreenId.ADMIN_CATALOG: self._catalog_tab, ScreenId.ADMIN_WINDOWS: self._windows_tab,
                       ScreenId.ADMIN_SETTINGS: self._settings_tab}
            tab = tab_map.get(sid, self._orders_tab)
            if render.model and hasattr(tab, 'bind'): tab.bind(render.model)
            if sid in (ScreenId.ADMIN_ORDERS, ScreenId.ADMIN) and hasattr(render.model, 'pending_count'):
                self._admin.set_pending_count(render.model.pending_count)
            self._admin.show_tab((sid if sid is not ScreenId.ADMIN else ScreenId.ADMIN_ORDERS).value)
            self._stack.setCurrentWidget(self._admin)
            return

        if sid == ScreenId.PAYMENT:
            if render.model:
                self._checkout.set_cart_total(getattr(render.model, 'price_minor_units', 0))
            self._stack.setCurrentWidget(self._checkout)
            return

        w = self._screen_map.get(sid)
        if w and hasattr(w, 'bind'): w.bind(render.model)
        if w: self._stack.setCurrentWidget(w)
        if sid == ScreenId.PIN: self._pin.reset()

    def _handle(self, action_id: str) -> None:
        self._run(self._presenter.handle_action(action_id))

    def _check_and_update_theme(self) -> None:
        s = current_stylesheet()
        if s != self._current_stylesheet:
            self._current_stylesheet = s
            self.setStyleSheet(s)

    def _run(self, coro: Coroutine[Any, Any, object]) -> None:
        t = asyncio.get_event_loop().create_task(coro)
        t.add_done_callback(lambda d: logger.error("bg_task_failed", exc_info=d.exception()) if d.exception() else None)

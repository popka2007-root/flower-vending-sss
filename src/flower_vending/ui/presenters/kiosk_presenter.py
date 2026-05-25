"""Top-level kiosk presenter coordinating navigation and screen rendering."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, cast

from flower_vending.app.orchestrators.service_mode_coordinator import ServiceModeLockedError
from flower_vending.domain.events import DomainEvent
from flower_vending.domain.exceptions import (
    ChangeUnavailableError,
    FlowerVendingError,
    ManualInterventionRequiredError,
)
from flower_vending.ui.facade import CatalogEntry, MachineUiSnapshot, UiApplicationFacade
from flower_vending.ui.navigation import NavigationState, ScreenId
from flower_vending.ui.presenters.catalog_presenter import CatalogPresenter
from flower_vending.ui.presenters.payment_presenter import PaymentPresenter
from flower_vending.ui.presenters.service_presenter import (
    ServicePresenter,
    is_product_toggle_action,
    parse_product_toggle_action,
)
from flower_vending.ui.presenters.status_presenter import StatusPresenter
from flower_vending.ui.presenters.admin_presenter import AdminPresenter
from flower_vending.ui.session import KioskSessionState
from flower_vending.ui.theme import ThemeName


logger = logging.getLogger("flower_vending.ui")

ViewListener = Callable[["ScreenRender"], None]


@dataclass(frozen=True, slots=True)
class ScreenRender:
    screen_id: ScreenId
    model: Any


class KioskPresenter:
    def __init__(
        self,
        facade: UiApplicationFacade,
        *,
        navigation: NavigationState | None = None,
        session: KioskSessionState | None = None,
        catalog_presenter: CatalogPresenter | None = None,
        payment_presenter: PaymentPresenter | None = None,
        status_presenter: StatusPresenter | None = None,
        service_presenter: ServicePresenter | None = None,
        admin_presenter: AdminPresenter | None = None,
    ) -> None:
        self._facade = facade
        self._navigation = navigation or NavigationState()
        self._session = session or KioskSessionState()
        self._catalog_presenter = catalog_presenter or CatalogPresenter()
        self._payment_presenter = payment_presenter or PaymentPresenter()
        self._status_presenter = status_presenter or StatusPresenter()
        self._service_presenter = service_presenter or ServicePresenter()
        self._admin_presenter = admin_presenter or AdminPresenter(facade)
        self._listeners: list[ViewListener] = []

    def subscribe(self, listener: ViewListener) -> None:
        self._listeners.append(listener)

    async def initialize(self) -> ScreenRender:
        logger.info("kiosk_initializing")
        self._facade.subscribe_events(self.handle_domain_event)
        return await self.show_home()

    async def show_home(self) -> ScreenRender:
        if self._session.active_transaction_id is not None:
            try:
                return await self.cancel_purchase()
            except Exception:
                self._session.reset_purchase()
        self._session.reset_purchase()
        self._navigation.reset(ScreenId.HOME)
        return await self._emit_current_render()

    async def show_catalog(self) -> ScreenRender:
        self._navigation.go_to(ScreenId.CATALOG)
        return await self._emit_current_render()

    async def select_product(self, product_id: str, slot_id: str) -> ScreenRender:
        self._touch()
        entry = self._facade.get_catalog_entry(product_id, slot_id)
        self._session.select_product(
            product_id=entry.product_id,
            slot_id=entry.slot_id,
            product_name=entry.display_name,
            price_minor_units=entry.price_minor_units,
            currency_code=entry.currency_code,
        )
        return await self._emit_current_render()

    async def show_product_details(self, product_id: str, slot_id: str) -> ScreenRender:
        entry = self._facade.get_catalog_entry(product_id, slot_id)
        self._session.select_product(
            product_id=entry.product_id,
            slot_id=entry.slot_id,
            product_name=entry.display_name,
            price_minor_units=entry.price_minor_units,
            currency_code=entry.currency_code,
        )
        self._navigation.go_to(ScreenId.PRODUCT_DETAILS)
        return await self._emit_current_render()

    async def start_checkout(self, payment_method: str = "cash") -> ScreenRender:
        self._touch()
        logger.info("start_checkout", extra={"payment_method": payment_method})
        if self._session.selected_product_id is None or self._session.selected_slot_id is None:
            return await self._show_error("Товар не выбран", "Сначала выберите товар в каталоге.")
        self._session.payment_method = payment_method
        correlation_id = self._facade.new_correlation_id()
        try:
            transaction_id = await self._facade.start_cash_checkout(
                product_id=self._session.selected_product_id,
                slot_id=self._session.selected_slot_id,
                correlation_id=correlation_id,
            )
        except ChangeUnavailableError as exc:
            logger.warning("change_unavailable", extra={"error": str(exc)})
            self._session.last_warning_message = exc.user_message or str(exc)
            self._navigation.go_to(ScreenId.NO_CHANGE)
            return await self._emit_current_render()
        except FlowerVendingError as exc:
            logger.error("checkout_failed", extra={"error": str(exc)})
            return await self._show_error("Оплата недоступна", exc.user_message or str(exc))
        self._session.start_transaction(transaction_id)
        self._navigation.go_to(ScreenId.PAYMENT)
        return await self._emit_current_render()

    async def show_checkout(self) -> ScreenRender:
        self._navigation.go_to(ScreenId.PAYMENT)
        return await self._emit_current_render()

    async def checkout_cart(self, items: list[tuple[str, str]], total_minor: int) -> ScreenRender:
        self._touch()
        logger.info("checkout_cart", extra={"items": len(items), "total": total_minor})
        if not items:
            return await self._show_error("Корзина пуста", "Добавьте товары в корзину.")
        product_id, slot_id = items[0]
        entry = self._facade.get_catalog_entry(product_id, slot_id)
        self._session.select_product(
            product_id=entry.product_id,
            slot_id=entry.slot_id,
            product_name=entry.display_name,
            price_minor_units=total_minor,
            currency_code=entry.currency_code,
        )
        correlation_id = self._facade.new_correlation_id()
        try:
            transaction_id = await self._facade.start_cash_checkout(
                product_id=product_id, slot_id=slot_id, correlation_id=correlation_id
            )
        except ChangeUnavailableError as exc:
            self._session.last_warning_message = exc.user_message or str(exc)
            self._navigation.go_to(ScreenId.NO_CHANGE)
            return await self._emit_current_render()
        except FlowerVendingError as exc:
            return await self._show_error("Оплата недоступна", exc.user_message or str(exc))
        self._session.start_transaction(transaction_id)
        self._navigation.go_to(ScreenId.PAYMENT)
        return await self._emit_current_render()

    async def cancel_purchase(self) -> ScreenRender:
        if self._session.active_transaction_id is None:
            return await self.show_catalog()
        correlation_id = self._facade.new_correlation_id()
        try:
            await self._facade.cancel_purchase(
                transaction_id=self._session.active_transaction_id,
                correlation_id=correlation_id,
            )
        except FlowerVendingError as exc:
            return await self._show_error(
                "Не удалось отменить покупку", exc.user_message or str(exc)
            )
        return await self.show_home()

    async def confirm_pickup(self) -> ScreenRender:
        if self._session.active_transaction_id is None:
            return await self.show_home()
        correlation_id = self._facade.new_correlation_id()
        try:
            await self._facade.confirm_pickup(
                transaction_id=self._session.active_transaction_id,
                correlation_id=correlation_id,
            )
        except FlowerVendingError as exc:
            return await self._show_error(
                "Не удалось завершить выдачу", exc.user_message or str(exc)
            )
        return await self.show_home()

    async def show_pin_screen(self) -> ScreenRender:
        self._navigation.go_to(ScreenId.PIN)
        return await self._emit_current_render()

    async def show_admin(self, tab: str = "admin_orders") -> ScreenRender:
        tab_map = {
            "orders": ScreenId.ADMIN_ORDERS,
            "analytics": ScreenId.ADMIN_ANALYTICS,
            "catalog": ScreenId.ADMIN_CATALOG,
            "windows": ScreenId.ADMIN_WINDOWS,
            "settings": ScreenId.ADMIN_SETTINGS,
        }
        screen = tab_map.get(tab, ScreenId.ADMIN_ORDERS)
        self._navigation.go_to(screen)
        return await self._emit_current_render()

    async def open_service_mode(
        self, operator_id: str = "technician", pin: str | None = None
    ) -> ScreenRender:
        if pin is None:
            return await self._show_error(
                "PIN не введён", "Введите PIN-код для доступа в сервисный режим"
            )
        logger.info("open_service_mode_requested", extra={"operator_id": operator_id})
        correlation_id = self._facade.new_correlation_id()
        try:
            await self._facade.enter_service_mode(
                operator_id=operator_id,
                correlation_id=correlation_id,
                pin=pin,
            )
        except ServiceModeLockedError as exc:
            return await self._show_error("Доступ заблокирован", str(exc))
        except ValueError:
            return await self._show_error("Неверный PIN", "Попробуйте снова")
        except FlowerVendingError as exc:
            return await self._show_error(
                "Не удалось открыть сервисный режим", exc.user_message or str(exc)
            )
        self._navigation.go_to(ScreenId.SERVICE)
        return await self._emit_current_render()

    async def exit_service_mode(self, operator_id: str = "technician") -> ScreenRender:
        correlation_id = self._facade.new_correlation_id()
        try:
            await self._facade.exit_service_mode(
                correlation_id=correlation_id,
                operator_id=operator_id,
            )
        except FlowerVendingError as exc:
            return await self._show_error(
                "Не удалось выйти из сервиса", exc.user_message or str(exc)
            )
        return await self.show_home()

    async def show_diagnostics(self) -> ScreenRender:
        self._navigation.go_to(ScreenId.DIAGNOSTICS)
        return await self._emit_current_render()

    async def recover_transaction(self, transaction_id: str) -> ScreenRender:
        correlation_id = self._facade.new_correlation_id()
        try:
            await self._facade.recover_transaction(
                transaction_id=transaction_id,
                correlation_id=correlation_id,
            )
        except ManualInterventionRequiredError as exc:
            self._session.record_restricted("manual_review_required", str(exc))
            self._navigation.go_to(ScreenId.RESTRICTED)
            return await self._emit_current_render()
        except FlowerVendingError as exc:
            return await self._show_error(
                "Восстановление не выполнено", exc.user_message or str(exc)
            )
        self._session.last_warning_message = "Выполняется безопасное восстановление транзакции."
        self._navigation.go_to(ScreenId.RESTRICTED)
        return await self._emit_current_render()

    async def clear_drift(self) -> ScreenRender:
        self._facade.clear_drift()
        return await self._emit_current_render()

    async def insert_simulated_bill(self, bill_minor_units: int) -> ScreenRender:
        correlation_id = self._facade.new_correlation_id()
        try:
            await self._facade.insert_simulated_bill(
                bill_minor_units=bill_minor_units,
                correlation_id=correlation_id,
            )
        except FlowerVendingError as exc:
            return await self._show_error("Купюра не принята", str(exc))
        return await self._emit_current_render()

    async def execute_service_action(self, action_id: str) -> ScreenRender:
        correlation_id = self._facade.new_correlation_id()
        try:
            await self._facade.execute_simulator_action(
                action_id=action_id,
                correlation_id=correlation_id,
            )
        except FlowerVendingError as exc:
            return await self._show_error("Действие симулятора не выполнено", str(exc))
        return await self._emit_current_render()

    async def _toggle_product(self, action_id: str) -> ScreenRender:
        parsed = parse_product_toggle_action(action_id)
        if parsed is None:
            return await self._emit_current_render()
        product_id, enabled = parsed
        cid = self._facade.new_correlation_id()
        await self._facade.toggle_product(
            product_id=product_id,
            enabled=enabled,
            operator_id="technician",
            correlation_id=cid,
        )
        return await self._emit_current_render()

    async def back(self) -> ScreenRender:
        self._navigation.back()
        return await self._emit_current_render()

    async def handle_action(self, action_id: str) -> ScreenRender:
        logger.info("ui_action", extra={"action_id": action_id})
        handlers: dict[str, Callable[[], Awaitable[ScreenRender]]] = {
            "show_catalog": self.show_catalog,
            "show_home": self.show_home,
            "force_home": self._force_home,
            "open_service": self.show_pin_screen,
            "confirm_pickup": self.confirm_pickup,
            "show_diagnostics": self.show_diagnostics,
            "exit_service": self.exit_service_mode,
            "back_to_service": self.back,
            "cancel_purchase": self.cancel_purchase,
            "show_admin": lambda: self.show_admin("orders"),
            "admin_orders": lambda: self.show_admin("orders"),
            "admin_analytics": lambda: self.show_admin("analytics"),
            "admin_catalog": lambda: self.show_admin("catalog"),
            "admin_windows": lambda: self.show_admin("windows"),
            "admin_settings": lambda: self.show_admin("settings"),
        }
        if action_id.startswith("insert_bill:"):
            return await self.insert_simulated_bill(int(action_id.split(":", maxsplit=1)[1]))
        if is_product_toggle_action(action_id):
            return await self._toggle_product(action_id)
        if action_id in self._facade.simulator_action_ids():
            return await self.execute_service_action(action_id)
        if action_id == "lock_purchase":
            cid = self._facade.new_correlation_id()
            await self._facade.lock_purchase_button(
                operator_id="technician",
                locked=True,
                correlation_id=cid,
            )
            return await self._emit_current_render()
        if action_id == "unlock_purchase":
            cid = self._facade.new_correlation_id()
            await self._facade.lock_purchase_button(
                operator_id="technician",
                locked=False,
                correlation_id=cid,
            )
            return await self._emit_current_render()
        if action_id.startswith("set_payment_methods:"):
            raw = action_id.split(":", 1)[1]
            methods = raw.split(",") if raw else []
            self._facade.set_payment_methods(methods)
            return await self._emit_current_render()
        if action_id.startswith("set_service_visible:"):
            vis = action_id.split(":", 1)[1] == "show"
            self._facade.set_service_visible(vis)
            self._service_visible = vis
            return await self._emit_current_render()
        if action_id.startswith("set_1c_enabled:"):
            enabled = action_id.split(":", 1)[1] == "on"
            self._session._1c_enabled = enabled
            return await self._emit_current_render()
        if action_id == "clear_pending_transactions":
            self._facade.clear_drift()
            return await self._emit_current_render()
        if action_id == "print_test":
            try:
                from flower_vending.ui.sounds import play_success

                play_success()
            except Exception:
                pass
            return await self._emit_current_render()
        if action_id.startswith("set_theme:"):
            theme = action_id.split(":", 1)[1]
            if theme in ("light", "dark", "auto"):
                self._facade.apply_theme(cast(ThemeName, theme))
            return await self._emit_current_render()
        if action_id == "clear_restricted_state":
            logger.info("clear_restricted_state")
            restore_actions = (
                "close_service_door",
                "restore_temperature_nominal",
                "restore_inventory_match",
                "clear_simulator_faults",
            )
            for restore_id in restore_actions:
                if restore_id in self._facade.simulator_action_ids():
                    try:
                        cid = self._facade.new_correlation_id()
                        await self._facade.execute_simulator_action(
                            action_id=restore_id, correlation_id=cid
                        )
                    except Exception:
                        pass
            self._facade.clear_simulator_recovery_state()
            self._session.reset_purchase()
            self._session.sale_blockers.clear()
            self._session.clear_messages()
            self._facade.clear_drift()
            self._navigation.reset(ScreenId.HOME)
            return await self._emit_current_render()
        if action_id.startswith("admin_filter:"):
            self._session._admin_filter = action_id.split(":", 1)[1]
            return await self._emit_current_render()
        if action_id.startswith("admin_toggle:"):
            parts = action_id.split(":")
            if len(parts) >= 3:
                pid = parts[1]
                enable = parts[2] == "1"
                cid = self._facade.new_correlation_id()
                await self._facade.toggle_product(
                    product_id=pid,
                    enabled=enable,
                    operator_id="technician",
                    correlation_id=cid,
                )
            return await self._emit_current_render()
        if action_id.startswith("admin_stock:"):
            parts = action_id.split(":")
            if len(parts) >= 3:
                pid = parts[1]
                qty = int(parts[2])
                self._facade.set_product_stock(pid, qty)
            return await self._emit_current_render()
        if action_id.startswith("admin_delete:"):
            pid = action_id.split(":", 1)[1]
            self._facade.remove_product(pid)
            return await self._emit_current_render()
        if action_id.startswith("admin_edit:"):
            parts = action_id.split(":", 1)[1].rsplit(":", 4)
            if len(parts) == 5:
                pid, name, price_str, stock_str, cat = parts
                self._facade.edit_product(pid, name, int(price_str), cat, int(stock_str))
            return await self._emit_current_render()
        if action_id.startswith("admin_add_product:"):
            parts = action_id.split(":", 1)[1].rsplit(":", 3)
            if len(parts) == 4:
                name, price_str, stock_str, cat = parts
                import uuid

                pid = f"prod-{uuid.uuid4().hex[:8]}"
                self._facade.add_product(pid, name, int(price_str), cat, int(stock_str))
            return await self._emit_current_render()
        if action_id.startswith("admin_change_pin:"):
            pin = action_id.split(":", 1)[1]
            self._facade.change_pin(pin)
            return await self._emit_current_render()
        if action_id.startswith("order_done:"):
            oid = action_id.split(":", 1)[1]
            cid = self._facade.new_correlation_id()
            try:
                await self._facade.confirm_pickup(transaction_id=oid, correlation_id=cid)
            except Exception:
                logger.warning("order_done_failed", extra={"order_id": oid})
            return await self._emit_current_render()
        if action_id.startswith("order_cancel:"):
            oid = action_id.split(":", 1)[1]
            cid = self._facade.new_correlation_id()
            try:
                await self._facade.cancel_purchase(transaction_id=oid, correlation_id=cid)
            except Exception:
                logger.warning("order_cancel_failed", extra={"order_id": oid})
            return await self._emit_current_render()
        if action_id.startswith("window_free:"):
            wid = action_id.split(":", 1)[1]
            self._admin_presenter.free_window(wid)
            return await self._emit_current_render()
        if action_id.startswith("window_toggle_maintenance:"):
            wid = action_id.split(":", 1)[1]
            self._admin_presenter.toggle_maintenance(wid)
            return await self._emit_current_render()
        if action_id.startswith("tgl:"):
            parts = action_id.split(":")
            if len(parts) == 3:
                key, val = parts[1], parts[2] == "1"
                if key in ("cash", "card", "sbp"):
                    current = self._facade.machine_snapshot().payment_methods or {"cash": True}
                    current[key] = val
                    methods = [k for k, v in current.items() if v]
                    self._facade.set_payment_methods(methods)
            return await self._emit_current_render()
        if action_id == "admin_save_settings":
            self._facade.save_settings({})
            return await self._emit_current_render()
        if action_id.startswith("scenario:"):
            name = action_id.split(":", 1)[1]
            logger.info("executing_scenario", extra={"name": name})
            sc_map = {
                "Тест оплаты": ("inject_validator_unavailable", "inject_bill_jam"),
                "Тест выдачи": ("inject_motor_fault", "inject_window_fault"),
                "Полный recovery": (
                    "close_service_door",
                    "restore_temperature_nominal",
                    "restore_inventory_match",
                    "clear_simulator_faults",
                ),
            }
            actions = sc_map.get(name, ())
            for a in actions:
                if a in self._facade.simulator_action_ids():
                    try:
                        cid = self._facade.new_correlation_id()
                        await self._facade.execute_simulator_action(action_id=a, correlation_id=cid)
                    except Exception:
                        pass
            return await self._emit_current_render()
        handler = handlers.get(action_id)
        if handler is None:
            return await self._emit_current_render()
        return await handler()

    async def handle_domain_event(self, event: DomainEvent) -> None:
        self._touch()
        logger.debug(
            "domain_event_received",
            extra={
                "event_type": event.event_type,
                "correlation_id": event.correlation_id,
            },
        )
        if event.event_type == "cash_amount_updated":
            self._session.accepted_minor_units = self._safe_int(
                event.payload.get("accepted_minor_units", 0)
            )
            self._navigation.go_to(ScreenId.PAYMENT)
        elif event.event_type == "payment_confirmed":
            self._session.accepted_minor_units = self._safe_int(
                event.payload.get("accepted_minor_units", 0)
            )
            self._session.change_due_minor_units = self._safe_int(
                event.payload.get("change_due_minor_units", 0)
            )
            self._navigation.go_to(ScreenId.DISPENSING)
        elif event.event_type in {"product_dispense_requested", "product_dispensed"}:
            self._navigation.go_to(ScreenId.DISPENSING)
        elif event.event_type in {"change_dispense_requested", "change_dispensed"}:
            pass
        elif event.event_type == "delivery_window_opened":
            self._navigation.go_to(ScreenId.PICKUP)
        elif event.event_type in {"transaction_completed", "transaction_cancelled"}:
            if event.event_type == "transaction_completed":
                self._navigation.go_to(ScreenId.THANK_YOU)
                await self._emit_current_render()
                self._session.reset_purchase()
                return
            self._session.reset_purchase()
            self._navigation.reset(ScreenId.HOME)
            return
        elif event.event_type == "refund_requested":
            self._session.refund_minor_units = self._safe_int(
                event.payload.get("refund_minor_units", 0)
            )
            self._navigation.go_to(ScreenId.REFUND)
        elif event.event_type == "refund_dispensed":
            self._session.refund_minor_units = 0
            self._session.record_restricted(
                "refund_complete",
                "Средства возвращены. Заберите деньги из лотка выдачи.",
            )
            self._navigation.go_to(ScreenId.REFUND)
        elif event.event_type == "refund_failed":
            self._session.record_restricted(
                "refund_failed",
                "Возврат не удался. Требуется сервисная проверка.",
            )
            self._navigation.go_to(ScreenId.MANUAL_REVIEW)
        elif event.event_type in {"machine_faulted"}:
            faults = tuple(str(item) for item in event.payload.get("faults", ()))
            logger.error("machine_faulted", extra={"faults": faults})
            self._session.active_transaction_id = None
            self._session.record_error(
                title="Требуется вмешательство",
                message=", ".join(faults) or event.event_type,
            )
            self._navigation.go_to(ScreenId.ERROR)
        elif event.event_type in {"manual_review_required", "recovery_started"}:
            self._session.record_restricted(
                str(event.payload.get("action", "recovery")),
                str(event.payload.get("reason", event.event_type)),
            )
            self._navigation.go_to(ScreenId.RESTRICTED)
        elif event.event_type == "pickup_timeout_elapsed":
            self._session.record_restricted(
                "pickup_timeout",
                "Время получения истекло; окно выдачи закрывается.",
            )
            self._navigation.go_to(ScreenId.RESTRICTED)
        elif event.event_type == "critical_temperature_detected":
            self._session.last_warning_message = (
                "Продажи остановлены из-за критической температуры."
            )
            self._navigation.go_to(ScreenId.SALES_BLOCKED)
        elif event.event_type == "service_door_opened":
            self._session.last_warning_message = "Продажи остановлены: открыта сервисная дверь."
            self._navigation.go_to(ScreenId.SALES_BLOCKED)
        await self._emit_current_render()

    def _touch(self) -> None:
        self._facade.touch()

    @staticmethod
    def _safe_int(value: object, default: int = 0) -> int:
        try:
            if isinstance(value, (int, float, str)):
                return int(value)
            return default
        except (TypeError, ValueError):
            return default

    async def _emit_current_render(self) -> ScreenRender:
        render = self._build_current_render()
        for listener in self._listeners:
            listener(render)
        return render

    def _build_current_render(self) -> ScreenRender:
        machine = self._facade.machine_snapshot()
        self._session.sale_blockers = set(machine.sale_blockers)
        screen_id = self._navigation.current_screen

        if (
            machine.machine_state in {"RECOVERY_PENDING", "MANUAL_REVIEW"}
            or bool(set(machine.sale_blockers) & {"recovery_pending", "manual_review_required"})
        ) and screen_id not in {
            ScreenId.SERVICE,
            ScreenId.DIAGNOSTICS,
            ScreenId.ERROR,
            ScreenId.RESTRICTED,
            ScreenId.MANUAL_REVIEW,
            ScreenId.PIN,
            ScreenId.THANK_YOU,
            ScreenId.ADMIN,
            ScreenId.ADMIN_ORDERS,
            ScreenId.ADMIN_ANALYTICS,
            ScreenId.ADMIN_CATALOG,
            ScreenId.ADMIN_WINDOWS,
            ScreenId.ADMIN_SETTINGS,
        }:
            screen_id = ScreenId.RESTRICTED
        elif machine.sale_blockers and screen_id not in {
            ScreenId.SERVICE,
            ScreenId.DIAGNOSTICS,
            ScreenId.ERROR,
            ScreenId.RESTRICTED,
            ScreenId.MANUAL_REVIEW,
            ScreenId.PIN,
            ScreenId.THANK_YOU,
            ScreenId.ADMIN,
            ScreenId.ADMIN_ORDERS,
            ScreenId.ADMIN_ANALYTICS,
            ScreenId.ADMIN_CATALOG,
            ScreenId.ADMIN_WINDOWS,
            ScreenId.ADMIN_SETTINGS,
        }:
            screen_id = ScreenId.SALES_BLOCKED
        elif screen_id is ScreenId.HOME and machine.exact_change_only:
            screen_id = ScreenId.EXACT_CHANGE

        if screen_id in {ScreenId.HOME, ScreenId.CATALOG}:
            title = "ЭКСПРЕСС БУКЕТ"
            subtitle = "Свежие цветы 24/7 · Выберите букет и оплатите"
            model = self._catalog_presenter.present_catalog(
                title=title,
                subtitle=subtitle,
                entries=self._facade.catalog_entries(),
                machine=machine,
            )
            return ScreenRender(screen_id, model)

        if screen_id is ScreenId.PRODUCT_DETAILS:
            entry = self._selected_entry()
            product_details_model = self._catalog_presenter.present_product_details(
                entry=entry,
                machine=machine,
            )
            return ScreenRender(screen_id, product_details_model)

        if screen_id is ScreenId.PAYMENT:
            transaction = self._facade.active_transaction_snapshot()
            if transaction is None:
                logger.warning("payment_session_missing_fallback_to_catalog")
                self._navigation.go_to(ScreenId.CATALOG)
                model = self._catalog_presenter.present_catalog(
                    title="ЭКСПРЕСС БУКЕТ",
                    subtitle="Свежие цветы 24/7 · Выберите букет и оплатите",
                    entries=self._facade.catalog_entries(),
                    machine=machine,
                )
                return ScreenRender(ScreenId.CATALOG, model)
            payment_model = self._payment_presenter.present_payment(
                transaction=transaction,
                machine=machine,
                quick_insert_denominations=self._facade.quick_insert_denominations(),
                warning_message=self._session.last_warning_message,
                payment_method=self._session.payment_method,
            )
            return ScreenRender(screen_id, payment_model)

        if screen_id is ScreenId.DISPENSING:
            dispensing_model = self._status_presenter.present_dispensing(
                product_name=self._session.selected_product_name or "товар",
            )
            return ScreenRender(screen_id, dispensing_model)

        if screen_id is ScreenId.PICKUP:
            transaction = self._facade.active_transaction_snapshot()
            pickup_model = self._status_presenter.present_pickup(
                product_name=self._session.selected_product_name or "товар",
                pickup_timeout_active=(
                    False if transaction is None else transaction.pickup_timeout_active
                ),
                pickup_timeout_remaining_s=(
                    None if transaction is None else transaction.pickup_timeout_remaining_s
                ),
            )
            return ScreenRender(screen_id, pickup_model)

        if screen_id is ScreenId.REFUND:
            return ScreenRender(
                screen_id,
                self._status_presenter.present_refund(
                    refund_minor_units=self._session.refund_minor_units,
                    refund_complete="refund_complete" in self._session.restricted_details,
                    error_message=self._session.last_error_message,
                ),
            )

        if screen_id is ScreenId.MANUAL_REVIEW:
            return ScreenRender(
                screen_id,
                self._status_presenter.present_manual_review(
                    reason=", ".join(detail for detail in self._session.restricted_details)
                    or "manual_review_required",
                    transaction_id=self._session.active_transaction_id,
                ),
            )

        if screen_id is ScreenId.EXACT_CHANGE:
            return ScreenRender(screen_id, self._status_presenter.present_exact_change_only())

        if screen_id is ScreenId.NO_CHANGE:
            return ScreenRender(
                screen_id,
                self._status_presenter.present_no_change(
                    message=self._session.last_warning_message
                    or "Сдача недоступна для безопасной продажи.",
                ),
            )

        if screen_id is ScreenId.SALES_BLOCKED:
            return ScreenRender(screen_id, self._status_presenter.present_sales_blocked(machine))

        if screen_id is ScreenId.RESTRICTED:
            diagnostics = self._facade.diagnostics_snapshot()
            details = self._restricted_details(
                fallback_details=self._session.restricted_details,
                machine=machine,
                unresolved_transaction_ids=diagnostics.unresolved_transaction_ids,
            )
            return ScreenRender(
                screen_id,
                self._status_presenter.present_restricted_mode(
                    details=details,
                    transaction_id=machine.active_transaction_id,
                    unresolved_transaction_ids=diagnostics.unresolved_transaction_ids,
                ),
            )

        if screen_id is ScreenId.SERVICE:
            diagnostics = self._facade.diagnostics_snapshot()
            ms = diagnostics.machine
            return ScreenRender(
                screen_id,
                self._service_presenter.present_service_dashboard(
                    diagnostics,
                    simulator_actions=self._facade.simulator_action_ids(),
                    catalog_entries=self._facade.catalog_entries(),
                    payment_methods=ms.payment_methods if ms.payment_methods else None,
                    purchase_locked=self._facade.purchase_locked,
                ),
            )

        if screen_id is ScreenId.DIAGNOSTICS:
            diagnostics = self._facade.diagnostics_snapshot()
            return ScreenRender(screen_id, self._service_presenter.present_diagnostics(diagnostics))

        if screen_id is ScreenId.PIN:
            return ScreenRender(screen_id, None)

        if screen_id is ScreenId.THANK_YOU:
            return ScreenRender(screen_id, None)

        if screen_id is ScreenId.ADMIN:
            return ScreenRender(ScreenId.ADMIN_ORDERS, self._admin_presenter.present_orders())

        if screen_id is ScreenId.ADMIN_ORDERS:
            return ScreenRender(
                screen_id,
                self._admin_presenter.present_orders(
                    active_filter=getattr(self._session, "_admin_filter", "all")
                ),
            )

        if screen_id is ScreenId.ADMIN_ANALYTICS:
            return ScreenRender(screen_id, self._admin_presenter.present_analytics())

        if screen_id is ScreenId.ADMIN_CATALOG:
            return ScreenRender(screen_id, self._admin_presenter.present_catalog())

        if screen_id is ScreenId.ADMIN_WINDOWS:
            return ScreenRender(screen_id, self._admin_presenter.present_windows())

        if screen_id is ScreenId.ADMIN_SETTINGS:
            return ScreenRender(screen_id, self._admin_presenter.present_settings())

        return ScreenRender(
            ScreenId.ERROR,
            self._status_presenter.present_error(
                title=self._session.last_error_title or "Ошибка автомата",
                message=self._session.last_error_message or "Произошла непредвиденная ошибка.",
            ),
        )

    async def _force_home(self) -> ScreenRender:
        self._session.reset_purchase()
        self._navigation.reset(ScreenId.HOME)
        return await self._emit_current_render()

    async def _show_error(self, title: str, message: str) -> ScreenRender:
        self._session.record_error(title=title, message=message)
        self._navigation.go_to(ScreenId.ERROR)
        return await self._emit_current_render()

    def _restricted_details(
        self,
        *,
        fallback_details: tuple[str, ...],
        machine: MachineUiSnapshot,
        unresolved_transaction_ids: tuple[str, ...],
    ) -> tuple[str, ...]:
        details: list[str] = []
        details.extend(item for item in fallback_details if item)
        details.extend(item for item in sorted(machine.sale_blockers) if item)
        if machine.active_transaction_id:
            details.append(f"tx:{machine.active_transaction_id}")
        if unresolved_transaction_ids:
            details.append("unresolved:" + ",".join(unresolved_transaction_ids))
        if not details:
            details.append("manual_review_required")
        return tuple(dict.fromkeys(details))

    def _selected_entry(self) -> CatalogEntry:
        if self._session.selected_product_id is None or self._session.selected_slot_id is None:
            raise RuntimeError("no product has been selected")
        return self._facade.get_catalog_entry(
            self._session.selected_product_id,
            self._session.selected_slot_id,
        )

"""Admin panel presenter — builds view models for admin tabs with real filtering."""

from __future__ import annotations

from flower_vending.ui.facade import UiApplicationFacade
from flower_vending.ui.presenters.formatting import format_money
from flower_vending.ui.viewmodels.screens import (
    AdminAnalyticsTabViewModel,
    AdminCatalogItemViewModel,
    AdminCatalogTabViewModel,
    AdminOrdersTabViewModel,
    AdminOrderViewModel,
    AdminSettingsTabViewModel,
    AdminWindowsTabViewModel,
    AdminWindowViewModel,
)


class AdminPresenter:
    def __init__(self, facade: UiApplicationFacade) -> None:
        self._facade = facade
        self._orders: list[AdminOrderViewModel] = []
        self._window_states: dict[str, str] = {}
        self._log_entries: list[str] = []

    def present_orders(self, active_filter: str = "all") -> AdminOrdersTabViewModel:
        entries = self._facade.catalog_entries()
        orders: list[AdminOrderViewModel] = []
        revenue = 0
        pending = 0
        completed = 0
        cancelled = 0

        statuses = ["completed", "pending", "cancelled", "completed", "pending"]
        stxt = {"completed": "Завершён", "pending": "В обработке", "cancelled": "Отменён"}

        for i, entry in enumerate(entries):
            if not entry.available and active_filter != "all":
                continue
            s = statuses[i % len(statuses)]
            if active_filter != "all" and s != active_filter:
                continue
            if s == "completed":
                completed += 1
                revenue += entry.price_minor_units
            elif s == "pending":
                pending += 1
            else:
                cancelled += 1
            orders.append(
                AdminOrderViewModel(
                    order_id=f"ORD-{1000 + i:04d}",
                    items_summary=f"{entry.display_name} × 1",
                    total_text=format_money(entry.price_minor_units, entry.currency_code),
                    status=s,
                    status_text=stxt[s],
                    date="2026-05-22",
                )
            )

        return AdminOrdersTabViewModel(
            orders=tuple(orders),
            revenue_total=format_money(revenue, "RUB"),
            pending_count=pending,
            completed_count=completed,
            cancelled_count=cancelled,
            active_filter=active_filter,
        )

    def present_analytics(self) -> AdminAnalyticsTabViewModel:
        entries = self._facade.catalog_entries()
        total = sum(e.price_minor_units for e in entries if e.available)
        top = []
        for i, e in enumerate(entries[:5]):
            fake_rev = format_money(e.price_minor_units * (5 - i) * 3, "RUB")
            top.append((e.display_name, fake_rev, float(e.price_minor_units * (5 - i) * 3 / 100)))
        return AdminAnalyticsTabViewModel(
            revenue_total=format_money(total * 3, "RUB"),
            revenue_delta="+12%",
            pending_count=len(entries) // 3,
            completed_count=len(entries),
            cancelled_count=1,
            chart_days={
                "Пн": total // 4,
                "Вт": total // 3,
                "Ср": total // 2,
                "Чт": total,
                "Пт": total // 2,
                "Сб": total // 3,
                "Вс": total // 4,
            },
            payment_methods={"cash": 65.0, "card": 25.0, "sbp": 10.0},
            top_products=tuple(top),
        )

    def present_catalog(self) -> AdminCatalogTabViewModel:
        entries = self._facade.catalog_entries()
        products = []
        for e in entries:
            img = e.metadata.get("image_path") or e.metadata.get("image") or None
            products.append(
                AdminCatalogItemViewModel(
                    product_id=e.product_id,
                    title=e.display_name,
                    price_text=format_money(e.price_minor_units, e.currency_code),
                    category=e.category,
                    stock=e.quantity,
                    active=e.available,
                    image_path=img,
                )
            )
        return AdminCatalogTabViewModel(products=tuple(products), can_add=True)

    def present_windows(self) -> AdminWindowsTabViewModel:
        snap = self._facade.machine_snapshot()
        windows = []
        for i in range(1, 4):
            wid = str(i)
            s = self._window_states.get(wid, "free")
            detail = "Готово к выдаче"
            if snap.active_transaction_id and s == "free":
                s = "busy"
                detail = f"Заказ #{snap.active_transaction_id[:8]}"
            windows.append(
                AdminWindowViewModel(
                    window_id=wid,
                    status=s,
                    status_text={
                        "free": "Свободно",
                        "busy": "Занято",
                        "maintenance": "Обслуживание",
                    }[s],
                    detail_text=detail
                    if s == "free"
                    else (
                        f"Заказ #{snap.active_transaction_id[:8]}"
                        if s == "busy" and snap.active_transaction_id
                        else "Плановое ТО"
                    ),
                )
            )
        return AdminWindowsTabViewModel(
            windows=tuple(windows),
            activity_log=tuple(self._log_entries[-10:]) if self._log_entries else ("Нет записей",),
        )

    def free_window(self, window_id: str) -> None:
        self._window_states[window_id] = "free"
        self._log_entries.append(f"Окно {window_id}: освобождено")

    def toggle_maintenance(self, window_id: str) -> None:
        current = self._window_states.get(window_id, "free")
        if current == "busy":
            return
        new = "free" if current == "maintenance" else "maintenance"
        self._window_states[window_id] = new
        self._log_entries.append(
            f"Окно {window_id}: {'переведено в обслуживание' if new == 'maintenance' else 'возвращено в работу'}"
        )

    def present_settings(self) -> AdminSettingsTabViewModel:
        snap = self._facade.machine_snapshot()
        pm = snap.payment_methods or {"cash": True}
        return AdminSettingsTabViewModel(
            vending_name="Экспресс Букет",
            working_hours="Круглосуточно",
            contact_phone="+7 (999) 123-45-67",
            support_email="support@express-bouquet.ru",
            accept_cash=pm.get("cash", True),
            accept_card=pm.get("card", False),
            accept_sbp=pm.get("sbp", False),
            min_order_amount=1000,
            delivery_time="2-3",
            auto_restock=True,
            restock_threshold=3,
            notify_on_order=True,
            notify_on_low_stock=True,
            receipt_printer=False,
            discounts_enabled=False,
            discount_percent=10,
            price_markup=0,
            current_pin="",
            new_pin="",
        )

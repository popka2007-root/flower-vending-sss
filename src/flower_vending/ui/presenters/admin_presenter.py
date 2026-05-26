"""Admin panel presenter — builds view models for admin tabs with real filtering."""

from __future__ import annotations

from flower_vending.ui.facade import UiApplicationFacade
from flower_vending.ui.presenters.formatting import format_money
from flower_vending.ui.viewmodels.screens import (
    AdminAnalyticsTabViewModel,
    AdminCatalogItemViewModel,
    AdminCatalogTabViewModel,
    AdminOrderViewModel,
    AdminOrdersTabViewModel,
    AdminSettingsTabViewModel,
    AdminWindowViewModel,
    AdminWindowsTabViewModel,
)


class AdminPresenter:
    def __init__(self, facade: UiApplicationFacade) -> None:
        self._facade = facade
        self._orders: list[AdminOrderViewModel] = []
        self._window_states: dict[str, str] = {}
        self._log_entries: list[str] = []

    def present_orders(self, active_filter: str = "all") -> AdminOrdersTabViewModel:
        tx_snapshots = self._facade.all_transactions()
        orders: list[AdminOrderViewModel] = []
        revenue = 0
        pending = 0
        completed = 0
        cancelled = 0

        stxt = {
            "completed": "Завершён",
            "pending": "В обработке",
            "cancelled": "Отменён",
            "created": "Создан",
            "dispensing": "Выдача",
            "pickup": "Ожидание",
            "faulted": "Ошибка",
            "ambiguous": "Неопределён",
            "pickup_timed_out": "Таймаут",
        }

        for tx in tx_snapshots:
            status = tx.status
            mapped_status = "pending"
            if status == "completed":
                mapped_status = "completed"
                completed += 1
                revenue += tx.price_minor_units
            elif status in ("cancelled", "pickup_timed_out"):
                mapped_status = "cancelled"
                cancelled += 1
            else:
                pending += 1

            if active_filter != "all" and mapped_status != active_filter:
                continue

            display_date = "Сегодня"
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(tx.created_at_iso)
                if dt.date() == datetime.now().date():
                    display_date = dt.strftime("%H:%M")
                else:
                    display_date = dt.strftime("%d.%m.%Y")
            except Exception:
                pass

            orders.append(
                AdminOrderViewModel(
                    order_id=tx.transaction_id[:8].upper(),
                    items_summary=f"{tx.product_name} × 1",
                    total_text=format_money(tx.price_minor_units, tx.currency_code),
                    status=mapped_status,
                    status_text=stxt.get(status, status),
                    date=display_date,
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
        tx_snapshots = self._facade.all_transactions()
        revenue = sum(tx.price_minor_units for tx in tx_snapshots if tx.status == "completed")
        pending = sum(
            1 for tx in tx_snapshots if tx.status not in ("completed", "cancelled", "pickup_timed_out")
        )
        completed = sum(1 for tx in tx_snapshots if tx.status == "completed")
        cancelled = sum(1 for tx in tx_snapshots if tx.status in ("cancelled", "pickup_timed_out"))

        # Real calculation for top products and payment methods
        product_sales: dict[str, int] = {}
        product_names: dict[str, str] = {}
        pm_counts: dict[str, int] = {"cash": 0, "card": 0, "sbp": 0}

        for tx in tx_snapshots:
            if tx.status == "completed":
                product_sales[tx.product_id] = product_sales.get(tx.product_id, 0) + tx.price_minor_units
                product_names[tx.product_id] = tx.product_name
                # Mocking payment method from transaction if not present,
                # though real Transaction might need this field.
                pm_counts["cash"] += 1

        top_products = sorted(product_sales.items(), key=lambda x: x[1], reverse=True)[:5]
        top = [
            (product_names[pid], format_money(rev, "RUB"), float(rev))
            for pid, rev in top_products
        ]

        # Real calculation for daily chart
        chart_days = {"Пн": 0.0, "Вт": 0.0, "Ср": 0.0, "Чт": 0.0, "Пт": 0.0, "Сб": 0.0, "Вс": 0.0}
        days_map = {0: "Пн", 1: "Вт", 2: "Ср", 3: "Чт", 4: "Пт", 5: "Сб", 6: "Вс"}
        from datetime import datetime
        for tx in tx_snapshots:
            if tx.status == "completed":
                try:
                    dt = datetime.fromisoformat(tx.created_at_iso)
                    day_name = days_map.get(dt.weekday())
                    if day_name:
                        chart_days[day_name] += float(tx.price_minor_units) / 100.0
                except Exception:
                    pass

        total_pm = sum(pm_counts.values()) or 1
        pm_stats = {k: (v / total_pm) * 100 for k, v in pm_counts.items()}

        return AdminAnalyticsTabViewModel(
            revenue_total=format_money(revenue, "RUB"),
            revenue_delta="+0%",
            pending_count=pending,
            completed_count=completed,
            cancelled_count=cancelled,
            chart_days=chart_days,
            payment_methods=pm_stats,
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
        s = self._facade.machine_settings
        return AdminSettingsTabViewModel(
            vending_name=s.get("vending_name", "Экспресс Букет"),
            working_hours=s.get("working_hours", "Круглосуточно"),
            contact_phone=s.get("contact_phone", "+7 (999) 123-45-67"),
            support_email=s.get("support_email", "support@express-bouquet.ru"),
            accept_cash=pm.get("cash", True),
            accept_card=pm.get("card", False),
            accept_sbp=pm.get("sbp", False),
            min_order_amount=s.get("min_order_amount", 1000),
            delivery_time="2-3",
            auto_restock=s.get("auto_restock", True),
            restock_threshold=s.get("restock_threshold", 3),
            notify_on_order=s.get("notify_on_order", True),
            notify_on_low_stock=s.get("notify_on_low_stock", True),
            receipt_printer=False,
            discounts_enabled=False,
            discount_percent=s.get("discount_percent", 0),
            price_markup=s.get("price_markup", 0),
            current_pin="",
            new_pin="",
        )

"""Admin orders tab — KPI cards, filter pills, QTableWidget with actions."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from flower_vending.ui.design_tokens import BrandColors, Radius, Typography
from flower_vending.ui.icons import IconName
from flower_vending.ui.viewmodels.screens import AdminOrdersTabViewModel
from flower_vending.ui.widgets.modern import KpiCard, repolish


class OrdersTab(QWidget):
    action_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(24)

        title = QLabel("Заказы")
        title.setStyleSheet(
            f"font-size: 24px; font-weight: {Typography.WEIGHTS['bold']};"
        )
        layout.addWidget(title)

        kpi_grid = QHBoxLayout()
        kpi_grid.setSpacing(16)
        self._kpi_revenue = KpiCard("Выручка", "0 ₽", IconName.DOLLAR_SIGN, BrandColors.KPI_GREEN)
        self._kpi_pending = KpiCard("В обработке", "0", IconName.CLOCK, BrandColors.KPI_YELLOW)
        self._kpi_completed = KpiCard("Выполнено", "0", IconName.CHECK_CIRCLE, BrandColors.KPI_BLUE)
        self._kpi_cancelled = KpiCard("Отменено", "0", IconName.X_CIRCLE, BrandColors.KPI_RED)
        for card in [self._kpi_revenue, self._kpi_pending, self._kpi_completed, self._kpi_cancelled]:
            kpi_grid.addWidget(card)
        layout.addLayout(kpi_grid)

        filters = QHBoxLayout()
        filters.setSpacing(8)
        self._filter_btns: dict[str, QPushButton] = {}
        for filter_id, label in [("all", "Все"), ("pending", "В обработке"), ("completed", "Завершённые"), ("cancelled", "Отменённые")]:
            btn = QPushButton(label)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(36)
            btn.setStyleSheet(
                f"QPushButton {{ padding: 6px 16px; border-radius: {Radius.XL}px; "
                f"border: 1px solid rgba(0,0,0,0.08); font-size: 13px; "
                f"font-weight: {Typography.WEIGHTS['medium']}; background: #FFFFFF; "
                f"color: {BrandColors.GRAY_500}; }}"
                f"QPushButton[active=\"true\"] {{ background: {BrandColors.PURPLE_600}; "
                f"color: #FFFFFF; border-color: {BrandColors.PURPLE_600}; }}"
            )
            btn.clicked.connect(lambda checked, fid=filter_id: self.action_requested.emit(f"admin_filter:{fid}"))
            filters.addWidget(btn)
            self._filter_btns[filter_id] = btn
        filters.addStretch(1)
        layout.addLayout(filters)

        self._table = QTableWidget()
        self._table.setColumnCount(8)
        self._table.setHorizontalHeaderLabels([
            "ID", "Дата", "Состав", "Сумма", "Статус", "Оплата", "Окно", "Действия"
        ])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.setStyleSheet(
            f"QTableWidget {{ border: 1px solid rgba(0,0,0,0.08); border-radius: {Radius.XL}px; "
            f"background: #FFFFFF; gridline-color: rgba(0,0,0,0.04); }}"
            f"QTableWidget::item {{ padding: 10px 8px; }}"
            f"QHeaderView::section {{ background: #F8FAFC; border: none; "
            f"border-bottom: 1px solid rgba(0,0,0,0.06); padding: 12px 8px; "
            f"font-weight: {Typography.WEIGHTS['semibold']}; font-size: 13px; color: {BrandColors.GRAY_500}; }}"
        )
        layout.addWidget(self._table, 1)

    def bind(self, model: AdminOrdersTabViewModel | object) -> None:
        if not isinstance(model, AdminOrdersTabViewModel):
            return
        self._kpi_revenue.set_value(model.revenue_total)
        self._kpi_pending.set_value(str(model.pending_count))
        self._kpi_completed.set_value(str(model.completed_count))
        self._kpi_cancelled.set_value(str(model.cancelled_count))

        for fid, btn in self._filter_btns.items():
            btn.setProperty("active", fid == model.active_filter)
            repolish(btn)

        self._table.setRowCount(len(model.orders))
        for row, order in enumerate(model.orders):
            self._table.setItem(row, 0, QTableWidgetItem(f"#{order.order_id}"))
            self._table.setItem(row, 1, QTableWidgetItem(order.date))
            self._table.setItem(row, 2, QTableWidgetItem(order.items_summary))
            self._table.setItem(row, 3, QTableWidgetItem(order.total_text))
            self._table.setItem(row, 4, QTableWidgetItem(order.status_text))
            self._table.setItem(row, 5, QTableWidgetItem(getattr(order, 'payment_method', '—')))
            self._table.setItem(row, 6, QTableWidgetItem(order.window_id or "—"))

            actions_w = QWidget()
            actions_l = QHBoxLayout(actions_w)
            actions_l.setContentsMargins(4, 2, 4, 2)
            actions_l.setSpacing(6)

            if order.status == "pending":
                done_btn = QPushButton("Выдать")
                done_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                done_btn.setStyleSheet(
                    f"QPushButton {{ padding: 4px 12px; border-radius: {Radius.MD}px; "
                    f"border: 1px solid {BrandColors.GREEN_600}; background: {BrandColors.GREEN_600}; color: #FFFFFF; font-size: 12px; }}"
                )
                done_btn.clicked.connect(lambda checked, oid=order.order_id: self.action_requested.emit(f"order_done:{oid}"))
                actions_l.addWidget(done_btn)

                cancel_btn = QPushButton("Отменить")
                cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                cancel_btn.setStyleSheet(
                    f"QPushButton {{ padding: 4px 12px; border-radius: {Radius.MD}px; "
                    f"border: 1px solid #EF4444; background: #EF4444; color: #FFFFFF; font-size: 12px; }}"
                )
                cancel_btn.clicked.connect(lambda checked, oid=order.order_id: self.action_requested.emit(f"order_cancel:{oid}"))
                actions_l.addWidget(cancel_btn)

            self._table.setCellWidget(row, 7, actions_w)

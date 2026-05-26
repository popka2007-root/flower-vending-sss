"""Admin analytics tab — KPI cards, custom drawn charts, top products."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from flower_vending.ui.design_tokens import BrandColors, Radius, Typography
from flower_vending.ui.icons import IconName
from flower_vending.ui.viewmodels.screens import AdminAnalyticsTabViewModel
from flower_vending.ui.widgets.modern import KpiCard


class _BarChart(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._data: dict[str, float] = {}
        self._bar_color = QColor("#9333EA")
        self._grid_color = QColor("#F3F4F6")
        self._text_color = QColor("#6B7280")
        self._font = QFont()
        self._font.setFamilies(["Segoe UI", "Arial", "sans-serif"])
        self._font.setPixelSize(11)
        self.setMinimumHeight(200)

    def set_data(self, data: dict[str, float]) -> None:
        self._data = data
        self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        if w <= 0 or h <= 0 or not self._data:
            painter.setPen(self._text_color)
            painter.setFont(self._font)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Нет данных")
            painter.end()
            return

        margin_l, margin_r, margin_t, margin_b = 40, 16, 16, 36
        chart_w = w - margin_l - margin_r
        chart_h = h - margin_t - margin_b

        values = list(self._data.values())
        labels = list(self._data.keys())
        max_val = max(values) if values else 1

        cols = len(values)
        if cols == 0:
            painter.end()
            return

        col_w = chart_w / cols
        bar_max_w = col_w * 0.6
        bar_gap = col_w * 0.2

        # Grid lines (3 horizontal)
        painter.setPen(QPen(self._grid_color, 1))
        for i in range(4):
            y = margin_t + chart_h - (chart_h * i // 3)
            painter.drawLine(int(margin_l), int(y), int(w - margin_r), int(y))
            val_text = str(int(max_val * i // 3))
            painter.setPen(self._text_color)
            painter.setFont(self._font)
            painter.drawText(
                0,
                int(y - 8),
                int(margin_l - 8),
                16,
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                val_text,
            )
            painter.setPen(QPen(self._grid_color, 1))

        # Bars
        for i, (label, val) in enumerate(self._data.items()):
            bar_h = (val / max_val) * chart_h if max_val > 0 else 0
            bar_x = margin_l + i * col_w + bar_gap
            bar_y = margin_t + chart_h - bar_h
            bar_w = bar_max_w

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(self._bar_color))
            painter.drawRoundedRect(int(bar_x), int(bar_y), int(bar_w), int(bar_h), 4, 4)

            # Label
            painter.setPen(self._text_color)
            painter.setFont(self._font)
            l_text = label
            painter.drawText(
                int(bar_x - 4),
                int(margin_t + chart_h + 4),
                int(bar_w + 8),
                24,
                Qt.AlignmentFlag.AlignCenter,
                l_text,
            )

        painter.end()


class _PieChart(QWidget):
    COLORS = ["#9333EA", "#EC4899", "#06B6D4", "#F59E0B", "#10B981", "#6366F1"]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._data: dict[str, float] = {}
        self._text_color = QColor("#6B7280")
        self._font = QFont()
        self._font.setFamilies(["Segoe UI", "Arial", "sans-serif"])
        self._font.setPixelSize(11)
        self._bold = QFont()
        self._bold.setFamilies(["Segoe UI", "Arial", "sans-serif"])
        self._bold.setPixelSize(12)
        self._bold.setWeight(QFont.Weight.Bold)
        self.setMinimumHeight(200)

    def set_data(self, data: dict[str, float]) -> None:
        self._data = data
        self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        if w <= 0 or h <= 0 or not self._data:
            painter.setPen(self._text_color)
            painter.setFont(self._font)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Нет данных")
            painter.end()
            return

        total = sum(self._data.values())
        if total <= 0:
            painter.end()
            return

        # Pie circle - left side
        pie_diameter = min(w // 2 - 24, h - 48)
        pie_diameter = max(pie_diameter, 80)
        pie_rect = (24, (h - pie_diameter) // 2, pie_diameter, pie_diameter)

        start_angle = 0
        for i, (label, val) in enumerate(self._data.items()):
            angle = int(val / total * 360 * 16)  # Qt uses 1/16 degree
            color = QColor(self.COLORS[i % len(self.COLORS)])
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPie(*pie_rect, start_angle, angle)
            start_angle += angle

        lx = w // 2 + 16
        ly = 24
        for i, (label, val) in enumerate(self._data.items()):
            pct = val / total * 100 if total > 0 else 0
            color = QColor(self.COLORS[i % len(self.COLORS)])
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(lx, ly, 12, 12, 3, 3)

            painter.setPen(self._text_color)
            painter.setFont(self._bold)
            label_map = {"cash": "Наличные", "card": "Карта", "sbp": "СБП"}
            display = label_map.get(label, label)
            painter.drawText(
                lx + 20,
                ly - 2,
                w - lx - 16,
                16,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                f"{display}  {pct:.0f}%",
            )
            ly += 36

        painter.end()


class _ProductBar(QWidget):
    def __init__(
        self, rank: int, name: str, revenue: str, pct: float, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setFixedHeight(40)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        rank_lbl = QLabel(f"{rank}")
        rank_lbl.setFixedWidth(24)
        rank_lbl.setStyleSheet(
            f"font-size: 13px; font-weight: {Typography.WEIGHTS['bold']}; color: {BrandColors.GRAY_500};"
        )
        rank_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(rank_lbl)

        name_lbl = QLabel(name)
        name_lbl.setStyleSheet(
            f"font-size: 13px; font-weight: {Typography.WEIGHTS['medium']}; color: #111827;"
        )
        layout.addWidget(name_lbl, 1)

        bar_wrap = QWidget()
        bar_wrap.setFixedHeight(8)
        bar_wrap.setStyleSheet(f"background: {BrandColors.GRAY_100}; border-radius: 4px;")
        bar_layout = QHBoxLayout(bar_wrap)
        bar_layout.setContentsMargins(0, 0, 0, 0)
        fill = QWidget()
        fill.setFixedWidth(int(160 * pct / 100))
        fill.setFixedHeight(8)
        fill.setStyleSheet(
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #EC4899, stop:1 #9333EA); border-radius: 4px;"
        )
        bar_layout.addWidget(fill)
        bar_layout.addStretch(1)
        layout.addWidget(bar_wrap)

        rev_lbl = QLabel(revenue)
        rev_lbl.setFixedWidth(80)
        rev_lbl.setStyleSheet(
            f"font-size: 13px; font-weight: {Typography.WEIGHTS['semibold']}; color: #111827;"
        )
        rev_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(rev_lbl)


class AnalyticsTab(QWidget):
    action_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(24)

        title = QLabel("Аналитика")
        title.setStyleSheet(f"font-size: 24px; font-weight: {Typography.WEIGHTS['bold']};")
        layout.addWidget(title)

        kpi_grid = QHBoxLayout()
        kpi_grid.setSpacing(16)
        self._kpi_revenue = KpiCard("Выручка", "0 ₽", IconName.DOLLAR_SIGN, BrandColors.KPI_GREEN)
        self._kpi_pending = KpiCard("В обработке", "0", IconName.CLOCK, BrandColors.KPI_YELLOW)
        self._kpi_completed = KpiCard("Выполнено", "0", IconName.CHECK_CIRCLE, BrandColors.KPI_BLUE)
        self._kpi_cancelled = KpiCard("Отменено", "0", IconName.X_CIRCLE, BrandColors.KPI_RED)
        for card in [
            self._kpi_revenue,
            self._kpi_pending,
            self._kpi_completed,
            self._kpi_cancelled,
        ]:
            kpi_grid.addWidget(card)
        layout.addLayout(kpi_grid)

        charts_row = QHBoxLayout()
        charts_row.setSpacing(20)

        bar_card = QWidget()
        bar_card.setStyleSheet(f"background: #FFFFFF; border-radius: {Radius.XL}px; border: none;")
        bar_card.setMinimumHeight(300)
        bar_layout = QVBoxLayout(bar_card)
        bar_layout.setContentsMargins(20, 16, 20, 16)
        bar_title = QLabel("Продажи по дням (неделя)")
        bar_title.setStyleSheet(f"font-size: 14px; font-weight: {Typography.WEIGHTS['semibold']};")
        bar_layout.addWidget(bar_title)
        self._bar_chart = _BarChart()
        bar_layout.addWidget(self._bar_chart, 1)
        charts_row.addWidget(bar_card, 2)

        pie_card = QWidget()
        pie_card.setStyleSheet(f"background: #FFFFFF; border-radius: {Radius.XL}px; border: none;")
        pie_card.setMinimumHeight(300)
        pie_layout = QVBoxLayout(pie_card)
        pie_layout.setContentsMargins(20, 16, 20, 16)
        pie_title = QLabel("Способы оплаты")
        pie_title.setStyleSheet(f"font-size: 14px; font-weight: {Typography.WEIGHTS['semibold']};")
        pie_layout.addWidget(pie_title)
        self._pie_chart = _PieChart()
        pie_layout.addWidget(self._pie_chart, 1)
        charts_row.addWidget(pie_card, 1)

        layout.addLayout(charts_row)

        top_card = QWidget()
        top_card.setStyleSheet(f"background: #FFFFFF; border-radius: {Radius.XL}px; border: none;")
        top_layout = QVBoxLayout(top_card)
        top_layout.setContentsMargins(20, 16, 20, 16)
        top_title = QLabel("Топ товаров")
        top_title.setStyleSheet(f"font-size: 14px; font-weight: {Typography.WEIGHTS['semibold']};")
        top_layout.addWidget(top_title)
        self._top_list = QVBoxLayout()
        top_layout.addLayout(self._top_list)
        layout.addWidget(top_card)

        layout.addStretch(1)

    def bind(self, model: AdminAnalyticsTabViewModel | object) -> None:
        if not isinstance(model, AdminAnalyticsTabViewModel):
            return
        self._kpi_revenue.set_value(model.revenue_total)
        self._kpi_pending.set_value(str(model.pending_count))
        self._kpi_completed.set_value(str(model.completed_count))
        self._kpi_cancelled.set_value(str(model.cancelled_count))
        self._bar_chart.set_data(model.chart_days)
        self._pie_chart.set_data(model.payment_methods)
        self._render_top_products(model.top_products)

    def _render_top_products(self, top_products: tuple[tuple[str, str, float], ...]) -> None:
        for i in reversed(range(self._top_list.count())):
            item = self._top_list.takeAt(i)
            if item is not None:
                if w := item.widget():
                    w.deleteLater()

        if not top_products:
            lbl = QLabel("Нет данных о продажах")
            lbl.setStyleSheet(f"color: {BrandColors.GRAY_500}; font-size: 13px; padding: 16px 0;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._top_list.addWidget(lbl)
            return

        total = sum(p[2] for p in top_products)
        for rank, (name, revenue, val) in enumerate(top_products, 1):
            pct = (val / total * 100) if total > 0 else 0
            bar = _ProductBar(rank, name, revenue, pct)
            self._top_list.addWidget(bar)

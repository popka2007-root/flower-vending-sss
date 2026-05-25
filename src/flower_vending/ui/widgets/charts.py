"""Simple chart widgets using QPainter for admin analytics."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget


class BarChart(QWidget):
    """Simple vertical bar chart matching reference purple bars."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(200)
        self._data: dict[str, float] = {}
        self._bar_color = QColor("#8b5cf6")
        self._grid_color = QColor("#f0f0f0")
        self._text_color = QColor("#9ca3af")

    def set_data(self, data: dict[str, float]) -> None:
        self._data = data
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        if not self._data or w < 40 or h < 40:
            p.end()
            return

        pad_left, pad_right, pad_top, pad_bottom = 40, 16, 16, 32
        chart_w = w - pad_left - pad_right
        chart_h = h - pad_top - pad_bottom

        max_val = max(self._data.values()) if self._data else 1
        keys = list(self._data.keys())
        n = len(keys)
        if n == 0:
            p.end()
            return

        bar_area = chart_w / n
        bar_w = bar_area * 0.55
        gap = bar_area * 0.45

        font = QFont()
        font.setPixelSize(10)
        p.setFont(font)

        for i in range(5):
            y = h - pad_bottom - int(chart_h * i / 4)
            p.setPen(QPen(self._grid_color, 1, Qt.PenStyle.DashLine))
            p.drawLine(pad_left, y, w - pad_right, y)
            val = max_val * i / 4
            p.setPen(self._text_color)
            p.drawText(0, y + 4, str(int(val)))

        for i, (label, val) in enumerate(self._data.items()):
            bar_h = int(chart_h * val / max_val) if max_val > 0 else 0
            x = pad_left + int(bar_area * i + gap * 0.5)
            y = h - pad_bottom - bar_h
            if bar_h < 2:
                bar_h = 2

            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(self._bar_color)
            p.drawRoundedRect(x, y, int(bar_w), bar_h, 4, 4)

            p.setPen(self._text_color)
            tw = p.fontMetrics().horizontalAdvance(label)
            p.drawText(x + int((bar_area - tw) / 2), h - 8, label)

        p.end()


class PieChart(QWidget):
    """Simple donut/pie chart."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(180)
        self._data: dict[str, tuple[float, str]] = {}
        self._colors = ["#8b5cf6", "#ec4899", "#06b6d4"]

    def set_data(self, data: dict[str, tuple[float, str]]) -> None:
        self._data = data
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        if not self._data or w < 40 or h < 40:
            p.end()
            return

        cx, cy = w // 2, h // 2
        r = min(w, h) // 2 - 24

        total = sum(v for v, _ in self._data.values())
        if total == 0:
            p.end()
            return

        start_angle = 90 * 16
        for i, (label, (val, color)) in enumerate(self._data.items()):
            span = int(360 * 16 * val / total)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(color))
            p.drawPie(cx - r, cy - r, r * 2, r * 2, start_angle, span)
            start_angle += span

        p.setBrush(QColor("#FFFFFF"))
        p.drawEllipse(cx - r // 2, cy - r // 2, r, r)

        font = QFont()
        font.setPixelSize(10)
        p.setFont(font)
        legend_x = cx + r + 12
        legend_y = cy - len(self._data) * 14
        for i, (label, (val, color)) in enumerate(self._data.items()):
            yy = legend_y + i * 20
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(color))
            p.drawEllipse(legend_x, yy, 8, 8)
            p.setPen(self._text_color() if hasattr(self, "_text_color") else QColor("#9ca3af"))
            pct = int(val / total * 100) if total > 0 else 0
            p.drawText(legend_x + 14, yy + 10, f"{label} {pct}%")

        p.end()

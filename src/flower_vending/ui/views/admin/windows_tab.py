"""Admin windows management tab — window status cards, activity log."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from flower_vending.ui.design_tokens import BrandColors, Radius, Typography
from flower_vending.ui.viewmodels.screens import AdminWindowsTabViewModel
from flower_vending.ui.widgets.modern import WindowStatusCard


class WindowsTab(QWidget):
    action_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(24)

        title = QLabel("Окна выдачи")
        title.setStyleSheet(f"font-size: 24px; font-weight: {Typography.WEIGHTS['bold']};")
        layout.addWidget(title)

        desc = QLabel("Управление состоянием окон выдачи заказов")
        desc.setStyleSheet(f"font-size: 14px; color: {BrandColors.GRAY_500};")
        layout.addWidget(desc)

        self._windows_grid = QHBoxLayout()
        self._windows_grid.setSpacing(16)
        layout.addLayout(self._windows_grid)

        log_widget = QWidget()
        log_widget.setStyleSheet(
            f"background: #FFFFFF; border-radius: {Radius.XL}px; border: none;"
        )
        log_layout = QVBoxLayout(log_widget)
        log_layout.setContentsMargins(20, 16, 20, 16)
        log_layout.setSpacing(8)
        log_title = QLabel("Журнал активности")
        log_title.setStyleSheet(f"font-size: 14px; font-weight: {Typography.WEIGHTS['semibold']};")
        log_layout.addWidget(log_title)

        self._log_content = QVBoxLayout()
        log_layout.addLayout(self._log_content)
        log_layout.addStretch(1)

        layout.addWidget(log_widget)

    def bind(self, model: AdminWindowsTabViewModel | object) -> None:
        if not isinstance(model, AdminWindowsTabViewModel):
            return

        for i in reversed(range(self._windows_grid.count())):
            item = self._windows_grid.takeAt(i)
            if item is not None:
                if w := item.widget():
                    w.deleteLater()

        for window in model.windows:
            card = WindowStatusCard(window.window_id, window.status)
            card.set_status(window.status, window.detail_text)
            card.action_requested.connect(self.action_requested.emit)
            self._windows_grid.addWidget(card)

        for i in reversed(range(self._log_content.count())):
            item = self._log_content.takeAt(i)
            if item is not None:
                if w := item.widget():
                    w.deleteLater()

        for entry in model.activity_log[-10:]:
            lbl = QLabel(entry)
            lbl.setStyleSheet(f"font-size: 12px; color: {BrandColors.GRAY_500}; padding: 4px 0;")
            self._log_content.addWidget(lbl)

"""Generic status/info screen — used for errors, blocked states, restricted mode, etc."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from flower_vending.ui.design_tokens import BrandColors
from flower_vending.ui.viewmodels import StatusScreenViewModel
from flower_vending.ui.widgets.controls import BannerWidget
from flower_vending.ui.widgets.modern import GradientButton, OutlineButton


_PADDING = 48


class StatusScreenWidget(QWidget):
    primary_action_requested = Signal(str)
    secondary_action_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("CustomerScreen")
        self.setStyleSheet(
            f"QWidget#CustomerScreen {{ "
            f"background: qlineargradient(x1:0 y1:0, x2:1 y2:1, "
            f"stop:0 {BrandColors.PINK_50}, stop:0.5 {BrandColors.PURPLE_50}, "
            f"stop:1 {BrandColors.BLUE_50}); }}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(_PADDING, _PADDING, _PADDING, _PADDING)
        layout.setSpacing(0)
        layout.addStretch(1)

        self._icon = QLabel()
        self._icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon.setFixedHeight(80)
        layout.addWidget(self._icon)

        self._title = QLabel()
        self._title.setObjectName("StatusMessage")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title.setWordWrap(True)
        layout.addWidget(self._title)

        self._message = QLabel()
        self._message.setObjectName("HumanMessage")
        self._message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._message.setWordWrap(True)
        layout.addWidget(self._message)

        self._details = QLabel()
        self._details.setWordWrap(True)
        self._details.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._details.setStyleSheet(
            f"font-size: 14px; color: {BrandColors.GRAY_500}; padding: 12px 0;"
        )
        layout.addWidget(self._details)

        self._banner = BannerWidget()
        layout.addSpacing(12)
        layout.addWidget(self._banner)

        layout.addStretch(1)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 20, 0, 0)
        buttons.setSpacing(16)

        self._secondary_btn = OutlineButton("Назад")
        self._secondary_btn.clicked.connect(lambda: self.secondary_action_requested.emit("back"))
        buttons.addWidget(self._secondary_btn)

        self._primary_btn = GradientButton("Продолжить")
        self._primary_btn.clicked.connect(lambda: self.primary_action_requested.emit("continue"))
        buttons.addWidget(self._primary_btn)

        layout.addLayout(buttons)

    def bind(self, model: StatusScreenViewModel | object) -> None:
        if not isinstance(model, StatusScreenViewModel):
            return
        self._title.setText(model.title)
        self._message.setText(model.message)

        details_text = "\n".join(model.details) if model.details else ""
        self._details.setText(details_text)
        self._details.setVisible(bool(details_text))

        self._banner.bind(model.banner)

        try:
            self._primary_btn.clicked.disconnect()
        except RuntimeError:
            pass
        if model.primary_action:
            self._primary_btn.setText(model.primary_action.label)
            self._primary_btn.setEnabled(model.primary_action.enabled)
            self._primary_btn.show()
            aid = model.primary_action.action_id
            self._primary_btn.clicked.connect(
                lambda _checked=False, a=aid: self.primary_action_requested.emit(a)
            )
        else:
            self._primary_btn.hide()

        try:
            self._secondary_btn.clicked.disconnect()
        except RuntimeError:
            pass
        if model.secondary_action:
            self._secondary_btn.setText(model.secondary_action.label)
            self._secondary_btn.setEnabled(model.secondary_action.enabled)
            self._secondary_btn.show()
            aid = model.secondary_action.action_id
            self._secondary_btn.clicked.connect(
                lambda _checked=False, a=aid: self.secondary_action_requested.emit(a)
            )
        else:
            self._secondary_btn.hide()

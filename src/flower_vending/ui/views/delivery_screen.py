"""Delivery/pickup screen — animated processing, countdown, pickup confirm."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from flower_vending.ui.design_tokens import BrandColors, Typography
from flower_vending.ui.viewmodels import DeliveryScreenViewModel
from flower_vending.ui.widgets.controls import BannerWidget
from flower_vending.ui.widgets.modern import GradientButton


class DeliveryScreenWidget(QWidget):
    primary_action_requested = Signal(str)

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
        layout.setContentsMargins(0, 0, 0, 0)
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

        self._details_label = QLabel()
        self._details_label.setWordWrap(True)
        self._details_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._details_label.setStyleSheet(
            f"font-size: 14px; color: {BrandColors.GRAY_500}; padding: 8px 0;"
        )
        layout.addWidget(self._details_label)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setFixedWidth(300)
        self._progress.setTextVisible(False)
        progress_wrap = QHBoxLayout()
        progress_wrap.addStretch(1)
        progress_wrap.addWidget(self._progress)
        progress_wrap.addStretch(1)
        layout.addLayout(progress_wrap)

        self._countdown = QLabel()
        self._countdown.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._countdown.setStyleSheet(
            f"font-size: 28px; font-weight: {Typography.WEIGHTS['bold']}; color: {BrandColors.PURPLE_600};"
        )
        self._countdown.hide()
        layout.addWidget(self._countdown)

        self._banner = BannerWidget()
        layout.addSpacing(12)
        layout.addWidget(self._banner)

        layout.addStretch(1)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch(1)
        self._action_btn = GradientButton("Забрать букет")
        self._action_btn.setFixedWidth(300)
        self._action_btn.clicked.connect(
            lambda: self.primary_action_requested.emit("confirm_pickup")
        )
        self._action_btn.hide()
        btn_layout.addWidget(self._action_btn)
        btn_layout.addStretch(1)
        layout.addLayout(btn_layout)

        layout.addSpacing(64)

        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(1000)
        self._remaining_s: float | None = None
        self._dots_frame = 0
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(600)
        self._anim_timer.timeout.connect(self._animate_dots)
        self._anim_timer.start()

    def _animate_dots(self) -> None:
        self._dots_frame = (self._dots_frame + 1) % 4
        dots = "." * (self._dots_frame + 1)
        msg = self._message.text().rstrip(".").rstrip()
        if msg:
            self._message.setText(f"{msg}{dots}")

    def bind(self, model: DeliveryScreenViewModel | object) -> None:
        if not isinstance(model, DeliveryScreenViewModel):
            return
        self._title.setText(model.title)
        self._message.setText(model.message)
        self._details_label.setText("\n".join(model.details) if model.details else "")

        self._banner.bind(model.banner)

        if model.primary_action:
            self._action_btn.setText(model.primary_action.label)
            self._action_btn.setEnabled(model.primary_action.enabled)
            self._action_btn.show()
        else:
            self._action_btn.hide()

        if model.remaining_seconds is not None and model.remaining_seconds > 0:
            self._remaining_s = model.remaining_seconds
            self._countdown.setText(self._format_time(int(self._remaining_s)))
            self._countdown.show()
            self._progress.setValue(100)
        else:
            self._remaining_s = None
            self._countdown.hide()
            self._progress.setValue(0)

    @staticmethod
    def _format_time(seconds: int) -> str:
        m, s = divmod(max(0, seconds), 60)
        return f"{m:01d}:{s:02d}"

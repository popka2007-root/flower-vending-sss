"""Animated processing indicator and progress bar widgets."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from flower_vending.ui.design_tokens import current_color_tokens
from flower_vending.ui.widgets.controls import repolish

_PHASE_INTERVAL_MS = 200
_MESSAGE_ROTATE_MS = 4_000

_FLOWER_SYMBOLS = ("...", "..", ".", "..")

_DISPENSING_MESSAGES = (
    "Готовим ваш букет...",
    "Проверяем свежесть цветов...",
    "Бережно упаковываем...",
    "Почти готово!",
)


class AnimatedProcessingWidget(QFrame):
    """Animated flower symbol + rotating message + optional progress bar."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ProcessingIndicator")
        self._phase_index = 0
        self._message_index = 0
        self._timer = QTimer(self)
        self._message_timer = QTimer(self)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(16)

        self._icon_label = QLabel()
        self._icon_label.setObjectName("ProcessingIcon")
        self._icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._icon_effect = QGraphicsOpacityEffect(self)
        self._icon_effect.setOpacity(1.0)
        self._icon_label.setGraphicsEffect(self._icon_effect)

        self._message_label = QLabel()
        self._message_label.setObjectName("ProcessingLabel")
        self._message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._message_label.setWordWrap(True)

        self._dots = QHBoxLayout()
        self._dots.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._dots.setSpacing(12)
        self._stage_labels: list[QLabel] = []
        tokens = current_color_tokens()
        for _ in range(4):
            dot = QLabel("•")
            dot.setStyleSheet(
                f"font-size: 10px; color: {tokens.processing_dot}; background: transparent;"
            )
            self._dots.addWidget(dot)
            self._stage_labels.append(dot)
        self._dots_container = QWidget()
        self._dots_container.setLayout(self._dots)
        self._dots_container.setStyleSheet("background: transparent;")

        self._progress = QProgressBar()
        self._progress.setObjectName("ProcessingProgress")
        self._progress.setRange(0, 4)
        self._progress.setValue(0)
        self._progress.setFixedHeight(8)
        self._progress.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._progress.hide()

        layout.addStretch(2)
        layout.addWidget(self._icon_label)
        layout.addWidget(self._message_label)
        layout.addWidget(self._dots_container)
        layout.addWidget(self._progress)
        layout.addStretch(3)

        self._timer.timeout.connect(self._tick)
        self._message_timer.timeout.connect(self._rotate_message)

    def start(self, message: str = "") -> None:
        self._message_label.setText(message or _DISPENSING_MESSAGES[0])
        self._phase_index = 0
        self._message_index = 0
        self._icon_label.setText(_FLOWER_SYMBOLS[0])
        self._timer.start(_PHASE_INTERVAL_MS)
        if not message:
            self._message_timer.start(_MESSAGE_ROTATE_MS)
        self.set_stage(0)
        self.show()

    def set_message(self, message: str) -> None:
        self._message_label.setText(message)
        self._message_timer.stop()
        repolish(self._message_label)

    def set_stage(self, stage: int) -> None:
        tokens = current_color_tokens()
        for i, label in enumerate(self._stage_labels):
            label.setStyleSheet(
                f"font-size: {'16px' if i == stage else '10px'}; "
                f"color: {tokens.processing_active if i <= stage else tokens.processing_dot}; "
                "background: transparent;"
            )
        self._progress.setValue(stage)
        self._progress.show()

    def advance_stage(self) -> None:
        current = self._progress.value()
        if current < 4:
            self.set_stage(current + 1)

    def complete(self, message: str = "Готово") -> None:
        self._timer.stop()
        self._message_timer.stop()
        self.set_stage(4)
        self._icon_label.setText("OK")
        self._message_label.setText(message)
        repolish(self._icon_label)
        repolish(self._message_label)

    def stop(self) -> None:
        self._timer.stop()
        self._message_timer.stop()
        self.hide()

    def _tick(self) -> None:
        self._phase_index = (self._phase_index + 1) % len(_FLOWER_SYMBOLS)
        self._icon_label.setText(_FLOWER_SYMBOLS[self._phase_index])
        self._icon_effect.setOpacity(0.3)
        anim = QPropertyAnimation(self._icon_effect, b"opacity")
        anim.setDuration(180)
        anim.setStartValue(0.3)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()

    def _rotate_message(self) -> None:
        self._message_index = (self._message_index + 1) % len(_DISPENSING_MESSAGES)
        self._message_label.setText(_DISPENSING_MESSAGES[self._message_index])
        repolish(self._message_label)

    def __del__(self) -> None:
        try:
            self._timer.stop()
            self._message_timer.stop()
        except RuntimeError:
            pass

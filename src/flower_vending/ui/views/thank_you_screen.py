"""Thank you screen — success state after completed purchase."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from flower_vending.ui.widgets.modern import GradientButton, AnimatedCheckLabel


class ThankYouScreenWidget(QWidget):
    buy_again = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ThankYouScreen")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addStretch(2)

        self._check = AnimatedCheckLabel(96)
        check_wrap = QHBoxLayout()
        check_wrap.addStretch(1)
        check_wrap.addWidget(self._check)
        check_wrap.addStretch(1)
        layout.addLayout(check_wrap)

        layout.addSpacing(24)

        title = QLabel("Спасибо за покупку!")
        title.setObjectName("ThankYouTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("Заберите ваш букет из окна выдачи")
        subtitle.setObjectName("ThankYouSubtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)

        layout.addStretch(2)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch(1)
        again_btn = GradientButton("Купить ещё", compact=True)
        again_btn.setFixedWidth(260)
        again_btn.clicked.connect(lambda: self.buy_again.emit())
        btn_layout.addWidget(again_btn)
        btn_layout.addStretch(1)
        layout.addLayout(btn_layout)

        layout.addStretch(1)

    def bind(self, model: object) -> None:
        self._check.show_animated()

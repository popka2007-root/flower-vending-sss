"""PIN entry screen — premium dark overlay with centered circular keypad."""

from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QKeyEvent, QPalette
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from flower_vending.ui.icons import IconName, icon


class PinScreenWidget(QWidget):
    pin_accepted = Signal(str)
    pin_cancelled = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("PinScreen")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAutoFillBackground(True)
        p = self.palette()
        p.setColor(QPalette.ColorRole.Window, QColor(13, 13, 13))
        self.setPalette(p)
        self.setStyleSheet("QWidget#PinScreen { background: #0D0D0D; }")

        self._digits: list[str] = []
        self._shaking = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        inner = QVBoxLayout()
        inner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        inner.setSpacing(0)

        inner.addStretch(1)

        lock_container = QLabel()
        lock_container.setFixedSize(56, 56)
        lock_container.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lock_container.setStyleSheet(
            "background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.10); "
            "border-radius: 28px;"
        )
        lock_icon = QLabel(lock_container)
        lock_icon.setPixmap(icon(IconName.LOCK, 24, "#FFFFFF").pixmap(24, 24))
        lock_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lock_icon.setGeometry(0, 0, 56, 56)
        lock_icon.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        inner.addWidget(lock_container, 0, Qt.AlignmentFlag.AlignCenter)
        inner.addSpacing(20)

        title = QLabel("Введите\nпароль")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("color: #FFFFFF; font-size: 28px; font-weight: 700;")
        inner.addWidget(title, 0, Qt.AlignmentFlag.AlignCenter)

        sub = QLabel("Админ-панель")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet("color: #8E8E93; font-size: 14px;")
        inner.addWidget(sub, 0, Qt.AlignmentFlag.AlignCenter)

        inner.addSpacing(24)

        dot_row = QHBoxLayout()
        dot_row.setSpacing(14)
        dot_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._dots: list[QLabel] = []
        for _ in range(4):
            dot = QLabel()
            dot.setFixedSize(12, 12)
            dot.setProperty("filled", False)
            dot.setStyleSheet(
                "min-width: 12px; max-width: 12px; min-height: 12px; max-height: 12px; "
                "border: 2px solid #555555; border-radius: 6px; background: transparent;"
            )
            dot_row.addWidget(dot)
            self._dots.append(dot)
        inner.addLayout(dot_row)

        inner.addSpacing(36)

        grid = QGridLayout()
        grid.setSpacing(20)
        grid.setAlignment(Qt.AlignmentFlag.AlignCenter)

        for i, digit in enumerate(["1", "2", "3", "4", "5", "6", "7", "8", "9"]):
            row, col = divmod(i, 3)
            btn = self._make_key(digit)
            grid.addWidget(btn, row, col, Qt.AlignmentFlag.AlignCenter)

        cancel_btn = self._make_key("Отмена")
        cancel_btn.setStyleSheet(
            "QPushButton {"
            "min-width: 80px; max-width: 80px; min-height: 80px; max-height: 80px;"
            "border: none; border-radius: 40px;"
            "background: rgba(255,255,255,0.08); color: #FFFFFF; font-size: 14px; font-weight: 500;"
            "}"
            "QPushButton:hover { background: rgba(255,255,255,0.15); }"
        )
        cancel_btn.clicked.disconnect()
        cancel_btn.clicked.connect(lambda: self.pin_cancelled.emit())
        grid.addWidget(cancel_btn, 3, 0, Qt.AlignmentFlag.AlignCenter)

        zero_btn = self._make_key("0")
        grid.addWidget(zero_btn, 3, 1, Qt.AlignmentFlag.AlignCenter)

        del_btn = QPushButton()
        del_btn.setAccessibleName("Стереть")
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        del_btn.setFixedSize(80, 80)
        del_btn.setIcon(icon(IconName.DELETE, 22, "#FFFFFF"))
        del_btn.setIconSize(del_btn.size())
        del_btn.setStyleSheet(
            "QPushButton {"
            "min-width: 80px; max-width: 80px; min-height: 80px; max-height: 80px;"
            "border: none; border-radius: 40px;"
            "background: rgba(255,255,255,0.08);"
            "}"
            "QPushButton:hover { background: rgba(255,255,255,0.15); }"
        )
        del_btn.clicked.connect(self._on_delete)
        grid.addWidget(del_btn, 3, 2, Qt.AlignmentFlag.AlignCenter)

        inner.addLayout(grid)
        inner.addStretch(1)

        outer.addLayout(inner)

    def _make_key(self, digit: str) -> QPushButton:
        btn = QPushButton(digit)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setFixedSize(80, 80)
        btn.setStyleSheet(
            "QPushButton {"
            "min-width: 80px; max-width: 80px; min-height: 80px; max-height: 80px;"
            "border: none; border-radius: 40px;"
            "background: rgba(255,255,255,0.08); color: #FFFFFF; font-size: 24px;"
            "}"
            "QPushButton:hover { background: rgba(255,255,255,0.15); }"
        )
        btn.clicked.connect(lambda: self._on_digit(digit))
        return btn

    def _on_digit(self, digit: str) -> None:
        if len(self._digits) >= 4:
            return
        self._digits.append(digit)
        self._refresh_dots()
        if len(self._digits) == 4:
            pin = "".join(self._digits)
            self.pin_accepted.emit(pin)

    def _on_delete(self) -> None:
        if self._digits:
            self._digits.pop()
        self._refresh_dots()

    def _refresh_dots(self) -> None:
        for i, dot in enumerate(self._dots):
            filled = i < len(self._digits)
            dot.setStyleSheet(
                "min-width: 12px; max-width: 12px; min-height: 12px; max-height: 12px; "
                "border-radius: 6px; "
                + (
                    "background: #FFFFFF; border: 2px solid #FFFFFF;"
                    if filled
                    else "background: transparent; border: 2px solid #555555;"
                )
            )

    def reset(self) -> None:
        self._digits.clear()
        self._refresh_dots()

    def show_error(self, message: str = "Неверный пароль") -> None:
        self._digits.clear()
        self._refresh_dots()
        self._shake()

    def _shake(self) -> None:
        if self._shaking:
            return
        self._shaking = True
        original = self.pos()
        anim = QPropertyAnimation(self, b"pos")
        anim.setDuration(400)
        anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        anim.setKeyValues(
            [
                (0.0, original),
                (0.1, original + self._delta_x(-10)),
                (0.2, original + self._delta_x(10)),
                (0.3, original + self._delta_x(-10)),
                (0.4, original + self._delta_x(10)),
                (0.5, original + self._delta_x(-6)),
                (0.6, original + self._delta_x(6)),
                (0.7, original + self._delta_x(-3)),
                (0.8, original + self._delta_x(3)),
                (1.0, original),
            ]
        )
        anim.finished.connect(lambda: setattr(self, "_shaking", False))
        anim.start()

    @staticmethod
    def _delta_x(dx: int):
        from PySide6.QtCore import QPoint

        return QPoint(dx, 0)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        if Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
            self._on_digit(str(key - Qt.Key.Key_0))
        elif key in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete):
            self._on_delete()
        elif key == Qt.Key.Key_Escape:
            self.pin_cancelled.emit()
        else:
            super().keyPressEvent(event)

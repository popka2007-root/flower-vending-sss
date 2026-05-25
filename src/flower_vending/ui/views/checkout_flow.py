"""Checkout flow: method -> processing -> success."""

from __future__ import annotations

import math
import random

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QStackedWidget, QVBoxLayout, QWidget

from flower_vending.ui.icons import IconName, icon

G = "qlineargradient(x1:0 y1:0, x2:1 y2:0, stop:0 #EC4899, stop:1 #9333EA)"
G_HOVER = "qlineargradient(x1:0 y1:0, x2:1 y2:0, stop:0 #F062A8, stop:1 #A855F7)"


def _scale(widget: QWidget) -> float:
    return max(0.85, min(1.35, widget.logicalDpiX() / 96.0))


def _px(widget: QWidget, n: float) -> int:
    return round(4 * n * _scale(widget))


_font_cache: dict[tuple[int, int], QFont] = {}


def _f(size: int, weight: int = 400) -> QFont:
    key = (size, weight)
    cached = _font_cache.get(key)
    if cached is not None:
        return cached
    f = QFont()
    f.setFamilies(["Segoe UI", "Arial", "sans-serif"])
    f.setPixelSize(size)
    wm = {
        400: QFont.Weight.Normal,
        500: QFont.Weight.Medium,
        600: QFont.Weight.DemiBold,
        700: QFont.Weight.Bold,
        800: QFont.Weight.ExtraBold,
    }
    f.setWeight(wm.get(weight, QFont.Weight.Normal))
    _font_cache[key] = f
    return f


def _fmt(amount: int) -> str:
    rubles = amount // 100
    kopeks = amount % 100
    major = f"{rubles:,}".replace(",", " ")
    return f"{major}.{kopeks:02d} ₽" if kopeks else f"{major} ₽"


class _ArcSpinner(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._angle = 0
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def set_angle(self, angle: int) -> None:
        self._angle = angle
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        h = self.height()
        cx = w / 2
        cy = h / 2
        r = min(w, h) / 2 - 8

        # Background circle
        painter.setPen(QPen(QColor("#F3F4F6"), 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawArc(int(cx - r), int(cy - r), int(r * 2), int(r * 2), 0, 360 * 16)

        # Gradient arc (starts at angle, spans ~120 degrees)
        span = 120 * 16
        start = self._angle * 16
        painter.setPen(QPen(QColor("#9333EA"), 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawArc(int(cx - r), int(cy - r), int(r * 2), int(r * 2), start, span)

        head_deg = self._angle + 120
        hx = cx + r * math.cos(math.radians(head_deg))
        hy = cy + r * math.sin(math.radians(head_deg))
        painter.setBrush(QColor("#9333EA"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(int(hx - 4), int(hy - 4), 8, 8)

        painter.end()


class _DotBar(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._dot = 0
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def set_dot(self, idx: int) -> None:
        self._dot = idx
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        h = self.height()
        n = 6
        spacing = 18
        total_w = n * spacing
        start_x = (w - total_w) / 2 + spacing / 2
        cy = h / 2
        for i in range(n):
            if i == self._dot % n:
                painter.setBrush(QColor("#9333EA"))
                r = 5
            else:
                painter.setBrush(QColor("#E5E7EB"))
                r = 3
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(int(start_x + i * spacing - r), int(cy - r), r * 2, r * 2)
        painter.end()


class CheckoutFlow(QWidget):
    back_requested = Signal()
    pay_confirmed = Signal(str)
    finish_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._payment_method = "cash"
        self._cart_total = 0

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.setStyleSheet("background: #FFFFFF;")

        self._stack = QStackedWidget()
        root.addWidget(self._stack, 1)

        self._step1 = self._build_step_method()
        self._step2 = self._build_step_processing()
        self._step3 = self._build_step_success()

        self._stack.addWidget(self._step1)
        self._stack.addWidget(self._step2)
        self._stack.addWidget(self._step3)

    def _build_step_method(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(0)

        header = QWidget()
        header.setFixedHeight(_px(self, 17))
        header.setStyleSheet("")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(_px(self, 6), 0, _px(self, 6), 0)
        hl.setSpacing(_px(self, 2))

        back = QPushButton()
        back.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        back.setCursor(Qt.CursorShape.PointingHandCursor)
        back.setFixedSize(36, 36)
        back.setIcon(icon(IconName.ARROW_LEFT, 22, "#374151"))
        back.setIconSize(back.size())
        back.setStyleSheet("QPushButton { border:none; background:transparent; }")
        back.clicked.connect(self.back_requested.emit)
        hl.addWidget(back)

        title = QLabel("Оформление заказа")
        title.setFont(_f(22, 700))
        title.setStyleSheet("color:#1F2937;")
        hl.addWidget(title)
        hl.addStretch(1)
        l.addWidget(header)

        self._order_card = QWidget()
        self._order_card.setStyleSheet("background:#F9FAFB; border-radius:14px;")
        self._order_card_layout = QVBoxLayout(self._order_card)
        self._order_card_layout.setContentsMargins(
            _px(self, 5), _px(self, 4), _px(self, 5), _px(self, 4)
        )
        self._order_card_layout.setSpacing(_px(self, 1))

        order_wrap = QWidget()
        ol = QHBoxLayout(order_wrap)
        ol.setContentsMargins(_px(self, 6), _px(self, 4), _px(self, 6), _px(self, 1))
        ol.addWidget(self._order_card)
        l.addWidget(order_wrap)

        pm_lbl = QLabel("Способ оплаты")
        pm_lbl.setFont(_f(16, 600))
        pm_lbl.setStyleSheet("color:#374151;")
        pm_lbl.setContentsMargins(_px(self, 6), _px(self, 2), 0, _px(self, 2))
        l.addWidget(pm_lbl)

        methods = QWidget()
        mhl = QHBoxLayout(methods)
        mhl.setContentsMargins(_px(self, 6), 0, _px(self, 6), 0)
        mhl.setSpacing(_px(self, 3))
        self._method_cards: dict[str, QWidget] = {}
        for mid, ico, label in [
            ("cash", IconName.WALLET, "Наличные"),
            ("card", IconName.CREDIT_CARD, "Карта"),
            ("sbp", IconName.HOME, "СБП"),
        ]:
            card = QWidget()
            card.setCursor(Qt.CursorShape.PointingHandCursor)
            card.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            card.setStyleSheet("border: none; border-radius:14px; background:white;")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(_px(self, 3), _px(self, 3), _px(self, 3), _px(self, 3))
            cl.setSpacing(_px(self, 1))
            icon_lbl = QLabel()
            icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon_lbl.setPixmap(icon(ico, 24, "#6B7280").pixmap(24, 24))
            name_lbl = QLabel(label)
            name_lbl.setFont(_f(14, 500))
            name_lbl.setStyleSheet("color:#6B7280;")
            name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cl.addWidget(icon_lbl)
            cl.addWidget(name_lbl)
            card.mouseReleaseEvent = lambda e, m=mid: self._select_method(m)
            mhl.addWidget(card, 1)
            self._method_cards[mid] = card
        l.addWidget(methods)
        l.addStretch(1)

        self._pay_btn = QPushButton("Оплатить 0 ₽")
        self._pay_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._pay_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pay_btn.setFixedHeight(_px(self, 14))
        self._pay_btn.setFont(_f(18, 700))
        self._pay_btn.setStyleSheet(
            f"""
            QPushButton {{ background:{G}; border:none; border-radius:14px; color:white; }}
            QPushButton:hover {{ background:{G_HOVER}; }}
            QPushButton:disabled {{ background:#D1D5DB; color:#9CA3AF; }}
            """
        )
        self._pay_btn.clicked.connect(self._go_to_processing)
        pay_wrap = QWidget()
        pl = QHBoxLayout(pay_wrap)
        pl.setContentsMargins(_px(self, 6), _px(self, 4), _px(self, 6), _px(self, 6))
        pl.addWidget(self._pay_btn)
        l.addWidget(pay_wrap)

        self._select_method("cash")
        return w

    def _build_step_processing(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(0)
        l.setAlignment(Qt.AlignmentFlag.AlignCenter)
        l.addStretch(2)

        self._spinner = _ArcSpinner(self)
        self._spinner.setFixedSize(80, 80)
        l.addWidget(self._spinner, 0, Qt.AlignmentFlag.AlignCenter)
        l.addSpacing(28)

        label = QLabel("Обработка платежа")
        label.setFont(_f(26, 700))
        label.setStyleSheet("color:#1F2937;")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        l.addWidget(label)

        sub = QLabel("Пожалуйста, подождите...")
        sub.setFont(_f(16, 400))
        sub.setStyleSheet("color:#9CA3AF;")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        l.addWidget(sub)

        self._dot_bar = _DotBar(self)
        self._dot_bar.setFixedSize(120, 24)
        l.addSpacing(20)
        l.addWidget(self._dot_bar, 0, Qt.AlignmentFlag.AlignCenter)

        l.addStretch(3)

        self._spin_timer = QTimer(self)
        self._spin_frame = 0
        self._spin_timer.timeout.connect(self._spin_tick)
        self._spin_timer.setInterval(50)
        return w

    def _build_step_success(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(0)
        l.setAlignment(Qt.AlignmentFlag.AlignCenter)
        l.addStretch(2)

        icon_wrap = QLabel()
        icon_wrap.setFixedSize(104, 104)
        icon_wrap.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_wrap.setStyleSheet("background: #DCFCE7; border-radius: 52px;")
        icon_wrap.setPixmap(icon(IconName.CHECK_CIRCLE, 58, "#16A34A").pixmap(58, 58))
        l.addWidget(icon_wrap, 0, Qt.AlignmentFlag.AlignCenter)

        l.addSpacing(_px(self, 4))
        title = QLabel("Оплата прошла успешно!")
        title.setFont(_f(34, 800))
        title.setStyleSheet("color:#1F2937;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        l.addWidget(title)

        self._order_num = QLabel("Заказ #0000")
        self._order_num.setFont(_f(16, 500))
        self._order_num.setStyleSheet("color:#6B7280;")
        self._order_num.setAlignment(Qt.AlignmentFlag.AlignCenter)
        l.addWidget(self._order_num)

        l.addSpacing(_px(self, 3))
        self._window_card = QWidget()
        self._window_card.setStyleSheet("background:#FDF2F8; border-radius:14px;")
        self._window_card.setFixedWidth(360)
        wl = QVBoxLayout(self._window_card)
        wl.setContentsMargins(_px(self, 4), _px(self, 3), _px(self, 4), _px(self, 3))
        wl.setSpacing(_px(self, 1))
        window_label = QLabel("Окно выдачи: 1")
        window_label.setFont(_f(18, 600))
        window_label.setStyleSheet("color:#BE185D;")
        window_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub_label = QLabel("Заберите ваш букет")
        sub_label.setFont(_f(14, 400))
        sub_label.setStyleSheet("color:#9CA3AF;")
        sub_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        wl.addWidget(window_label)
        wl.addWidget(sub_label)
        l.addWidget(self._window_card, 0, Qt.AlignmentFlag.AlignCenter)

        l.addStretch(2)
        self._finish_btn = QPushButton("Завершить")
        self._finish_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._finish_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._finish_btn.setFixedHeight(_px(self, 16))
        self._finish_btn.setMinimumWidth(240)
        self._finish_btn.setFont(_f(20, 700))
        self._finish_btn.setStyleSheet(
            f"""
            QPushButton {{ background:{G}; border:none; border-radius:16px; color:white; padding: 0 24px; }}
            QPushButton:hover {{ background:{G_HOVER}; }}
            """
        )
        self._finish_btn.clicked.connect(self.finish_requested.emit)
        l.addWidget(self._finish_btn, 0, Qt.AlignmentFlag.AlignCenter)
        l.addSpacing(_px(self, 8))
        return w

    def _spin_tick(self) -> None:
        self._spin_frame += 1
        self._spinner.set_angle(self._spin_frame * 6)
        self._dot_bar.set_dot(self._spin_frame // 8)

    def _select_method(self, method: str) -> None:
        self._payment_method = method
        for mid, card in self._method_cards.items():
            if mid == method:
                card.setStyleSheet("border: none; border-radius:14px; background:#FDF2F8;")
            else:
                card.setStyleSheet("border: none; border-radius:14px; background:white;")

    def _go_to_processing(self) -> None:
        self.pay_confirmed.emit(self._payment_method)
        self.show_step(1)

    def _show_success(self) -> None:
        self._order_num.setText(f"Заказ #{random.randint(1000, 9999)}")
        self.show_step(2)

    def set_cart_total(self, amount: int) -> None:
        self._cart_total = amount
        self._pay_btn.setText(f"Оплатить {_fmt(amount)}")

    def set_order_items(self, items: list[str]) -> None:
        while (item := self._order_card_layout.takeAt(0)) is not None:
            if w := item.widget():
                w.deleteLater()
        for name in items:
            lbl = QLabel(name)
            lbl.setFont(_f(14, 400))
            lbl.setStyleSheet("color:#374151;")
            self._order_card_layout.addWidget(lbl)

    def show_step(self, step: int) -> None:
        self._stack.setCurrentIndex(step)
        if step == 1:
            self._spin_timer.start(150)
            QTimer.singleShot(1800, self._show_success)
        else:
            self._spin_timer.stop()

    def reset(self) -> None:
        self._spin_timer.stop()
        self._spin_frame = 0
        self._stack.setCurrentIndex(0)
        self._select_method("cash")

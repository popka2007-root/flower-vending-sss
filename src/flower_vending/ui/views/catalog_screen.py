"""Catalog screen with reference-like card grid and cart drawer."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QPixmap,
    QPainter,
    QPainterPath,
    QBrush,
    QRegion,
)
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
)

from flower_vending.ui.icons import IconName, icon
from flower_vending.ui.viewmodels import CatalogItemViewModel, CatalogScreenViewModel

SP = 4


def _px(n: float) -> int:
    return round(SP * n)


# Градиент строго как на макете (розово-фиолетовый)
GRADIENT = "qlineargradient(x1:0 y1:0, x2:1 y2:0, stop:0 #E13B9B, stop:1 #9F30ED)"
GRADIENT_HOVER = "qlineargradient(x1:0 y1:0, x2:1 y2:0, stop:0 #EF4BB0, stop:1 #B24BF5)"

_font_cache: dict[tuple[int, int], QFont] = {}


def _f(size: int, weight: int = 400) -> QFont:
    key = (size, weight)
    cached = _font_cache.get(key)
    if cached is not None:
        return cached
    f = QFont()
    f.setFamilies(["Segoe UI", "Arial", "sans-serif"])
    f.setPixelSize(size)
    weight_map = {
        300: QFont.Weight.Light,
        400: QFont.Weight.Normal,
        500: QFont.Weight.Medium,
        600: QFont.Weight.DemiBold,
        700: QFont.Weight.Bold,
        800: QFont.Weight.ExtraBold,
    }
    f.setWeight(weight_map.get(weight, QFont.Weight.Normal))
    _font_cache[key] = f
    return f


@dataclass
class CartItem:
    product_id: str
    slot_id: str
    title: str
    price_minor: int
    currency: str
    image_path: str | None = None
    quantity: int = 1


class _CartManager:
    def __init__(self) -> None:
        self.items: list[CartItem] = []
        self._listeners: list = []

    def subscribe(self, cb) -> None:
        self._listeners.append(cb)

    def _notify(self) -> None:
        for cb in self._listeners:
            cb()

    def add(
        self,
        product_id: str,
        slot_id: str,
        title: str,
        price_minor: int,
        currency: str = "RUB",
        image_path: str | None = None,
    ) -> None:
        for it in self.items:
            if it.product_id == product_id and it.slot_id == slot_id:
                it.quantity += 1
                self._notify()
                return
        self.items.append(
            CartItem(product_id, slot_id, title, price_minor, currency, image_path, 1)
        )
        self._notify()

    def remove(self, product_id: str, slot_id: str) -> None:
        self.items = [
            i for i in self.items if not (i.product_id == product_id and i.slot_id == slot_id)
        ]
        self._notify()

    def clear(self) -> None:
        self.items.clear()
        self._notify()

    def update_qty(self, product_id: str, slot_id: str, delta: int) -> None:
        for it in self.items:
            if it.product_id == product_id and it.slot_id == slot_id:
                it.quantity = max(0, it.quantity + delta)
                if it.quantity == 0:
                    self.items.remove(it)
                self._notify()
                return

    @property
    def total_count(self) -> int:
        return sum(i.quantity for i in self.items)

    @property
    def total_minor(self) -> int:
        return sum(i.price_minor * i.quantity for i in self.items)

    @property
    def is_empty(self) -> bool:
        return len(self.items) == 0


def _fmt_price(minor: int, currency: str = "RUB") -> str:
    rubles = minor // 100
    major = f"{rubles:,}".replace(",", " ")
    return f"{major} ₽"


class _ProductCard(QFrame):
    """Карточка с идеальными скруглениями и мягкой, прозрачной тенью."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ProductCardContainer")
        self.setStyleSheet("background: transparent; border: none;")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self.inner = QFrame(self)
        self.inner.setObjectName("ProductCard")
        self.inner.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.inner.setGeometry(self.rect())


class _PriceBadge(QWidget):
    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._text = text
        self._bg_color = QColor("#FFFFFF")
        self._text_color = QColor("#E13B9B")
        self._font = _f(14, 700)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        fd = self._font
        self._pad_h = 16
        self._pad_v = 6
        fm = QFontMetrics(fd)
        tw = fm.horizontalAdvance(text)
        th = fm.height()
        self.setFixedSize(tw + self._pad_h * 2, th + self._pad_v * 2)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect()
        painter.setBrush(QBrush(self._bg_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(r, 20, 20)
        painter.setPen(self._text_color)
        painter.setFont(self._font)
        painter.drawText(r, Qt.AlignmentFlag.AlignCenter, self._text)
        painter.end()


class CatalogScreenWidget(QWidget):
    product_selected = Signal(str, str)
    selection_changed = Signal(str, str)
    service_requested = Signal()
    checkout_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("CustomerScreen")
        self._tap_count = 0
        self._catalog_items: list[CatalogItemViewModel] = []
        self._cart_open = False
        self._cart_anim = None

        self._cart = _CartManager()
        self._cart.subscribe(self._refresh_cart_ui)

        self._layout_main = QVBoxLayout(self)
        self._layout_main.setContentsMargins(0, 0, 0, 0)
        self._layout_main.setSpacing(0)

        self._build_header()
        self._build_catalog()
        self._build_cart_drawer()
        self._build_overlay()

        self.setStyleSheet(
            """
            QWidget#CustomerScreen {
                background: #B8B8C8; 
            }
            """
        )
        self._scroll.viewport().setStyleSheet("background: #B8B8C8;")

    def _build_header(self) -> None:
        header_wrap = QFrame()
        header_wrap.setObjectName("HeaderWrap")
        header_wrap.setFrameShape(QFrame.Shape.NoFrame)
        header_wrap.setStyleSheet("QFrame#HeaderWrap { background: #FFFFFF; border: none; }")

        header_layout = QHBoxLayout(header_wrap)
        header_layout.setContentsMargins(40, 16, 40, 16)
        header_layout.setSpacing(16)

        logo_text_col = QVBoxLayout()
        logo_text_col.setSpacing(2)
        logo_row = QHBoxLayout()
        logo_row.setSpacing(12)

        self._flower_icon = QLabel()
        self._flower_icon.setFixedSize(36, 36)
        self._flower_icon.setStyleSheet("background: #E13B9B; border-radius: 8px;")
        self._flower_icon.setPixmap(
            icon(IconName.SHOPPING_CART, 20, "#FFFFFF").pixmap(QSize(20, 20))
        )
        self._flower_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._hero_title = QLabel()
        self._hero_title.setFont(_f(22, 800))
        self._hero_title.setStyleSheet("color: #1A1A24;")
        self._hero_subtitle = QLabel()
        self._hero_subtitle.setFont(_f(13, 400))
        self._hero_subtitle.setStyleSheet("color: #8E8E93;")
        self._hero_title.mousePressEvent = self._on_title_tap
        self._hero_subtitle.mousePressEvent = self._on_title_tap

        logo_row.addWidget(self._flower_icon)
        logo_row.addWidget(self._hero_title)
        logo_row.addStretch(1)

        logo_text_col.addLayout(logo_row)
        logo_text_col.addWidget(self._hero_subtitle)

        header_layout.addLayout(logo_text_col, 1)

        self._cart_btn_wrap = QWidget()
        self._cart_btn_wrap.setStyleSheet("background: transparent;")
        cbl = QHBoxLayout(self._cart_btn_wrap)
        cbl.setContentsMargins(0, 0, 0, 0)

        self._cart_btn = QPushButton("  Корзина")
        self._cart_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cart_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._cart_btn.setMinimumHeight(44)
        self._cart_btn.setFont(_f(15, 600))
        self._cart_btn.setStyleSheet(
            f"""
            QPushButton {{
                background: {GRADIENT};
                border-radius: 22px;
                border: none;
                color: white;
                padding: 10px 24px;
            }}
            QPushButton:hover {{ background: {GRADIENT_HOVER}; }}
            """
        )
        self._cart_btn.setIcon(icon(IconName.SHOPPING_CART, 18, "#FFFFFF"))
        self._cart_btn.clicked.connect(self._toggle_cart)
        cbl.addWidget(self._cart_btn)
        header_layout.addWidget(self._cart_btn_wrap, 0, Qt.AlignmentFlag.AlignVCenter)

        self._cart_badge = QLabel("0", self._cart_btn_wrap)
        self._cart_badge.setFont(_f(11, 700))
        self._cart_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cart_badge.setStyleSheet(
            "background: #4B5563; color: white; border-radius: 10px; min-width: 20px; min-height: 20px; padding: 0 4px;"
        )
        self._cart_badge.hide()

        self._layout_main.addWidget(header_wrap)

    def _build_catalog(self) -> None:
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.viewport().setContentsMargins(0, 0, 0, 0)
        self._scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self._grid_container = QWidget()
        self._grid_container.setStyleSheet("background: transparent;")
        outer = QVBoxLayout(self._grid_container)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._grid_wrap = QWidget()
        self._grid_wrap.setStyleSheet("background: transparent;")
        wrap_layout = QHBoxLayout(self._grid_wrap)
        wrap_layout.setContentsMargins(0, 16, 0, 32)
        wrap_layout.setSpacing(0)
        wrap_layout.addStretch(1)

        self._grid = QGridLayout()
        self._grid.setContentsMargins(40, 20, 40, 20)
        self._grid.setSpacing(28)
        self._grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        wrap_layout.addLayout(self._grid)
        wrap_layout.addStretch(1)

        outer.addWidget(self._grid_wrap)
        self._scroll.setWidget(self._grid_container)
        self._layout_main.addWidget(self._scroll, 1)

    def _build_overlay(self) -> None:
        self._overlay = QWidget(self)
        self._overlay.setStyleSheet("background: rgba(10, 10, 15, 0.4);")
        self._overlay.hide()
        self._overlay.mouseReleaseEvent = lambda e: self._hide_cart()
        self._overlay_effect = QGraphicsOpacityEffect(self._overlay)
        self._overlay.setGraphicsEffect(self._overlay_effect)

    def _build_cart_drawer(self) -> None:
        self._cart_widget = QFrame(self)
        self._cart_widget.setObjectName("CartDrawer")
        self._cart_widget.setFixedWidth(460)
        self._cart_widget.setStyleSheet("QFrame#CartDrawer { background: #FFFFFF; border: none; }")
        self._cart_widget.hide()

        drawer_shadow = QGraphicsDropShadowEffect(self)
        drawer_shadow.setBlurRadius(50)
        drawer_shadow.setColor(QColor(0, 0, 0, 25))
        drawer_shadow.setOffset(-5, 0)
        self._cart_widget.setGraphicsEffect(drawer_shadow)

        root = QVBoxLayout(self._cart_widget)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QWidget()
        header.setFixedHeight(72)
        header.setStyleSheet("background: #FFFFFF; border-bottom: 1px solid #F3F4F6;")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(28, 0, 20, 0)
        self._cart_title = QLabel("Ваша корзина")
        self._cart_title.setFont(_f(20, 700))
        self._cart_title.setStyleSheet("color: #111827;")
        close_btn = QPushButton()
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        close_btn.setFixedSize(36, 36)
        close_btn.setIcon(icon(IconName.X, 20, "#9CA3AF"))
        close_btn.setStyleSheet(
            "QPushButton { border: none; background: transparent; } QPushButton:hover { background: #F3F4F6; border-radius: 18px; }"
        )
        close_btn.clicked.connect(self._hide_cart)
        hl.addWidget(self._cart_title)
        hl.addStretch(1)
        hl.addWidget(close_btn)
        root.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self._cart_items_widget = QWidget()
        self._cart_items_layout = QVBoxLayout(self._cart_items_widget)
        self._cart_items_layout.setContentsMargins(28, 24, 28, 24)
        self._cart_items_layout.setSpacing(16)
        self._cart_items_layout.addStretch(1)
        scroll.setWidget(self._cart_items_widget)
        root.addWidget(scroll, 1)

        footer = QFrame()
        footer.setObjectName("CartFooter")
        footer.setStyleSheet(
            "QFrame#CartFooter { background: #FFFFFF; border-top: 1px solid #F3F4F6; }"
        )
        fl = QVBoxLayout(footer)
        fl.setContentsMargins(28, 24, 28, 28)
        fl.setSpacing(20)

        total_row = QHBoxLayout()
        total_row.setContentsMargins(0, 0, 0, 0)
        total_caption = QLabel("Итого:")
        total_caption.setFont(_f(18, 700))
        total_caption.setStyleSheet("color: #111827;")
        self._cart_total_label = QLabel("0 ₽")
        self._cart_total_label.setFont(_f(24, 800))
        self._cart_total_label.setStyleSheet("color: #111827;")
        total_row.addWidget(total_caption)
        total_row.addStretch(1)
        total_row.addWidget(self._cart_total_label)
        fl.addLayout(total_row)

        self._cart_checkout_btn = QPushButton("Оформить заказ")
        self._cart_checkout_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cart_checkout_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._cart_checkout_btn.setFixedHeight(56)
        self._cart_checkout_btn.setFont(_f(16, 700))
        self._cart_checkout_btn.setStyleSheet(
            f"""
            QPushButton {{
                background: #6B7280;
                border: none;
                border-radius: 28px;
                color: white;
            }}
            QPushButton:hover {{ background: #4B5563; }}
            QPushButton:disabled {{ background: #E5E7EB; color: #9CA3AF; }}
            """
        )
        self._cart_checkout_btn.clicked.connect(self._on_checkout)
        fl.addWidget(self._cart_checkout_btn)
        root.addWidget(footer)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._cart_open:
            drawer_w = self._cart_widget.width()
            self._cart_widget.setGeometry(self.width() - drawer_w, 0, drawer_w, self.height())
            self._overlay.setGeometry(0, 0, max(0, self.width() - drawer_w), self.height())
        else:
            self._overlay.setGeometry(0, 0, self.width(), self.height())
        self._relayout_grid()
        QTimer.singleShot(0, self._reposition_cart_badge)

    def _toggle_cart(self) -> None:
        if self._cart_open:
            self._hide_cart()
        else:
            self._show_cart()

    def _show_cart(self) -> None:
        if self._cart_open:
            return
        self._cart_open = True
        drawer_w = self._cart_widget.width()
        self._overlay.setGeometry(0, 0, max(0, self.width() - drawer_w), self.height())
        self._overlay.show()
        self._overlay_fade = QPropertyAnimation(self._overlay_effect, b"opacity")
        self._overlay_fade.setDuration(250)
        self._overlay_fade.setStartValue(0.0)
        self._overlay_fade.setEndValue(1.0)
        self._overlay_fade.start()

        self._cart_widget.setGeometry(self.width() + 10, 0, drawer_w, self.height())
        self._cart_widget.show()
        self._cart_widget.raise_()

        self._cart_anim = QPropertyAnimation(self._cart_widget, b"geometry")
        self._cart_anim.setDuration(300)
        self._cart_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        start = self._cart_widget.geometry()
        end = start.translated(-(drawer_w + 10), 0)
        self._cart_anim.setStartValue(start)
        self._cart_anim.setEndValue(end)
        self._cart_anim.start()

    def _hide_cart(self) -> None:
        if not self._cart_open:
            return
        self._cart_open = False
        if self._cart_anim is not None:
            self._cart_anim.stop()
        self._overlay_fade = QPropertyAnimation(self._overlay_effect, b"opacity")
        self._overlay_fade.setDuration(200)
        self._overlay_fade.setStartValue(self._overlay_effect.opacity())
        self._overlay_fade.setEndValue(0.0)
        self._overlay_fade.finished.connect(self._overlay.hide)
        self._overlay_fade.start()

        self._cart_anim = QPropertyAnimation(self._cart_widget, b"geometry")
        self._cart_anim.setDuration(250)
        self._cart_anim.setEasingCurve(QEasingCurve.Type.InCubic)
        start = self._cart_widget.geometry()
        end = start
        end.moveLeft(self.width() + 10)
        self._cart_anim.setStartValue(start)
        self._cart_anim.setEndValue(end)
        self._cart_anim.finished.connect(self._cart_widget.hide)
        self._cart_anim.start()

    def bind(self, model: CatalogScreenViewModel | object) -> None:
        if not isinstance(model, CatalogScreenViewModel):
            return
        self._hero_title.setText(model.title)
        self._hero_subtitle.setText(model.subtitle)
        self._catalog_items = list(model.items)
        self._relayout_grid()

    def _relayout_grid(self) -> None:
        if not self._catalog_items:
            return
        cols = 3
        for i in reversed(range(self._grid.count())):
            item = self._grid.takeAt(i)
            if item is not None and item.widget() is not None:
                item.widget().deleteLater()
        for idx, item in enumerate(self._catalog_items):
            row = idx // cols
            col = idx % cols
            card = self._make_product_card(item)
            self._grid.addWidget(card, row, col, Qt.AlignmentFlag.AlignCenter)
        QTimer.singleShot(0, self._reposition_all_badges)
        QTimer.singleShot(0, self._reposition_cart_badge)

    def _reposition_cart_badge(self) -> None:
        w = self._cart_btn
        if w.width() > 0:
            self._cart_badge.adjustSize()
            bw = self._cart_badge.width()
            self._cart_badge.move(w.width() - bw + 6, -6)
            self._cart_badge.raise_()

    def _reposition_all_badges(self) -> None:
        for i in range(self._grid.count()):
            item = self._grid.itemAt(i)
            if item is not None and item.widget() is not None:
                card = item.widget()
                if hasattr(card, "inner") and card.inner.layout() is not None:
                    child = card.inner.layout().itemAt(0)
                    if child is not None and child.widget() is not None:
                        image_wrap = child.widget()
                        if hasattr(image_wrap, "_reposition_badge"):
                            image_wrap._reposition_badge()

    @staticmethod
    def _get_rounded_pixmap(pix: QPixmap, w: int, h: int, radius: int) -> QPixmap:
        """Делает программную обрезку картинки, чтобы верхние углы были идеально круглыми."""
        if pix.isNull() or w <= 0 or h <= 0:
            return pix
        scaled = pix.scaled(
            w,
            h,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        # Центрируем кроп
        x = (scaled.width() - w) // 2
        y = (scaled.height() - h) // 2
        scaled = scaled.copy(x, y, w, h)

        out = QPixmap(w, h)
        out.fill(Qt.GlobalColor.transparent)
        painter = QPainter(out)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        # Скругляем верхние углы, низ оставляем прямым
        path.addRoundedRect(0, 0, w, h + radius, radius, radius)
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, scaled)
        painter.end()
        return out

    def _load_photo(self, item: CatalogItemViewModel, photo: QLabel, image_wrap: QWidget) -> None:
        if not item.image_path:
            photo.setProperty("placeholder", True)
            photo.setPixmap(icon(IconName.FLOWER, 48, "#D1D5DB").pixmap(48, 48))
            photo.setStyleSheet(
                "background: #F3F4F6; border-top-left-radius: 24px; border-top-right-radius: 24px;"
            )
            return
        pix = QPixmap(item.image_path)
        if pix.isNull():
            photo.setProperty("placeholder", True)
            photo.setPixmap(icon(IconName.FLOWER, 48, "#D1D5DB").pixmap(48, 48))
            photo.setStyleSheet(
                "background: #F3F4F6; border-top-left-radius: 24px; border-top-right-radius: 24px;"
            )
            return
        photo.setProperty("placeholder", False)
        photo.setProperty("_source_pixmap", pix)
        photo._original_pixmap = pix
        photo.setText("")
        # Непосредственная отрисовка скруглений будет в _reposition_badge

    def _make_product_card(self, item: CatalogItemViewModel) -> QWidget:
        card = _ProductCard()
        card.setMinimumWidth(300)
        card.setMaximumWidth(360)
        card.setMinimumHeight(440)
        card.setMaximumHeight(480)

        layout = QVBoxLayout(card.inner)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Белый фон карточки и радиус в 24px (очень скругленный, как на референсе)
        card.inner.setStyleSheet(
            """
            QFrame#ProductCard {
                background-color: #FFFFFF;
                border: none;
                border-radius: 24px;
            }
            """
        )

        image_wrap = QFrame(card.inner)
        image_wrap.setFixedHeight(230)
        image_wrap.setStyleSheet("background: transparent; border: none;")

        photo = QLabel(image_wrap)
        photo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._load_photo(item, photo, image_wrap)

        price_badge = _PriceBadge(item.price_text, image_wrap)

        def _reposition_children() -> None:
            pw = image_wrap.width()
            ph = image_wrap.height()
            if pw <= 0 or ph <= 0:
                return
            photo.setGeometry(0, 0, pw, ph)
            if (
                hasattr(photo, "_original_pixmap")
                and photo._original_pixmap
                and not photo._original_pixmap.isNull()
            ):
                # Программное закругление
                rounded = self._get_rounded_pixmap(photo._original_pixmap, pw, ph, 24)
                photo.setPixmap(rounded)
            price_badge.move(pw - price_badge.width() - 16, 16)
            price_badge.raise_()

        image_wrap._reposition_badge = _reposition_children
        layout.addWidget(image_wrap)

        body = QFrame()
        body.setStyleSheet("background: transparent;")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(24, 20, 24, 24)
        bl.setSpacing(4)

        title = QLabel(item.title)
        title.setFont(_f(18, 700))
        title.setStyleSheet("color: #111827;")
        title.setWordWrap(True)

        desc = QLabel(item.short_description or "")
        desc.setWordWrap(True)
        desc.setFont(_f(13, 400))
        desc.setStyleSheet("color: #6B7280;")
        desc.setVisible(bool(item.short_description))

        bl.addWidget(title)
        bl.addWidget(desc)
        bl.addSpacing(12)

        add_btn = QPushButton(" Добавить в корзину")
        add_btn.setIcon(icon(IconName.PLUS, 16, "#FFFFFF"))
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        add_btn.setFixedHeight(44)
        add_btn.setFont(_f(14, 600))
        add_btn.setEnabled(item.enabled)
        # Полностью скругленная кнопка градиентом
        add_btn.setStyleSheet(
            f"""
            QPushButton {{
                background: {GRADIENT};
                border: none;
                border-radius: 22px;
                color: white;
            }}
            QPushButton:hover {{ background: {GRADIENT_HOVER}; }}
            QPushButton:disabled {{ background: #E5E7EB; color: #9CA3AF; }}
            """
        )
        add_btn.clicked.connect(lambda _checked=False, it=item: self._add_to_cart(it))

        bl.addWidget(add_btn)
        layout.addWidget(body)
        return card

    def _make_cart_item_row(self, item: CartItem) -> QWidget:
        row = QWidget()
        row.setStyleSheet("background: transparent; border: none;")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(16)

        img = QLabel()
        img.setFixedSize(56, 56)
        img.setStyleSheet("background: transparent; border: none;")
        img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if item.image_path:
            pix = QPixmap(item.image_path)
            if not pix.isNull():
                img.setPixmap(self._get_rounded_pixmap(pix, 70, 70, 12))
            else:
                img.setPixmap(icon(IconName.FLOWER, 32, "#D1D5DB").pixmap(32, 32))
        else:
            img.setPixmap(icon(IconName.FLOWER, 32, "#D1D5DB").pixmap(32, 32))
        layout.addWidget(img)

        info = QVBoxLayout()
        info.setContentsMargins(0, 0, 0, 0)
        info.setSpacing(2)
        title = QLabel(item.title)
        title.setFont(_f(15, 600))
        title.setStyleSheet("color: #111827;")

        # Строка с кол-вом и ценой под названием
        subtitle = QLabel(f"(1 шт.) - {_fmt_price(item.price_minor)}")
        subtitle.setFont(_f(13, 500))
        subtitle.setStyleSheet("color: #4B5563;")

        info.addWidget(title)
        info.addWidget(subtitle)
        info.addStretch(1)
        layout.addLayout(info, 1)

        qty_wrap = QWidget()
        qty_wrap.setStyleSheet("background: transparent;")
        qty_inner = QHBoxLayout(qty_wrap)
        qty_inner.setContentsMargins(0, 0, 0, 0)
        qty_inner.setSpacing(12)

        pid, sid = item.product_id, item.slot_id

        minus_btn = QPushButton()
        minus_btn.setFixedSize(26, 26)
        minus_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        minus_btn.setIcon(icon(IconName.MINUS, 14, "#374151"))
        minus_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none; } QPushButton:hover { background: #F3F4F6; border-radius: 13px; }"
        )
        minus_btn.clicked.connect(
            lambda _checked=False, p=pid, s=sid: self._cart.update_qty(p, s, -1)
        )

        count_lbl = QLabel(str(item.quantity))
        count_lbl.setFont(_f(15, 600))
        count_lbl.setStyleSheet("color: #111827; background: transparent; border: none;")
        count_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        count_lbl.setFixedWidth(20)

        plus_btn = QPushButton()
        plus_btn.setFixedSize(26, 26)
        plus_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        plus_btn.setIcon(icon(IconName.PLUS, 14, "#9333EA"))
        plus_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none; } QPushButton:hover { background: #F3F4F6; border-radius: 13px; }"
        )
        plus_btn.clicked.connect(
            lambda _checked=False, p=pid, s=sid: self._cart.update_qty(p, s, 1)
        )

        qty_inner.addWidget(minus_btn)
        qty_inner.addWidget(count_lbl)
        qty_inner.addWidget(plus_btn)
        layout.addWidget(qty_wrap)
        return row

    def _refresh_cart_ui(self) -> None:
        for i in reversed(range(self._cart_items_layout.count())):
            item = self._cart_items_layout.takeAt(i)
            if item is not None and item.widget() is not None:
                item.widget().deleteLater()
        for it in self._cart.items:
            self._cart_items_layout.addWidget(self._make_cart_item_row(it))
        self._cart_items_layout.addStretch(1)
        self._cart_total_label.setText(_fmt_price(self._cart.total_minor))
        self._cart_checkout_btn.setEnabled(not self._cart.is_empty)

        count = self._cart.total_count
        if count > 0:
            self._cart_badge.setText(str(count) if count <= 99 else "99+")
            self._cart_badge.show()
        else:
            self._cart_badge.hide()
        QTimer.singleShot(0, self._reposition_cart_badge)

    def _add_to_cart(self, item: CatalogItemViewModel) -> None:
        if not item.enabled:
            return
        self._cart.add(
            item.product_id,
            item.slot_id,
            item.title,
            item.price_minor_units,
            item.currency_code or "RUB",
            item.image_path,
        )
        self.selection_changed.emit(item.product_id, item.slot_id)
        self._show_cart()

    def _on_checkout(self) -> None:
        if self._cart.is_empty:
            return
        self.checkout_requested.emit()

    def get_cart(self) -> _CartManager:
        return self._cart

    def _on_title_tap(self, event) -> None:
        self._tap_count += 1
        if self._tap_count >= 5:
            self._tap_count = 0
            self.service_requested.emit()

    def set_service_visible(self, visible: bool) -> None:
        return

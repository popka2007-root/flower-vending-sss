"""Catalog screen with reference-like card grid and cart drawer."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QPainterPath,
    QPixmap,
)
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from flower_vending.ui.design_tokens import (
    DARK_TOKENS,
    BrandColors,
    current_color_tokens,
)
from flower_vending.ui.icons import IconName, icon
from flower_vending.ui.viewmodels import (
    CatalogItemViewModel,
    CatalogScreenViewModel,
)

SP = 4


def _px(n: float) -> int:
    return round(SP * n)


# Фирменные цвета
PRIMARY_COLOR = BrandColors.ORANGE_PRIMARY
BG_COLOR = BrandColors.CREAM_BACKGROUND
CARD_BG = BrandColors.CREAM_CARD
TEXT_MAIN = BrandColors.TEXT_MAIN
TEXT_MUTED = BrandColors.TEXT_MUTED

_font_cache: dict[tuple[int, int, bool], QFont] = {}


def _f(size: int, weight: int = 400, serif: bool = False) -> QFont:
    key = (size, weight, serif)
    cached = _font_cache.get(key)
    if cached is not None:
        return cached
    f = QFont()
    if serif:
        f.setFamilies(["Georgia", "Times New Roman", "serif"])
    else:
        f.setFamilies(["Segoe UI", "Arial", "sans-serif"])
    f.setPixelSize(size)
    weight_map = {
        300: QFont.Weight.Light,
        400: QFont.Weight.Normal,
        500: QFont.Weight.Medium,
        600: QFont.Weight.DemiBold,
        700: QFont.Weight.Bold,
        800: QFont.Weight.ExtraBold,
        900: QFont.Weight.Black,
    }
    f.setWeight(weight_map.get(weight, QFont.Weight.Normal))
    _font_cache[key] = f
    return f


# --- Специальный класс для работы с кликами (Админ панель) ---
class _TapLabel(QLabel):
    """Кастомный QLabel, который правильно прокидывает сигналы клика в Qt."""

    tapped = Signal()

    def mousePressEvent(self, event):
        self.tapped.emit()
        super().mousePressEvent(event)


# --- Генерация векторного сердечка ---
def _get_heart_pixmap(size: int, color: str) -> QPixmap:
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(color))
    painter.setPen(Qt.PenStyle.NoPen)

    scale = size / 24.0
    path = QPainterPath()
    path.moveTo(12 * scale, 21.35 * scale)
    path.lineTo(10.55 * scale, 20.03 * scale)
    path.cubicTo(5.4 * scale, 15.36 * scale, 2 * scale, 12.28 * scale, 2 * scale, 8.5 * scale)
    path.cubicTo(2 * scale, 5.42 * scale, 4.42 * scale, 3 * scale, 7.5 * scale, 3 * scale)
    path.cubicTo(9.24 * scale, 3 * scale, 10.91 * scale, 3.81 * scale, 12 * scale, 5.09 * scale)
    path.cubicTo(13.09 * scale, 3.81 * scale, 14.76 * scale, 3 * scale, 16.5 * scale, 3 * scale)
    path.cubicTo(19.58 * scale, 3 * scale, 22 * scale, 5.42 * scale, 22 * scale, 8.5 * scale)
    path.cubicTo(
        22 * scale, 12.28 * scale, 18.6 * scale, 15.36 * scale, 13.45 * scale, 20.04 * scale
    )
    path.lineTo(12 * scale, 21.35 * scale)

    painter.drawPath(path)
    painter.end()
    return pix


@dataclass
class CartItem:
    product_id: str
    slot_id: str
    title: str
    price_minor: int
    currency: str
    image_path: str | None = None
    quantity: int = 1
    available_quantity: int = 1


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
        available_quantity: int = 1,
    ) -> None:
        for it in self.items:
            if it.product_id == product_id and it.slot_id == slot_id:
                if it.quantity < it.available_quantity:
                    it.quantity += 1
                self._notify()
                return
        if available_quantity > 0:
            self.items.append(
                CartItem(
                    product_id,
                    slot_id,
                    title,
                    price_minor,
                    currency,
                    image_path,
                    1,
                    available_quantity,
                )
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
                new_qty = it.quantity + delta
                if new_qty > it.available_quantity:
                    new_qty = it.available_quantity
                it.quantity = max(0, new_qty)
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


def _fmt_price(minor: int) -> str:
    rubles = minor // 100
    return f"{rubles:,}".replace(",", " ")


class _ProductCard(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ProductCardContainer")
        self.setStyleSheet("background: transparent; border: none;")
        # Оставили курсор для понимания, что элемент кликабельный
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(0)

        self.inner = QFrame(self)
        self.inner.setObjectName("ProductCard")
        self.inner.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout.addWidget(self.inner)


class CatalogScreenWidget(QWidget):
    product_selected = Signal(str, str)
    selection_changed = Signal(str, str)
    service_requested = Signal()
    checkout_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("CustomerScreen")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self._tap_count = 0
        self._catalog_items: list[CatalogItemViewModel] = []
        self._cart_open = False
        self._cart_anim = None
        self._overlay_fade = None

        self._cart = _CartManager()
        self._cart.subscribe(self._refresh_cart_ui)

        self._layout_main = QVBoxLayout(self)
        self._layout_main.setContentsMargins(0, 0, 0, 0)
        self._layout_main.setSpacing(0)

        self._build_header()
        self._build_catalog()
        self._build_cart_drawer()
        self._build_overlay()

        self.setStyleSheet(f"QWidget#CustomerScreen {{ background: {BG_COLOR}; }}")
        self._scroll.viewport().setStyleSheet(f"background: {BG_COLOR};")

    def _build_header(self) -> None:
        header_wrap = QFrame()
        header_wrap.setObjectName("HeaderWrap")
        header_wrap.setFrameShape(QFrame.Shape.NoFrame)
        header_wrap.setStyleSheet("QFrame#HeaderWrap { background: transparent; border: none; }")

        header_layout = QHBoxLayout(header_wrap)
        header_layout.setContentsMargins(40, 20, 40, 20)

        # === ЛЕВЫЙ БЛОК: ЛОГОТИП ===
        logo_row = QHBoxLayout()
        logo_row.setSpacing(12)

        self._flower_icon = _TapLabel()
        self._flower_icon.setAccessibleName("Логотип")
        self._flower_icon.setFixedSize(56, 56)
        self._flower_icon.setStyleSheet("background: transparent; border: none;")
        self._flower_icon.tapped.connect(self._on_title_tap)

        pix = QPixmap(56, 56)
        pix.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(PRIMARY_COLOR))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(0, 0, 56, 56)

        painter.translate(28, 28)
        painter.setBrush(QColor("#FFFFFF"))
        painter.setPen(Qt.PenStyle.NoPen)
        for _ in range(8):
            path = QPainterPath()
            path.moveTo(0, -4)
            path.cubicTo(4, -8, 4, -16, 0, -18)
            path.cubicTo(-4, -16, -4, -8, 0, -4)
            painter.drawPath(path)
            painter.rotate(45)

        painter.drawEllipse(-3, -3, 6, 6)
        painter.setBrush(QColor(PRIMARY_COLOR))
        painter.drawEllipse(-1.5, -1.5, 3, 3)
        painter.end()
        self._flower_icon.setPixmap(pix)

        logo_text_layout = QVBoxLayout()
        logo_text_layout.setSpacing(0)
        logo_text_layout.setContentsMargins(0, 0, 0, 0)
        logo_text_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        l1 = _TapLabel("ЭКСПРЕСС")
        l1.setFont(_f(16, 900))
        l1.setStyleSheet("color: #8C7B73; letter-spacing: 2px;")
        l1.tapped.connect(self._on_title_tap)

        l2 = _TapLabel("БУКЕТ 24")
        l2.setFont(_f(16, 900))
        l2.setStyleSheet(f"color: {PRIMARY_COLOR}; letter-spacing: 2px;")
        l2.tapped.connect(self._on_title_tap)

        logo_text_layout.addWidget(l1)
        logo_text_layout.addWidget(l2)

        logo_row.addWidget(self._flower_icon)
        logo_row.addLayout(logo_text_layout)

        # === ЦЕНТРАЛЬНЫЙ БЛОК: ЗАГОЛОВОК ===
        title_col = QVBoxLayout()
        title_col.setSpacing(4)
        title_col.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._title_wrap = QWidget()
        self._title_wrap.setStyleSheet("background: transparent;")
        title_row = QHBoxLayout(self._title_wrap)
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(12)
        title_row.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._hero_title = _TapLabel("Выбирайте с любовью")
        self._hero_title.setAccessibleName("Заголовок")
        self._hero_title.setFont(_f(38, 400, serif=True))
        self._hero_title.setStyleSheet(f"color: {TEXT_MAIN};")

        self._heart_icon = _TapLabel()
        self._heart_icon.setAccessibleName("Иконка сердца")
        self._heart_icon.setPixmap(_get_heart_pixmap(36, PRIMARY_COLOR))

        title_row.addStretch(1)
        title_row.addWidget(self._hero_title)
        title_row.addWidget(self._heart_icon)
        title_row.addStretch(1)

        self._hero_subtitle = _TapLabel("Коснитесь букета, чтобы добавить его в заказ")
        self._hero_subtitle.setFont(_f(15, 400))
        self._hero_subtitle.setStyleSheet(f"color: {TEXT_MUTED};")
        self._hero_subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._hero_title.tapped.connect(self._on_title_tap)
        self._heart_icon.tapped.connect(self._on_title_tap)
        self._hero_subtitle.tapped.connect(self._on_title_tap)

        title_col.addWidget(self._title_wrap)
        title_col.addWidget(self._hero_subtitle)

        # === ПРАВЫЙ БЛОК: КОРЗИНА ===
        self._cart_btn_wrap = QWidget()
        self._cart_btn_wrap.setStyleSheet("background: transparent;")
        cbl = QHBoxLayout(self._cart_btn_wrap)
        cbl.setContentsMargins(0, 0, 0, 0)

        self._cart_btn = QPushButton("  Корзина")
        self._cart_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cart_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._cart_btn.setMinimumHeight(44)
        self._cart_btn.setFont(_f(15, 600))

        shadow = QGraphicsDropShadowEffect(self._cart_btn)
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(239, 125, 0, 76))
        shadow.setOffset(0, 4)
        self._cart_btn.setGraphicsEffect(shadow)

        # Полностью удалена анимация (:hover и :pressed)
        self._cart_btn.setStyleSheet(
            f"""
            QPushButton {{
                background: {PRIMARY_COLOR};
                border-radius: 22px;
                border: none;
                color: white;
                padding: 10px 24px;
                margin: 0px;
            }}
            """
        )
        self._cart_btn.setIcon(icon(IconName.SHOPPING_CART, 18, "#FFFFFF"))
        self._cart_btn.clicked.connect(self._toggle_cart)
        cbl.addWidget(self._cart_btn)

        self._cart_badge = QLabel("0", self._cart_btn_wrap)
        self._cart_badge.setFont(_f(11, 700))
        self._cart_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cart_badge.setStyleSheet(
            f"background: #FFFFFF; color: {PRIMARY_COLOR}; border: 1px solid #FFEDD5; border-radius: 10px; min-width: 20px; min-height: 20px; padding: 0 4px;"
        )
        self._cart_badge.hide()

        header_layout.addLayout(logo_row)
        header_layout.addStretch(1)
        header_layout.addLayout(title_col)
        header_layout.addStretch(1)
        header_layout.addWidget(self._cart_btn_wrap)

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

        # Категории полностью удалены из кода

        self._grid_wrap = QWidget()
        self._grid_wrap.setStyleSheet("background: transparent;")
        wrap_layout = QHBoxLayout(self._grid_wrap)
        wrap_layout.setContentsMargins(0, 16, 0, 32)
        wrap_layout.setSpacing(0)
        wrap_layout.addStretch(1)

        self._grid = QGridLayout()
        self._grid.setContentsMargins(40, 20, 40, 20)
        self._grid.setSpacing(20)
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
        # Фиксируем ширину корзины
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
        close_btn.setAccessibleName("Закрыть")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        close_btn.setFixedSize(36, 36)
        close_btn.setIcon(icon(IconName.X, 20, "#9CA3AF"))
        # Статичная кнопка без hover
        close_btn.setStyleSheet("QPushButton { border: none; background: transparent; }")
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
        # Статичный стиль без анимаций
        self._cart_checkout_btn.setStyleSheet(
            f"""
            QPushButton {{
                background: {PRIMARY_COLOR};
                border: none;
                border-radius: 28px;
                color: white;
            }}
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
            self._overlay.setGeometry(0, 0, self.width(), self.height())
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

        # Плавно выводим оверлей
        self._overlay.setGeometry(0, 0, self.width(), self.height())
        self._overlay.show()
        self._overlay_fade = QPropertyAnimation(self._overlay_effect, b"opacity")
        self._overlay_fade.setDuration(400)
        self._overlay_fade.setStartValue(0.0)
        self._overlay_fade.setEndValue(1.0)
        self._overlay_fade.start()

        # Плавная анимация появления корзины (геометрия)
        self._cart_widget.setGeometry(self.width(), 0, drawer_w, self.height())
        self._cart_widget.show()
        self._cart_widget.raise_()

        self._cart_anim = QPropertyAnimation(self._cart_widget, b"geometry")
        self._cart_anim.setDuration(400)
        self._cart_anim.setEasingCurve(QEasingCurve.Type.OutExpo)

        start_geom = self._cart_widget.geometry()
        end_geom = start_geom.translated(-drawer_w, 0)

        self._cart_anim.setStartValue(start_geom)
        self._cart_anim.setEndValue(end_geom)
        self._cart_anim.start()

    def _hide_cart(self) -> None:
        if not self._cart_open:
            return
        self._cart_open = False

        if self._cart_anim is not None:
            self._cart_anim.stop()

        self._overlay_fade = QPropertyAnimation(self._overlay_effect, b"opacity")
        self._overlay_fade.setDuration(300)
        self._overlay_fade.setStartValue(self._overlay_effect.opacity())
        self._overlay_fade.setEndValue(0.0)
        self._overlay_fade.finished.connect(self._overlay.hide)
        self._overlay_fade.start()

        self._cart_anim = QPropertyAnimation(self._cart_widget, b"geometry")
        self._cart_anim.setDuration(300)
        self._cart_anim.setEasingCurve(QEasingCurve.Type.OutExpo)

        start_geom = self._cart_widget.geometry()
        end_geom = start_geom.translated(self._cart_widget.width(), 0)

        self._cart_anim.setStartValue(start_geom)
        self._cart_anim.setEndValue(end_geom)
        self._cart_anim.finished.connect(self._cart_widget.hide)
        self._cart_anim.start()

    def bind(self, model: CatalogScreenViewModel | object) -> None:
        if not isinstance(model, CatalogScreenViewModel):
            return
        # Категории больше не нужны, просто рендерим все товары
        self.set_catalog_items(list(model.items))

    def set_catalog_items(self, items: list[CatalogItemViewModel], *args) -> None:
        self._catalog_items = items
        self._relayout_grid()

    def _relayout_grid(self) -> None:
        cols = 3
        for i in reversed(range(self._grid.count())):
            item = self._grid.takeAt(i)
            if item is not None:
                if w := item.widget():
                    w.deleteLater()

        for idx, item in enumerate(self._catalog_items):
            row = idx // cols
            col = idx % cols
            card = self._make_product_card(item)
            self._grid.addWidget(card, row, col, Qt.AlignmentFlag.AlignCenter)

        QTimer.singleShot(0, self._reposition_all_images)
        QTimer.singleShot(0, self._reposition_cart_badge)

    def _reposition_cart_badge(self) -> None:
        w = self._cart_btn
        if w.width() > 0:
            self._cart_badge.adjustSize()
            bw = self._cart_badge.width()
            self._cart_badge.move(w.width() - bw + 6, -6)
            self._cart_badge.raise_()

    def _reposition_all_images(self) -> None:
        for i in range(self._grid.count()):
            item = self._grid.itemAt(i)
            if item is not None and item.widget() is not None:
                card = item.widget()
                if hasattr(card, "inner") and card.inner.layout() is not None:
                    child = card.inner.layout().itemAt(0)
                    if child is not None and child.widget() is not None:
                        image_wrap = child.widget()
                        if hasattr(image_wrap, "_reposition_image"):
                            image_wrap._reposition_image()

    @staticmethod
    def _get_rounded_pixmap(pix: QPixmap, w: int, h: int, radius: int) -> QPixmap:
        if pix.isNull() or w <= 0 or h <= 0:
            return pix
        scaled = pix.scaled(
            w,
            h,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = (scaled.width() - w) // 2
        y = (scaled.height() - h) // 2
        scaled = scaled.copy(x, y, w, h)

        out = QPixmap(w, h)
        out.fill(Qt.GlobalColor.transparent)
        painter = QPainter(out)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0, 0, w, h + radius, radius, radius)
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, scaled)
        painter.end()
        return out

    def _generate_placeholder(self, w: int, h: int) -> QPixmap:
        """Генерирует розовую заглушку с текстом."""
        tokens = current_color_tokens()
        bg = "#FDF2F8" if tokens is not DARK_TOKENS else "#3A322F"
        fg = "#D81B60" if tokens is not DARK_TOKENS else tokens.muted_foreground
        pix = QPixmap(w, h)
        pix.fill(QColor(bg))
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setFont(_f(20, 700))
        painter.setPen(QColor(fg))
        painter.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, "Фото недоступно")
        painter.end()
        return pix

    def _load_photo(self, item: CatalogItemViewModel, photo: QLabel, image_wrap: QWidget) -> None:
        pix = QPixmap()
        if item.image_path:
            pix = QPixmap(item.image_path)

        if pix.isNull():
            placeholder_pix = self._generate_placeholder(400, 400)
            photo.setProperty("placeholder", True)
            photo.setProperty("_source_pixmap", placeholder_pix)
            photo._original_pixmap = placeholder_pix
        else:
            photo.setProperty("placeholder", False)
            photo.setProperty("_source_pixmap", pix)
            photo._original_pixmap = pix
        photo.setText("")

    def _make_product_card(self, item: CatalogItemViewModel) -> QWidget:
        card = _ProductCard()
        card.setFixedSize(360, 520)

        layout = QVBoxLayout(card.inner)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        card.inner.setStyleSheet(
            f"""
            QFrame#ProductCard {{
                background-color: {CARD_BG};
                border: none;
                border-radius: 24px;
            }}
            """
        )

        shadow = QGraphicsDropShadowEffect(card.inner)
        shadow.setBlurRadius(35)
        shadow.setColor(QColor(0, 0, 0, 15))
        shadow.setOffset(0, 8)
        card.inner.setGraphicsEffect(shadow)

        image_wrap = QFrame(card.inner)
        image_wrap.setFixedHeight(300)
        image_wrap.setStyleSheet("background: transparent; border: none;")

        photo = QLabel(image_wrap)
        photo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._load_photo(item, photo, image_wrap)

        def _reposition_image() -> None:
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
                rounded = self._get_rounded_pixmap(photo._original_pixmap, pw, ph, 24)
                photo.setPixmap(rounded)

        image_wrap._reposition_image = _reposition_image
        layout.addWidget(image_wrap)

        body = QFrame()
        body.setStyleSheet("background: transparent;")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(24, 20, 24, 24)
        bl.setSpacing(6)

        title = QLabel(item.title)
        title.setFont(_f(22, 600))
        title.setStyleSheet(f"color: {TEXT_MAIN};")
        title.setWordWrap(True)

        desc = QLabel(item.short_description or "")
        desc.setWordWrap(True)
        desc.setFont(_f(14, 400))
        desc.setStyleSheet(f"color: {TEXT_MUTED}; line-height: 1.5;")
        desc.setVisible(bool(item.short_description))

        bl.addWidget(title)
        bl.addWidget(desc)
        bl.addStretch(1)

        footer_row = QHBoxLayout()
        footer_row.setContentsMargins(0, 0, 0, 0)
        footer_row.setAlignment(Qt.AlignmentFlag.AlignBottom)

        price_col = QVBoxLayout()
        price_col.setSpacing(0)

        lbl_caption = QLabel("ЦЕНА")
        lbl_caption.setFont(_f(11, 700))
        lbl_caption.setStyleSheet("color: #A69B96; letter-spacing: 1px;")

        price_value_layout = QHBoxLayout()
        price_value_layout.setContentsMargins(0, 0, 0, 0)
        price_value_layout.setSpacing(6)
        price_value_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)

        lbl_price_val = QLabel(_fmt_price(item.price_minor_units).replace(" ₽", ""))
        lbl_price_val.setFont(_f(28, 400))
        lbl_price_val.setStyleSheet(f"color: {TEXT_MAIN}; background: transparent; padding: 0;")

        lbl_price_cur = QLabel("₽")
        lbl_price_cur.setFont(_f(20, 400))
        lbl_price_cur.setStyleSheet(
            f"color: {TEXT_MUTED}; background: transparent; margin-bottom: 4px;"
        )

        price_value_layout.addWidget(lbl_price_val)
        price_value_layout.addWidget(lbl_price_cur)

        price_col.addWidget(lbl_caption)
        price_col.addLayout(price_value_layout)

        add_btn = QPushButton("В КОРЗИНУ +")
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        add_btn.setFixedHeight(46)
        add_btn.setFont(_f(13, 700))
        add_btn.setEnabled(item.enabled)
        # Статичный стиль без анимаций
        add_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {PRIMARY_COLOR};
                border: none;
                border-radius: 16px;
                color: white;
                padding: 0 16px;
            }}
            QPushButton:disabled {{ background-color: #E5E7EB; color: #9CA3AF; }}
            """
        )
        add_btn.clicked.connect(lambda _checked=False, it=item: self._add_to_cart(it))

        footer_row.addLayout(price_col)
        footer_row.addStretch(1)
        footer_row.addWidget(add_btn, 0, Qt.AlignmentFlag.AlignBottom)

        bl.addLayout(footer_row)
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
                img.setPixmap(self._generate_placeholder(70, 70))
        else:
            img.setPixmap(self._generate_placeholder(70, 70))
        layout.addWidget(img)

        info = QVBoxLayout()
        info.setContentsMargins(0, 0, 0, 0)
        info.setSpacing(2)
        title = QLabel(item.title)
        title.setFont(_f(15, 600))
        title.setStyleSheet("color: #111827;")

        subtitle = QLabel(f"(1 шт.) - {_fmt_price(item.price_minor)} ₽")
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
        minus_btn.setAccessibleName("Уменьшить количество")
        minus_btn.setFixedSize(26, 26)
        minus_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        minus_btn.setIcon(icon(IconName.MINUS, 14, "#374151"))
        # Статичная кнопка
        minus_btn.setStyleSheet("QPushButton { background: transparent; border: none; }")
        minus_btn.clicked.connect(
            lambda _checked=False, p=pid, s=sid: self._cart.update_qty(p, s, -1)
        )

        count_lbl = QLabel(str(item.quantity))
        count_lbl.setFont(_f(15, 600))
        count_lbl.setStyleSheet("color: #111827; background: transparent; border: none;")
        count_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        count_lbl.setFixedWidth(20)

        plus_btn = QPushButton()
        plus_btn.setAccessibleName("Увеличить количество")
        plus_btn.setFixedSize(26, 26)
        plus_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        plus_btn.setIcon(icon(IconName.PLUS, 14, PRIMARY_COLOR))
        if item.quantity >= item.available_quantity:
            plus_btn.setEnabled(False)
            plus_btn.setStyleSheet(
                "QPushButton { background: transparent; border: none; opacity: 0.5; }"
            )
        else:
            plus_btn.setStyleSheet("QPushButton { background: transparent; border: none; }")
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
            if item is not None:
                if w := item.widget():
                    w.deleteLater()
        for it in self._cart.items:
            self._cart_items_layout.addWidget(self._make_cart_item_row(it))
        self._cart_items_layout.addStretch(1)
        self._cart_total_label.setText(f"{_fmt_price(self._cart.total_minor)} ₽")
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
            item.available_quantity,
        )
        self.selection_changed.emit(item.product_id, item.slot_id)
        self._show_cart()

    def _on_checkout(self) -> None:
        if self._cart.is_empty:
            return
        self.checkout_requested.emit()

    def get_cart(self) -> _CartManager:
        return self._cart

    def _on_title_tap(self, *args, **kwargs) -> None:
        self._tap_count += 1
        if self._tap_count >= 5:
            self._tap_count = 0
            self.service_requested.emit()

    def set_service_visible(self, visible: bool) -> None:
        return

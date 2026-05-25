"""Modern Figma-aligned reusable widgets for the flower vending kiosk UI."""

from __future__ import annotations

import time

from PySide6.QtCore import (
    QEvent,
    QPropertyAnimation,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QTouchEvent,
)
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from flower_vending.ui.design_tokens import (
    BrandColors,
    Radius,
    Typography,
)
from flower_vending.ui.icons import IconName, icon


_SPACING_UNIT = 4


def _px(multiplier: float) -> int:
    return round(_SPACING_UNIT * multiplier)


def _font(size: int, weight: int = Typography.WEIGHTS["normal"]) -> QFont:
    f = QFont()
    f.setFamilies([f.strip().strip('"') for f in Typography.FONT_FAMILY.split(",")])
    f.setPixelSize(size)
    from PySide6.QtGui import QFont as _QFont
    _weight_map = {
        300: _QFont.Weight.Light,
        400: _QFont.Weight.Normal,
        500: _QFont.Weight.Medium,
        600: _QFont.Weight.DemiBold,
        700: _QFont.Weight.Bold,
        800: _QFont.Weight.ExtraBold,
        900: _QFont.Weight.Black,
    }
    f.setWeight(_weight_map.get(weight, _QFont.Weight.Normal))
    return f


def repolish(widget: QWidget) -> None:
    try:
        widget.style().unpolish(widget)
    except Exception:
        pass
    try:
        widget.style().polish(widget)
    except Exception:
        pass
    widget.update()


class GradientButton(QPushButton):
    """Primary button with pink→purple gradient matching Figma design."""

    def __init__(
        self,
        label: str,
        *,
        compact: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(label, parent)
        self.setObjectName("PrimaryButton")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setProperty("compact", compact)
        h = 44 if compact else 56
        self.setMinimumHeight(h)
        self.setMaximumHeight(h)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._last_release_ms = 0.0
        self._touch_active = False
        self.setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents, True)
        repolish(self)

    def event(self, event: QEvent) -> bool:
        if event.type() == QEvent.Type.TouchBegin:
            self._touch_active = True
        elif event.type() == QEvent.Type.TouchEnd:
            if self._touch_active:
                self._touch_active = False
                now = time.monotonic() * 1000.0
                if now - self._last_release_ms >= 300:
                    self._last_release_ms = now
                    self.click()
            return True
        elif event.type() == QEvent.Type.TouchCancel:
            self._touch_active = False
        return super().event(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._touch_active:
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._touch_active:
            self.setDown(False)
            event.accept()
            return
        super().mouseReleaseEvent(event)


class OutlineButton(QPushButton):
    """Secondary outline button with pink border."""

    def __init__(
        self,
        label: str,
        *,
        compact: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(label, parent)
        self.setObjectName("SecondaryButton")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setProperty("compact", compact)
        h = 44 if compact else 56
        self.setMinimumHeight(h)
        self.setMaximumHeight(h)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._touch_active = False
        self._last_release_ms = 0.0
        self.setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents, True)
        repolish(self)

    def event(self, event: QEvent) -> bool:
        if event.type() == QEvent.Type.TouchBegin:
            self._touch_active = True
        elif event.type() == QEvent.Type.TouchEnd:
            if self._touch_active:
                self._touch_active = False
                now = time.monotonic() * 1000.0
                if now - self._last_release_ms >= 300:
                    self._last_release_ms = now
                    self.click()
            return True
        elif event.type() == QEvent.Type.TouchCancel:
            self._touch_active = False
        return super().event(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._touch_active:
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._touch_active:
            self.setDown(False)
            event.accept()
            return
        super().mouseReleaseEvent(event)


class GhostButton(QPushButton):
    """Subtle ghost button for secondary actions."""

    def __init__(self, label: str, *, parent: QWidget | None = None) -> None:
        super().__init__(label, parent)
        self.setObjectName("GhostButton")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(44)
        self.setMaximumHeight(44)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        repolish(self)


class IconButton(QPushButton):
    """Square icon button."""

    def __init__(
        self,
        icon_name: IconName,
        *,
        size: int = 44,
        icon_size: int = 20,
        color: str = "#717182",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("IconButton")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(size, size)
        self.setIcon(icon(icon_name, icon_size, color))
        self.setIconSize(QSize(icon_size, icon_size))
        repolish(self)


class DangerButton(QPushButton):
    """Red destructive action button."""

    def __init__(self, label: str, *, parent: QWidget | None = None) -> None:
        super().__init__(label, parent)
        self.setObjectName("DangerButton")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(48)
        self.setMaximumHeight(48)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        repolish(self)


class ChipButton(QPushButton):
    """Pill/chip toggle button."""

    def __init__(self, label: str, *, parent: QWidget | None = None) -> None:
        super().__init__(label, parent)
        self.setObjectName("ChipButton")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(40)
        self.setMaximumHeight(44)
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        repolish(self)


class StatusBadge(QLabel):
    """Status badge pill (green/yellow/red)."""

    def __init__(
        self,
        text: str = "",
        status: str = "info",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        self.setObjectName("Badge")
        self.setProperty("status", status)
        self.setFixedHeight(24)
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        repolish(self)

    def set_status(self, status: str) -> None:
        self.setProperty("status", status)
        repolish(self)


class KpiCard(QFrame):
    """Dashboard KPI metric card with label, value, and icon."""

    def __init__(
        self,
        label: str = "",
        value: str = "",
        icon_name: IconName | None = None,
        accent_color: str = BrandColors.KPI_GREEN,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("KPICard")
        self.setMinimumHeight(100)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        self._value_label = QLabel(value)
        self._value_label.setFont(_font(28, Typography.WEIGHTS["bold"]))
        self._value_label.setStyleSheet(f"color: {accent_color};")
        if icon_name:
            icon_widget = QLabel()
            icon_widget.setPixmap(icon(icon_name, 24, accent_color).pixmap(24, 24))
            icon_widget.setFixedSize(24, 24)
            icon_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
            top.addWidget(self._value_label, 1)
            top.addWidget(icon_widget, 0, Qt.AlignmentFlag.AlignTop)
        else:
            top.addWidget(self._value_label, 1)
        layout.addLayout(top)

        self._label = QLabel(label)
        self._label.setFont(_font(12, Typography.WEIGHTS["medium"]))
        self._label.setStyleSheet(f"color: {BrandColors.GRAY_500};")
        self._label.setWordWrap(True)
        layout.addWidget(self._label)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(12)
        shadow.setXOffset(0)
        shadow.setYOffset(4)
        shadow.setColor(QColor(0, 0, 0, 15))
        self.setGraphicsEffect(shadow)

    def set_value(self, text: str) -> None:
        self._value_label.setText(text)


class ProductCard(QFrame):
    """Product card matching Figma catalog card design."""

    clicked = Signal(str, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ProductCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumWidth(280)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._product_id = ""
        self._slot_id = ""
        self._touch_active = False
        self._last_release_ms = 0.0
        self.setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._photo = QLabel()
        self._photo.setObjectName("ProductPhoto")
        self._photo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._photo.setMinimumHeight(200)
        self._photo.setFixedHeight(200)
        self._photo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._photo.setWordWrap(True)
        self._photo.setText("БУКЕТ")

        info = QWidget()
        info_layout = QVBoxLayout(info)
        info_layout.setContentsMargins(20, 16, 20, 20)
        info_layout.setSpacing(6)

        self._title = QLabel()
        self._title.setObjectName("ProductTitle")
        self._title.setWordWrap(True)
        info_layout.addWidget(self._title)

        self._category = QLabel()
        self._category.setObjectName("ProductCategory")
        info_layout.addWidget(self._category)

        info_layout.addSpacing(4)

        price_row = QHBoxLayout()
        price_row.setContentsMargins(0, 0, 0, 0)
        self._price = QLabel()
        self._price.setObjectName("ProductPrice")
        self._badge = QLabel()
        self._badge.setObjectName("Badge")
        self._badge.hide()
        price_row.addWidget(self._price, 1)
        price_row.addWidget(self._badge, 0)
        info_layout.addLayout(price_row)

        layout.addWidget(self._photo)
        layout.addWidget(info)

    def bind(
        self,
        product_id: str,
        slot_id: str,
        title: str,
        price_text: str,
        category: str = "",
        badge_text: str = "",
        badge_status: str = "info",
        image_path: str | None = None,
        enabled: bool = True,
    ) -> None:
        self._product_id = product_id
        self._slot_id = slot_id
        self._title.setText(title)
        self._price.setText(price_text)
        self._category.setText(category)
        self._category.setVisible(bool(category))
        if badge_text:
            self._badge.setText(badge_text)
            self._badge.setProperty("status", badge_status)
            repolish(self._badge)
            self._badge.show()
        else:
            self._badge.hide()

        if image_path:
            from PySide6.QtGui import QPixmap
            pix = QPixmap(image_path)
            if not pix.isNull():
                scaled = pix.scaled(
                    self._photo.size() if self._photo.width() > 0 else QSize(280, 200),
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self._photo.setPixmap(scaled)
                self._photo.setText("")
                self.setProperty("hasImage", True)
            else:
                self.setProperty("hasImage", False)
        else:
            self.setProperty("hasImage", False)

        self.setProperty("available", enabled)
        self.setEnabled(enabled)
        repolish(self)

    def event(self, event: QEvent) -> bool:
        if event.type() == QEvent.Type.TouchBegin:
            self._touch_active = True
        elif event.type() == QEvent.Type.TouchEnd:
            if self._touch_active:
                self._touch_active = False
                if self.isEnabled() and isinstance(event, QTouchEvent):
                    pts = event.points()
                    if pts and self.rect().contains(pts[0].position().toPoint()):
                        now = time.monotonic() * 1000.0
                        if now - self._last_release_ms >= 300:
                            self._last_release_ms = now
                            self.clicked.emit(self._product_id, self._slot_id)
            return True
        elif event.type() == QEvent.Type.TouchCancel:
            self._touch_active = False
        return super().event(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._touch_active:
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            if self.rect().contains(event.position().toPoint()):
                self.clicked.emit(self._product_id, self._slot_id)
        super().mouseReleaseEvent(event)


class OrderCard(QFrame):
    """Order row card for the orders tab."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.setMinimumHeight(64)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 12, 20, 12)
        layout.setSpacing(16)

        self._id_label = QLabel()
        self._id_label.setFont(_font(14, Typography.WEIGHTS["semibold"]))
        layout.addWidget(self._id_label)

        self._items_label = QLabel()
        self._items_label.setFont(_font(14))
        self._items_label.setStyleSheet(f"color: {BrandColors.GRAY_500};")
        self._items_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(self._items_label, 1)

        self._price_label = QLabel()
        self._price_label.setFont(_font(16, Typography.WEIGHTS["bold"]))
        layout.addWidget(self._price_label)

        self._badge = StatusBadge(status="warning")
        layout.addWidget(self._badge)

    def bind(self, order_id: str, items: str, price: str, status: str, status_text: str) -> None:
        self._id_label.setText(order_id)
        self._items_label.setText(items)
        self._price_label.setText(price)
        self._badge.setProperty("status", status)
        self._badge.setText(status_text)
        repolish(self._badge)


class ToggleSwitch(QWidget):
    """Custom toggle switch matching Figma admin panel design."""

    toggled = Signal(bool)

    def __init__(
        self,
        checked: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._checked = checked
        self.setFixedSize(44, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._knob_anim = QPropertyAnimation(self, b"pos")
        self._knob_offset = 22 if checked else 2

    def is_checked(self) -> bool:
        return self._checked

    def set_checked(self, checked: bool) -> None:
        self._checked = checked
        self._knob_offset = 22 if checked else 2
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._checked = not self._checked
            self._knob_offset = 2 if self._checked else 22
            self.toggled.emit(self._checked)
            self.update()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        track_color = QColor("#9333EA") if self._checked else QColor("#D1D5DB")
        p.setBrush(track_color)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(0, 0, 44, 24, 12, 12)

        knob_color = QColor("#FFFFFF")
        p.setBrush(knob_color)
        p.drawEllipse(self._knob_offset, 3, 18, 18)

        p.end()


class ModernLineEdit(QLineEdit):
    """Styled input field matching Figma admin input design."""

    def __init__(
        self,
        placeholder: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setProperty("class", "adminInput")
        self.setPlaceholderText(placeholder)
        self.setMinimumHeight(42)
        self.setFont(_font(14))
        repolish(self)


class WindowStatusCard(QFrame):
    """Vending window status card for admin panel."""

    action_requested = Signal(str)

    def __init__(
        self,
        window_id: str = "",
        status: str = "free",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._window_id = window_id
        self._status = status
        self.setObjectName("Card")
        self.setMinimumHeight(140)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        color_map = {"free": BrandColors.GREEN_600, "busy": "#CA8A04", "maintenance": BrandColors.RED_600}
        border_color = color_map.get(status, BrandColors.RED_600)
        self.setStyleSheet(f"QFrame#Card {{ border-left: 4px solid {border_color}; }}")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(icon(IconName.BOX, 32, border_color).pixmap(32, 32))
        icon_lbl.setFixedSize(32, 32)
        layout.addWidget(icon_lbl)

        info = QVBoxLayout()
        info.setContentsMargins(0, 0, 0, 0)
        info.setSpacing(4)

        self._title = QLabel(f"Окно {window_id}")
        self._title.setFont(_font(16, Typography.WEIGHTS["semibold"]))
        info.addWidget(self._title)

        self._status_badge = StatusBadge(
            text={"free": "Свободно", "busy": "Занято", "maintenance": "Обслуживание"}.get(status, status),
            status={"free": "success", "busy": "warning", "maintenance": "error"}.get(status, "info"),
        )
        info.addWidget(self._status_badge)

        self._detail = QLabel()
        self._detail.setFont(_font(12))
        self._detail.setStyleSheet(f"color: {BrandColors.GRAY_500};")
        info.addWidget(self._detail)

        layout.addLayout(info, 1)

        actions = QVBoxLayout()
        actions.setSpacing(6)
        free_btn = QPushButton("Освободить")
        free_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        free_btn.setStyleSheet(
            f"QPushButton {{ padding: 6px 14px; border-radius: {Radius.MD}px; "
            f"border: none; background: {BrandColors.GREEN_600}; color: #FFFFFF; font-size: 13px; }}"
            f"QPushButton:hover {{ background: #15803D; }}"
        )
        free_btn.clicked.connect(lambda: self.action_requested.emit(f"window_free:{window_id}"))
        actions.addWidget(free_btn)

        maint_btn = QPushButton("Сервис" if status != "maintenance" else "Вернуть")
        maint_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        maint_btn.setStyleSheet(
            f"QPushButton {{ padding: 6px 14px; border-radius: {Radius.MD}px; "
            f"border: none; background: {BrandColors.RED_600 if status != 'maintenance' else BrandColors.PURPLE_600}; "
            f"color: #FFFFFF; font-size: 13px; }}"
        )
        maint_btn.clicked.connect(lambda: self.action_requested.emit(f"window_toggle_maintenance:{window_id}"))
        actions.addWidget(maint_btn)

        layout.addLayout(actions)

    def set_status(self, status: str, detail: str = "") -> None:
        self._status = status
        color_map = {"free": BrandColors.GREEN_600, "busy": "#CA8A04", "maintenance": BrandColors.RED_600}
        border_color = color_map.get(status, BrandColors.RED_600)
        self.setStyleSheet(f"QFrame#Card {{ border-left: 4px solid {border_color}; }}")
        self._status_badge.setProperty("status", {"free": "success", "busy": "warning", "maintenance": "error"}.get(status, "info"))
        self._status_badge.setText({"free": "Свободно", "busy": "Занято", "maintenance": "Обслуживание"}.get(status, status))
        repolish(self._status_badge)
        self._detail.setText(detail)


class SectionHeader(QWidget):
    """Section divider with uppercase title."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(40)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        lbl = QLabel(title)
        lbl.setObjectName("SectionTitle")
        layout.addWidget(lbl)
        layout.addStretch(1)


class BadgedButton(QPushButton):
    """Button with a notification badge."""

    def __init__(
        self,
        label: str = "",
        badge_count: int = 0,
        icon_name: IconName | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(label, parent)
        self._badge_count = badge_count


class AnimatedCheckLabel(QLabel):
    """Animated green checkmark for success screens."""

    def __init__(self, size: int = 96, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity)

        self._anim = QPropertyAnimation(self._opacity, b"opacity", self)
        self._anim.setDuration(400)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)

        self._check_color = QColor(BrandColors.GREEN_600)

    def show_animated(self) -> None:
        self._anim.stop()
        self._anim.start()

    def paintEvent(self, event) -> None:
        QLabel.paintEvent(self, event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        cx = self.width() // 2
        cy = self.height() // 2
        r = min(self.width(), self.height()) // 2 - 4

        p.setBrush(QColor(BrandColors.GREEN_100))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(cx - r, cy - r, r * 2, r * 2)

        pen = QPen(QColor(BrandColors.GREEN_600))
        pen.setWidth(4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)

        path = QPainterPath()
        path.moveTo(cx - r * 0.35, cy)
        path.lineTo(cx - r * 0.05, cy + r * 0.3)
        path.lineTo(cx + r * 0.4, cy - r * 0.25)
        p.drawPath(path)

        p.end()


class SpinnerWidget(QWidget):
    """Animated spinning loader."""

    def __init__(self, size: int = 64, color: str = "#EC4899", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._color = QColor(color)
        self._angle = 0.0
        self._timer = None
        self._anim: QPropertyAnimation | None = None

    def start(self) -> None:
        self._anim = QPropertyAnimation(self, b"size")
        self.show()

    def stop(self) -> None:
        self.hide()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.translate(self.width() / 2, self.height() / 2)
        r = min(self.width(), self.height()) / 2 - 8

        for i in range(12):
            p.rotate(30)
            alpha = 1.0 - i / 12.0
            c = QColor(self._color)
            c.setAlphaF(alpha)
            p.setBrush(c)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(-3, -r, 6, r * 0.3, 3, 3)

        p.end()

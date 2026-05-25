"""Reusable touch-friendly Qt controls."""

from __future__ import annotations

import time

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QPoint,
    QPropertyAnimation,
    Qt,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QMouseEvent,
    QPaintEvent,
    QPainter,
    QPixmap,
    QResizeEvent,
    QTouchEvent,
)
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsBlurEffect,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from flower_vending.ui.viewmodels import BannerViewModel, CatalogItemViewModel


_TAP_DEBOUNCE_MS = 500.0


def repolish(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


class TouchButton(QPushButton):
    def __init__(
        self,
        label: str,
        *,
        secondary: bool = False,
        compact: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(label, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setProperty("secondary", secondary)
        self.setProperty("compact", compact)

        if compact:
            self.setMinimumHeight(44)
            self.setMaximumHeight(48)
        else:
            self.setMinimumHeight(64)
            self.setMaximumHeight(64)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._last_release_monotonic_ms = 0.0
        self._touch_active = False
        self.setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents, True)

    def event(self, event: QEvent) -> bool:
        if event.type() == QEvent.Type.TouchBegin:
            self._touch_active = True
        elif event.type() == QEvent.Type.TouchEnd:
            if self._touch_active:
                self._touch_active = False
                current_ms = time.monotonic() * 1000.0
                if current_ms - self._last_release_monotonic_ms >= _TAP_DEBOUNCE_MS:
                    self._last_release_monotonic_ms = current_ms
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
        if event.button() != Qt.MouseButton.LeftButton:
            super().mouseReleaseEvent(event)
            return
        current_monotonic_ms = time.monotonic() * 1000.0
        if current_monotonic_ms - self._last_release_monotonic_ms < _TAP_DEBOUNCE_MS:
            self.setDown(False)
            event.accept()
            return
        self._last_release_monotonic_ms = current_monotonic_ms
        super().mouseReleaseEvent(event)


class BannerWidget(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Banner")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(4)
        self._title = QLabel()
        self._title.setObjectName("BannerTitle")
        self._message = QLabel()
        self._message.setObjectName("BannerMessage")
        self._message.setWordWrap(True)
        layout.addWidget(self._title)
        layout.addWidget(self._message)
        self.hide()

    def bind(self, banner: BannerViewModel | None) -> None:
        if banner is None:
            self.hide()
            repolish(self)
            return
        tone = banner.tone.value
        self.setProperty("tone", tone)
        self._title.setText(banner.title)
        self._message.setText(banner.message)
        self._title.setProperty("tone", tone)
        self._message.setProperty("tone", tone)
        repolish(self)
        repolish(self._title)
        repolish(self._message)
        self.show()


class ProductPhotoLabel(QLabel):
    def __init__(self, *, height: int = 180, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ProductPhoto")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedHeight(height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setWordWrap(True)
        self._source_pixmap: QPixmap | None = None
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(1.0)
        self.setGraphicsEffect(self._opacity_effect)
        self._fade_animation = QPropertyAnimation(self._opacity_effect, b"opacity", self)
        self._fade_animation.setDuration(300)
        self._fade_animation.setEasingCurve(QEasingCurve.Type.InOutCubic)

    _FLOWER_PLACEHOLDER_MAP = {
        "Розы": "РОЗЫ",
        "Тюльпаны": "ТЮЛЬПАНЫ",
        "Букеты": "БУКЕТ",
        "Сезонные": "СЕЗОН",
        "Подарочные": "ПОДАРОК",
        "Цветы": "ЦВЕТЫ",
    }

    def set_image(self, image_path: str | None, *, fallback_text: str) -> None:
        pixmap = QPixmap(image_path) if image_path else QPixmap()
        self._source_pixmap = None if pixmap.isNull() else pixmap
        self.setProperty("hasImage", self._source_pixmap is not None)
        if self._source_pixmap is None:
            self.setPixmap(QPixmap())
            placeholder = self._FLOWER_PLACEHOLDER_MAP.get(fallback_text, "БУКЕТ")
            self.setText(f"{placeholder}\n{fallback_text}")
        else:
            self.setText("")
        repolish(self)
        self._refresh_pixmap()
        self._start_fade_in()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._refresh_pixmap()

    def _refresh_pixmap(self) -> None:
        if self._source_pixmap is None or self.width() <= 0 or self.height() <= 0:
            return
        scaled = self._source_pixmap.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = max(0, (scaled.width() - self.width()) // 2)
        y = max(0, (scaled.height() - self.height()) // 2)
        self.setPixmap(scaled.copy(x, y, self.width(), self.height()))

    def _start_fade_in(self) -> None:
        self._fade_animation.stop()
        self._opacity_effect.setOpacity(1.0)


class ProductTile(QFrame):
    selected = Signal(str, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ProductTile")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumSize(270, 360)
        self.setMaximumSize(16777215, 16777215)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._product_id = ""
        self._slot_id = ""
        self._last_release_monotonic_ms = 0.0
        self._touch_active = False
        self.setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents, True)
        self.setProperty("pressed", False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(9)

        self._photo = ProductPhotoLabel(height=146)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)
        self._title = QLabel()
        self._title.setObjectName("ProductTitle")
        self._title.setWordWrap(True)
        self._title.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._badge = QLabel()
        self._badge.setObjectName("Badge")
        header.addWidget(self._title, 1)
        header.addWidget(self._badge, 0, Qt.AlignmentFlag.AlignTop)

        self._category = QLabel()
        self._category.setObjectName("ProductMeta")
        self._category.setWordWrap(True)
        self._category.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._description = QLabel()
        self._description.setObjectName("ProductDescription")
        self._description.setWordWrap(True)
        self._description.setMinimumHeight(42)
        self._description.setMaximumHeight(50)
        self._description.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._price = QLabel()
        self._price.setObjectName("ProductPrice")
        self._price.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._availability = QLabel()
        self._availability.setObjectName("StockLabel")
        self._availability.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout.addWidget(self._photo)
        layout.addLayout(header)
        layout.addWidget(self._description)
        layout.addWidget(self._category)
        layout.addStretch(1)
        layout.addWidget(self._price)
        layout.addWidget(self._availability)

    def bind(self, item: CatalogItemViewModel) -> None:
        self._product_id = item.product_id
        self._slot_id = item.slot_id
        self._title.setText(item.title)
        self._badge.setText(item.badge_text or "")
        self._badge.setVisible(bool(item.badge_text))
        meta = " · ".join(text for text in (item.category_label, item.freshness_note) if text)
        self._category.setText(meta)
        self._description.setText(item.short_description or "")
        self._description.setVisible(bool(item.short_description))
        self._price.setText(item.price_text)
        self._availability.setText(item.availability_text)
        self._photo.set_image(item.image_path, fallback_text=item.category_label or "Букет")
        self.setProperty("available", item.enabled)
        self.setProperty("lowStock", item.availability_text == "Остался 1")
        self.setProperty("pressed", False)
        self.setEnabled(item.enabled)
        repolish(self)
        repolish(self._availability)

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", selected)
        repolish(self)

    def event(self, event: QEvent) -> bool:
        if event.type() == QEvent.Type.TouchBegin:
            self._touch_active = True
        elif event.type() == QEvent.Type.TouchEnd:
            if self._touch_active:
                self._touch_active = False
                if self.isEnabled() and isinstance(event, QTouchEvent):
                    tp = event.points()[0] if event.points() else None
                    if tp is not None and self.rect().contains(tp.position().toPoint()):
                        current_ms = time.monotonic() * 1000.0
                        if current_ms - self._last_release_monotonic_ms >= _TAP_DEBOUNCE_MS:
                            self._last_release_monotonic_ms = current_ms
                            self.selected.emit(self._product_id, self._slot_id)
            return True
        elif event.type() == QEvent.Type.TouchCancel:
            self._touch_active = False
        return super().event(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._touch_active:
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            self.setProperty("pressed", True)
            repolish(self)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._touch_active:
            self.setProperty("pressed", False)
            repolish(self)
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self.setProperty("pressed", False)
            repolish(self)
            if self.isEnabled() and self.rect().contains(event.position().toPoint()):
                current_monotonic_ms = time.monotonic() * 1000.0
                if current_monotonic_ms - self._last_release_monotonic_ms >= _TAP_DEBOUNCE_MS:
                    self._last_release_monotonic_ms = current_monotonic_ms
                    self.selected.emit(self._product_id, self._slot_id)
        super().mouseReleaseEvent(event)


class SmoothScrollArea(QScrollArea):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SmoothScrollArea")
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self._velocity = 0.0
        self._last_touch_y = 0.0
        self._last_touch_ms = 0.0
        self._tracking = False

        self._scroll_anim = QVariantAnimation(self)
        self._scroll_anim.setDuration(400)
        self._scroll_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._scroll_anim.valueChanged.connect(self._on_scroll_anim_value)

        self._start_value = 0
        self._target_value = 0

    def event(self, event: QEvent) -> bool:
        if event.type() == QEvent.Type.TouchBegin:
            self._scroll_anim.stop()
            tp = self._touch_point(event)
            if tp is not None:
                self._last_touch_y = tp.y()
                self._last_touch_ms = time.monotonic() * 1000.0
            self._tracking = True
        elif event.type() == QEvent.Type.TouchUpdate and self._tracking:
            tp = self._touch_point(event)
            if tp is not None:
                now_ms = time.monotonic() * 1000.0
                dy = self._last_touch_y - tp.y()
                dt_ms = now_ms - self._last_touch_ms
                if dt_ms > 0:
                    self._velocity = dy / dt_ms * 16.0
                sb = self.verticalScrollBar()
                sb.setValue(sb.value() + int(dy))
                self._last_touch_y = tp.y()
                self._last_touch_ms = now_ms
            return True
        elif event.type() == QEvent.Type.TouchEnd and self._tracking:
            self._tracking = False
            if abs(self._velocity) > 1.0:
                target = self.verticalScrollBar().value() + int(self._velocity * 20.0)
                self._start_scroll_animation(target)
            self._velocity = 0.0
            return True
        elif event.type() == QEvent.Type.TouchCancel:
            self._tracking = False
            self._velocity = 0.0
        return super().event(event)

    def _touch_point(self, event: QEvent) -> QPoint | None:
        if isinstance(event, QTouchEvent):
            pts = event.points()
            return pts[0].position().toPoint() if pts else None
        return None

    def _start_scroll_animation(self, target: int) -> None:
        sb = self.verticalScrollBar()
        target = max(sb.minimum(), min(sb.maximum(), target))
        self._start_value = sb.value()
        self._target_value = target
        self._scroll_anim.stop()
        self._scroll_anim.setStartValue(float(self._start_value))
        self._scroll_anim.setEndValue(float(self._target_value))
        self._scroll_anim.start()

    def _on_scroll_anim_value(self, value: float) -> None:
        self.verticalScrollBar().setValue(int(value))


class BlurOverlayWidget(QWidget):
    def __init__(self, parent: QWidget, *, tint_color: QColor | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self._tint_color = tint_color or QColor(26, 20, 16, 140)
        self._blur_radius = 12.0
        self._snapshot = QPixmap()
        self._blur_effect: QGraphicsBlurEffect | None = None
        self._blur_label: QLabel | None = None

    def capture(self) -> None:
        target = self.parentWidget()
        if target is None:
            return
        self.resize(target.size())
        self._snapshot = target.grab()
        if self._blur_label is not None:
            self._blur_label.deleteLater()
        self._blur_label = QLabel(self)
        self._blur_label.resize(self.size())
        self._blur_label.setPixmap(self._snapshot)
        if self._blur_effect is not None:
            self._blur_label.setGraphicsEffect(self._blur_effect)
        else:
            self._blur_effect = QGraphicsBlurEffect(self._blur_label)
            self._blur_effect.setBlurRadius(self._blur_radius)
            self._blur_label.setGraphicsEffect(self._blur_effect)

    def set_blur_radius(self, radius: float) -> None:
        self._blur_radius = max(0.0, radius)
        if self._blur_effect is not None:
            self._blur_effect.setBlurRadius(self._blur_radius)

    def show(self) -> None:
        self.capture()
        self.raise_()
        super().show()

    def hide(self) -> None:
        if self._blur_label is not None:
            self._blur_label.hide()
        super().hide()

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QBrush(self._tint_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(self.rect())
        painter.end()

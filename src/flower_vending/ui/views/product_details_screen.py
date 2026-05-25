"""Product details screen with full product info and payment method selector."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from flower_vending.ui.design_tokens import BrandColors, Radius, Typography
from flower_vending.ui.icons import IconName, icon
from flower_vending.ui.viewmodels import ProductDetailsScreenViewModel
from flower_vending.ui.widgets.modern import GradientButton, OutlineButton


class ProductDetailsScreenWidget(QWidget):
    back_requested = Signal()
    pay_requested = Signal(str)

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
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(0)

        back_wrap = QWidget()
        back_layout = QHBoxLayout(back_wrap)
        back_layout.setContentsMargins(0, 0, 0, 16)
        back_btn = QLabel()
        back_btn.setPixmap(icon(IconName.ARROW_LEFT, 24, BrandColors.GRAY_500).pixmap(24, 24))
        back_btn.setFixedSize(44, 44)
        back_btn.setAlignment(Qt.AlignmentFlag.AlignCenter)
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.mouseReleaseEvent = lambda e: self.back_requested.emit()
        back_layout.addWidget(back_btn)
        back_layout.addStretch(1)
        layout.addWidget(back_wrap)

        content = QHBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(40)

        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(12)

        self._photo = QLabel()
        self._photo.setObjectName("ProductPhoto")
        self._photo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._photo.setMinimumSize(400, 400)
        self._photo.setFixedSize(420, 420)
        self._photo.setWordWrap(True)
        self._photo.setText("БУКЕТ")
        left.addWidget(self._photo)
        content.addLayout(left, 1)

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(16)

        self._title = QLabel()
        self._title.setObjectName("HeroTitle")
        self._title.setWordWrap(True)
        right.addWidget(self._title)

        self._category = QLabel()
        self._category.setObjectName("ProductCategory")
        right.addWidget(self._category)

        self._price = QLabel()
        self._price.setObjectName("ProductPrice")
        self._price.setStyleSheet("font-size: 36px;")
        right.addWidget(self._price)

        self._stock_label = QLabel()
        self._stock_label.setStyleSheet(
            f"font-size: 15px; color: {BrandColors.GREEN_600}; font-weight: {Typography.WEIGHTS['semibold']};"
        )
        right.addWidget(self._stock_label)

        self._description = QLabel()
        self._description.setWordWrap(True)
        self._description.setStyleSheet(
            f"font-size: 16px; color: {BrandColors.GRAY_500}; line-height: 1.6;"
        )
        right.addWidget(self._description)

        self._advisory = QLabel()
        self._advisory.setWordWrap(True)
        self._advisory.setStyleSheet(
            f"font-size: 14px; color: {BrandColors.YELLOW_600}; "
            f"background: {BrandColors.YELLOW_100}; border-radius: {Radius.LG}px; padding: 12px 16px;"
        )
        self._advisory.hide()
        right.addWidget(self._advisory)

        right.addStretch(1)

        self._payment_methods_wrap = QWidget()
        pm_layout = QHBoxLayout(self._payment_methods_wrap)
        pm_layout.setContentsMargins(0, 0, 0, 0)
        pm_layout.setSpacing(12)
        pm_layout.addStretch(1)
        right.addWidget(self._payment_methods_wrap)

        buttons = QHBoxLayout()
        buttons.setSpacing(16)
        self._back_btn = OutlineButton("Назад")
        self._back_btn.clicked.connect(lambda: self.back_requested.emit())
        self._pay_btn = GradientButton("Оплатить")
        self._pay_btn.clicked.connect(lambda: self.pay_requested.emit("cash"))
        buttons.addWidget(self._back_btn)
        buttons.addWidget(self._pay_btn)
        right.addLayout(buttons)

        content.addLayout(right, 1)
        layout.addLayout(content)

    def bind(self, model: ProductDetailsScreenViewModel | object) -> None:
        if not isinstance(model, ProductDetailsScreenViewModel):
            return
        self._title.setText(model.title)
        self._category.setText(model.category_label or "")
        self._category.setVisible(bool(model.category_label))
        self._price.setText(model.price_text)
        self._stock_label.setText(model.availability_text)
        self._stock_label.setVisible(bool(model.availability_text))
        self._description.setText(model.short_description or "")
        self._description.setVisible(bool(model.short_description))

        if model.advisory_text:
            self._advisory.setText(model.advisory_text)
            self._advisory.show()
        else:
            self._advisory.hide()

        self._pay_btn.setEnabled(model.primary_action.enabled)
        self._pay_btn.setText(model.primary_action.label)

        if model.image_path:
            pix = QPixmap(model.image_path)
            if not pix.isNull():
                scaled = pix.scaled(
                    420, 420,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self._photo.setPixmap(scaled)
                self._photo.setText("")

        pm_layout = self._payment_methods_wrap.layout()
        for i in reversed(range(pm_layout.count())):
            item = pm_layout.takeAt(i)
            if item is not None and item.widget() is not None:
                item.widget().deleteLater()

        pm_layout.addStretch(1)
        for method in model.payment_methods:
            chip = self._make_payment_chip(method.label, method.action_id)
            chip.mouseReleaseEvent = lambda e, m=method.action_id: self.pay_requested.emit(m)
            pm_layout.addWidget(chip)
        pm_layout.addStretch(1)

    def _make_payment_chip(self, label: str, method_id: str) -> QWidget:
        chip = QWidget()
        chip.setCursor(Qt.CursorShape.PointingHandCursor)
        chip.setFixedHeight(64)
        chip.setMinimumWidth(140)
        chip.setMaximumWidth(250)
        chip.setStyleSheet(
            f"background: #FFFFFF; border: none; "
            f"border-radius: {Radius.XL}px;"
        )
        chip_layout = QVBoxLayout(chip)
        chip_layout.setContentsMargins(16, 10, 16, 10)
        icon_map = {"cash": IconName.WALLET, "card": IconName.CREDIT_CARD, "sbp": IconName.REFRESH_CW}
        ic = icon(icon_map.get(method_id, IconName.WALLET), 24, BrandColors.PURPLE_600)
        icon_lbl = QLabel()
        icon_lbl.setPixmap(ic.pixmap(24, 24))
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl = QLabel(label)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet(f"font-size: 13px; font-weight: {Typography.WEIGHTS['medium']}; color: {BrandColors.GRAY_500};")
        chip_layout.addWidget(icon_lbl)
        chip_layout.addWidget(lbl)
        return chip

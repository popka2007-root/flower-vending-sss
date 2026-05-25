"""Admin settings tab — form fields, toggle switches, save button."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from flower_vending.ui.design_tokens import BrandColors, Radius, Typography
from flower_vending.ui.viewmodels.screens import AdminSettingsTabViewModel
from flower_vending.ui.widgets.modern import ToggleSwitch


def _make_section(title: str, parent: QWidget | None = None) -> tuple[QWidget, QVBoxLayout]:
    outer = QWidget(parent)
    outer.setStyleSheet(f"background: #FFFFFF; border-radius: {Radius.XL}px; border: none;")

    outer_layout = QVBoxLayout(outer)
    outer_layout.setContentsMargins(0, 0, 0, 0)
    outer_layout.setSpacing(0)

    header = QWidget()
    header.setFixedHeight(48)
    header.setStyleSheet(
        f"background: {BrandColors.GRAY_50}; border-radius: {Radius.XL}px {Radius.XL}px 0 0;"
    )
    header_layout = QHBoxLayout(header)
    header_layout.setContentsMargins(20, 0, 20, 0)
    header_lbl = QLabel(title.upper())
    header_lbl.setStyleSheet(
        f"font-size: 13px; font-weight: {Typography.WEIGHTS['semibold']}; "
        f"color: {BrandColors.GRAY_500}; text-transform: uppercase;"
    )
    header_layout.addWidget(header_lbl)
    outer_layout.addWidget(header)

    body = QWidget()
    body_layout = QVBoxLayout(body)
    body_layout.setContentsMargins(20, 16, 20, 16)
    body_layout.setSpacing(16)
    outer_layout.addWidget(body)

    return outer, body_layout


def _make_field(label: str, widget: QWidget) -> QWidget:
    field = QWidget()
    layout = QVBoxLayout(field)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)

    lbl = QLabel(label)
    lbl.setStyleSheet(
        f"font-size: 13px; font-weight: {Typography.WEIGHTS['medium']}; "
        f"color: {BrandColors.GRAY_500};"
    )
    layout.addWidget(lbl)
    layout.addWidget(widget)
    return field


class _ToggleRow(QWidget):
    def __init__(self, label: str, checked: bool, on_toggled) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        lbl = QLabel(label)
        lbl.setStyleSheet(f"font-size: 14px; font-weight: {Typography.WEIGHTS['medium']};")
        layout.addWidget(lbl, 1)
        self._toggle = ToggleSwitch(checked)
        self._toggle.toggled.connect(on_toggled)
        layout.addWidget(self._toggle)

    def set_checked(self, checked: bool) -> None:
        self._toggle.set_checked(checked)


class SettingsTab(QWidget):
    action_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(24)

        header = QHBoxLayout()
        title = QLabel("Настройки")
        title.setStyleSheet(f"font-size: 24px; font-weight: {Typography.WEIGHTS['bold']};")
        header.addWidget(title)
        header.addStretch(1)

        self._save_btn = QPushButton("Сохранить")
        self._save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._save_btn.setFixedHeight(40)
        self._save_btn.setStyleSheet(
            f"QPushButton {{ padding: 8px 20px; border-radius: {Radius.XL}px; "
            f"border: none; font-size: 14px; font-weight: {Typography.WEIGHTS['semibold']}; "
            f"background: {BrandColors.PURPLE_600}; color: #FFFFFF; }}"
            f"QPushButton:hover {{ background: {BrandColors.PINK_500}; }}"
        )
        self._save_btn.clicked.connect(lambda: self.action_requested.emit("admin_save_settings"))
        header.addWidget(self._save_btn)
        layout.addLayout(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(20)

        general_section, general_body = _make_section("Основные")
        self._name_input = QLineEdit()
        self._name_input.setProperty("class", "adminInput")
        self._name_input.setStyleSheet(
            f"QLineEdit {{ min-height: 42px; padding: 8px 12px; "
            f"border: 1px solid {BrandColors.GRAY_300}; border-radius: {Radius.XL}px; "
            f"font-size: 14px; background: {BrandColors.GRAY_100}; }}"
            f"QLineEdit:focus {{ border-color: {BrandColors.PURPLE_600}; }}"
        )
        self._hours_input = QLineEdit()
        self._hours_input.setStyleSheet(self._name_input.styleSheet())
        self._phone_input = QLineEdit()
        self._phone_input.setStyleSheet(self._name_input.styleSheet())
        self._email_input = QLineEdit()
        self._email_input.setStyleSheet(self._name_input.styleSheet())

        general_body.addWidget(_make_field("Название вендинга", self._name_input))
        general_body.addWidget(_make_field("Часы работы", self._hours_input))
        general_body.addWidget(_make_field("Телефон для связи", self._phone_input))
        general_body.addWidget(_make_field("Email поддержки", self._email_input))
        content_layout.addWidget(general_section)

        payment_section, payment_body = _make_section("Способы оплаты")
        self._cash_toggle = _ToggleRow(
            "Наличные", True, lambda v: self.action_requested.emit(f"tgl:cash:{1 if v else 0}")
        )
        self._card_toggle = _ToggleRow(
            "Банковская карта",
            False,
            lambda v: self.action_requested.emit(f"tgl:card:{1 if v else 0}"),
        )
        self._sbp_toggle = _ToggleRow(
            "СБП (QR-код)", False, lambda v: self.action_requested.emit(f"tgl:sbp:{1 if v else 0}")
        )
        payment_body.addWidget(self._cash_toggle)
        payment_body.addWidget(self._card_toggle)
        payment_body.addWidget(self._sbp_toggle)
        content_layout.addWidget(payment_section)

        inv_section, inv_body = _make_section("Склад и уведомления")
        self._restock_toggle = _ToggleRow(
            "Авто-пополнение",
            False,
            lambda v: self.action_requested.emit(f"tgl:restock:{1 if v else 0}"),
        )
        self._notify_order = _ToggleRow(
            "Уведомлять о заказах",
            False,
            lambda v: self.action_requested.emit(f"tgl:notify_order:{1 if v else 0}"),
        )
        self._notify_low = _ToggleRow(
            "Уведомлять о низком остатке",
            False,
            lambda v: self.action_requested.emit(f"tgl:notify_low:{1 if v else 0}"),
        )
        inv_body.addWidget(self._restock_toggle)
        inv_body.addWidget(self._notify_order)
        inv_body.addWidget(self._notify_low)
        content_layout.addWidget(inv_section)

        pricing_section, pricing_body = _make_section("Цены и лимиты")
        _spin_style = (
            f"QSpinBox {{ min-height: 42px; padding: 8px 12px; "
            f"border: 1px solid {BrandColors.GRAY_300}; border-radius: {Radius.XL}px; "
            f"font-size: 14px; background: {BrandColors.GRAY_100}; }}"
            f"QSpinBox:focus {{ border-color: {BrandColors.PURPLE_600}; }}"
            f"QSpinBox::up-button {{ border: none; background: transparent; width: 28px; "
            f"subcontrol-origin: border; subcontrol-position: top right; "
            f"border-left: 1px solid {BrandColors.GRAY_200}; }}"
            f"QSpinBox::down-button {{ border: none; background: transparent; width: 28px; "
            f"subcontrol-origin: border; subcontrol-position: bottom right; "
            f"border-left: 1px solid {BrandColors.GRAY_200}; }}"
            f"QSpinBox::up-arrow {{ width: 10px; height: 10px; }}"
            f"QSpinBox::down-arrow {{ width: 10px; height: 10px; }}"
            f"QSpinBox::up-button:hover {{ background: {BrandColors.GRAY_200}; }}"
            f"QSpinBox::down-button:hover {{ background: {BrandColors.GRAY_200}; }}"
        )
        self._min_order_spin = QSpinBox()
        self._min_order_spin.setMinimum(0)
        self._min_order_spin.setMaximum(999999)
        self._min_order_spin.setSuffix(" ₽")
        self._min_order_spin.setStyleSheet(_spin_style)
        self._discount_spin = QSpinBox()
        self._discount_spin.setMinimum(0)
        self._discount_spin.setMaximum(100)
        self._discount_spin.setSuffix(" %")
        self._discount_spin.setStyleSheet(_spin_style)
        self._markup_spin = QSpinBox()
        self._markup_spin.setMinimum(0)
        self._markup_spin.setMaximum(1000)
        self._markup_spin.setSuffix(" %")
        self._markup_spin.setStyleSheet(_spin_style)
        self._threshold_spin = QSpinBox()
        self._threshold_spin.setMinimum(1)
        self._threshold_spin.setMaximum(999)
        self._threshold_spin.setStyleSheet(_spin_style)

        pricing_body.addWidget(_make_field("Мин. сумма заказа", self._min_order_spin))
        pricing_body.addWidget(_make_field("Скидка", self._discount_spin))
        pricing_body.addWidget(_make_field("Наценка", self._markup_spin))
        pricing_body.addWidget(_make_field("Порог остатка для уведомлений", self._threshold_spin))
        content_layout.addWidget(pricing_section)

        security_section, security_body = _make_section("Безопасность")
        self._pin_input = QLineEdit()
        self._pin_input.setStyleSheet(self._name_input.styleSheet())
        self._pin_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._pin_input.setMaxLength(4)
        self._pin_input.setPlaceholderText("Новый PIN-код (4 цифры)")

        pin_widget = QWidget()
        pin_row = QHBoxLayout(pin_widget)
        pin_row.setContentsMargins(0, 0, 0, 0)
        pin_row.addWidget(self._pin_input)
        change_btn = QPushButton("Сменить PIN")
        change_btn.setFixedWidth(140)
        change_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        change_btn.setStyleSheet(
            f"QPushButton {{ padding: 8px 16px; border-radius: {Radius.MD}px; "
            f"border: 1px solid rgba(0,0,0,0.12); font-size: 13px; "
            f"font-weight: {Typography.WEIGHTS['medium']}; background: #FFFFFF; }}"
            f"QPushButton:hover {{ background: {BrandColors.GRAY_100}; }}"
        )
        change_btn.clicked.connect(self._change_pin)
        pin_row.addWidget(change_btn)
        security_body.addWidget(_make_field("Изменить PIN-код", pin_widget))
        content_layout.addWidget(security_section)

        content_layout.addStretch(1)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

    def _change_pin(self) -> None:
        new_pin = self._pin_input.text().strip()
        if len(new_pin) != 4 or not new_pin.isdigit():
            self._pin_input.setStyleSheet(
                f"QLineEdit {{ min-height: 42px; padding: 8px 12px; "
                f"border: 2px solid #EF4444; border-radius: {Radius.XL}px; "
                f"font-size: 14px; background: {BrandColors.GRAY_100}; }}"
            )
            return
        self._pin_input.setStyleSheet(self._name_input.styleSheet())
        self.action_requested.emit(f"admin_change_pin:{new_pin}")

    def bind(self, model: AdminSettingsTabViewModel | object) -> None:
        if not isinstance(model, AdminSettingsTabViewModel):
            return
        self._name_input.setText(model.vending_name)
        self._hours_input.setText(model.working_hours)
        self._phone_input.setText(model.contact_phone)
        self._email_input.setText(model.support_email)

        self._cash_toggle.set_checked(model.accept_cash)
        self._card_toggle.set_checked(model.accept_card)
        self._sbp_toggle.set_checked(model.accept_sbp)
        self._restock_toggle.set_checked(model.auto_restock)
        self._notify_order.set_checked(model.notify_on_order)
        self._notify_low.set_checked(model.notify_on_low_stock)

        self._min_order_spin.setValue(model.min_order_amount)
        self._discount_spin.setValue(model.discount_percent)
        self._markup_spin.setValue(model.price_markup)
        self._threshold_spin.setValue(model.restock_threshold)

"""Diagnostics screen — machine state, device list, event log, recovery."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from flower_vending.ui.design_tokens import BrandColors, Radius, Typography
from flower_vending.ui.viewmodels import DiagnosticsScreenViewModel, DiagnosticsDeviceViewModel
from flower_vending.ui.widgets.modern import GradientButton


class DiagnosticsScreenWidget(QWidget):
    back_requested = Signal()
    recover_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ServiceScreen")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(20)

        header = QHBoxLayout()
        title = QLabel("Диагностика")
        title.setStyleSheet(f"font-size: 28px; font-weight: {Typography.WEIGHTS['bold']};")
        header.addWidget(title)
        header.addStretch(1)

        back_btn = GradientButton("Назад", compact=True)
        back_btn.clicked.connect(lambda: self.back_requested.emit())
        back_btn.setFixedWidth(120)
        header.addWidget(back_btn)
        layout.addLayout(header)

        self._subtitle = QLabel()
        self._subtitle.setStyleSheet(f"font-size: 14px; color: {BrandColors.GRAY_500};")
        layout.addWidget(self._subtitle)

        info_row = QHBoxLayout()
        info_row.setSpacing(16)

        state_card = QWidget()
        state_card.setStyleSheet(
            f"background: #FFFFFF; border-radius: {Radius.XL}px; border: none;"
        )
        state_layout = QVBoxLayout(state_card)
        state_layout.setContentsMargins(20, 16, 20, 16)
        state_layout.setSpacing(8)
        state_title = QLabel("Состояние автомата")
        state_title.setStyleSheet(
            f"font-size: 14px; font-weight: {Typography.WEIGHTS['semibold']};"
        )
        self._state_value = QLabel()
        self._state_value.setStyleSheet(
            f"font-size: 20px; font-weight: {Typography.WEIGHTS['bold']}; color: {BrandColors.PURPLE_600};"
        )
        state_layout.addWidget(state_title)
        state_layout.addWidget(self._state_value)
        info_row.addWidget(state_card)

        blockers_card = QWidget()
        blockers_card.setStyleSheet(
            f"background: #FFFFFF; border-radius: {Radius.XL}px; border: none;"
        )
        blockers_layout = QVBoxLayout(blockers_card)
        blockers_layout.setContentsMargins(20, 16, 20, 16)
        blockers_layout.setSpacing(8)
        blockers_title = QLabel("Блокировки продаж")
        blockers_title.setStyleSheet(
            f"font-size: 14px; font-weight: {Typography.WEIGHTS['semibold']};"
        )
        self._blockers_value = QLabel()
        self._blockers_value.setWordWrap(True)
        self._blockers_value.setStyleSheet(f"font-size: 14px; color: {BrandColors.RED_600};")
        blockers_layout.addWidget(blockers_title)
        blockers_layout.addWidget(self._blockers_value)
        info_row.addWidget(blockers_card)

        layout.addLayout(info_row)

        devices_card = QWidget()
        devices_card.setStyleSheet(
            f"background: #FFFFFF; border-radius: {Radius.XL}px; border: none;"
        )
        devices_layout = QVBoxLayout(devices_card)
        devices_layout.setContentsMargins(20, 16, 20, 16)
        devices_layout.setSpacing(8)
        devices_title = QLabel("Устройства")
        devices_title.setStyleSheet(
            f"font-size: 14px; font-weight: {Typography.WEIGHTS['semibold']};"
        )
        devices_layout.addWidget(devices_title)

        self._device_list = QVBoxLayout()
        devices_layout.addLayout(self._device_list)
        layout.addWidget(devices_card)

        events_card = QWidget()
        events_card.setStyleSheet(
            f"background: #FFFFFF; border-radius: {Radius.XL}px; border: none;"
        )
        events_layout = QVBoxLayout(events_card)
        events_layout.setContentsMargins(20, 16, 20, 16)
        events_layout.setSpacing(4)
        events_title = QLabel("Последние события")
        events_title.setStyleSheet(
            f"font-size: 14px; font-weight: {Typography.WEIGHTS['semibold']};"
        )
        events_layout.addWidget(events_title)

        self._events_list = QVBoxLayout()
        events_layout.addLayout(self._events_list)
        layout.addWidget(events_card)

        self._tx_section = QWidget()
        tx_layout = QVBoxLayout(self._tx_section)
        tx_layout.setContentsMargins(0, 0, 0, 0)
        tx_layout.setSpacing(8)
        self._tx_list = QVBoxLayout()
        tx_layout.addLayout(self._tx_list)
        layout.addWidget(self._tx_section)

        layout.addStretch(1)

    def bind(self, model: DiagnosticsScreenViewModel | object) -> None:
        if not isinstance(model, DiagnosticsScreenViewModel):
            return
        self._subtitle.setText(model.subtitle)
        self._state_value.setText(model.machine_state)

        blockers_text = ", ".join(model.sale_blockers) if model.sale_blockers else "Нет"
        self._blockers_value.setText(blockers_text)

        for i in reversed(range(self._device_list.count())):
            item = self._device_list.takeAt(i)
            if item is not None and item.widget() is not None:
                item.widget().deleteLater()

        for device in model.devices:
            self._device_list.addWidget(self._make_device_row(device))

        for i in reversed(range(self._events_list.count())):
            item = self._events_list.takeAt(i)
            if item is not None and item.widget() is not None:
                item.widget().deleteLater()

        for event_text in model.recent_events[-20:]:
            lbl = QLabel(event_text)
            lbl.setStyleSheet(f"font-size: 12px; color: {BrandColors.GRAY_500};")
            self._events_list.addWidget(lbl)

        for i in reversed(range(self._tx_list.count())):
            item = self._tx_list.takeAt(i)
            if item is not None and item.widget() is not None:
                item.widget().deleteLater()
            elif item is not None and item.layout() is not None:
                pass  # sub-layout removed by takeAt above

        for tx_id in model.unresolved_transactions:
            row = QHBoxLayout()
            lbl = QLabel(f"Незавершённая транзакция: {tx_id}")
            lbl.setStyleSheet(f"font-size: 14px; color: {BrandColors.YELLOW_600};")
            row.addWidget(lbl, 1)
            recover_btn = QPushButton("Восстановить")
            recover_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            recover_btn.setStyleSheet(
                f"QPushButton {{ padding: 6px 14px; border-radius: {Radius.MD}px; "
                f"border: none; background: {BrandColors.PURPLE_600}; color: #FFFFFF; "
                f"font-size: 13px; }}"
            )
            recover_btn.clicked.connect(lambda checked, t=tx_id: self.recover_requested.emit(t))
            row.addWidget(recover_btn)
            self._tx_list.addLayout(row)

        self._tx_section.setVisible(bool(model.unresolved_transactions))

    def _make_device_row(self, device: DiagnosticsDeviceViewModel) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(8)

        color_map = {
            "green": BrandColors.GREEN_600,
            "yellow": "#CA8A04",
            "red": BrandColors.RED_600,
            "gray": BrandColors.GRAY_500,
        }
        dot_color = color_map.get(device.state_color, color_map["gray"])
        dot = QLabel("●")
        dot.setStyleSheet(f"color: {dot_color}; font-size: 16px;")
        dot.setFixedWidth(24)
        layout.addWidget(dot)

        name_lbl = QLabel(device.device_name)
        name_lbl.setStyleSheet(f"font-size: 14px; font-weight: {Typography.WEIGHTS['medium']};")
        layout.addWidget(name_lbl)

        state_lbl = QLabel(device.state)
        state_lbl.setStyleSheet(f"font-size: 14px; color: {BrandColors.GRAY_500};")
        layout.addWidget(state_lbl, 1)

        return row

"""Payment screen — shows price, accepted amount, remaining, sim quick-insert buttons."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from flower_vending.ui.design_tokens import BrandColors, Radius
from flower_vending.ui.viewmodels import PaymentScreenViewModel
from flower_vending.ui.widgets.controls import BannerWidget
from flower_vending.ui.widgets.modern import OutlineButton


class PaymentScreenWidget(QWidget):
    cancel_requested = Signal()
    simulator_action_requested = Signal(str)

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
        layout.setContentsMargins(48, 48, 48, 48)
        layout.setSpacing(0)

        self._product_name = QLabel()
        self._product_name.setObjectName("HeroTitle")
        layout.addWidget(self._product_name)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 8, 0, 0)
        self._subtitle = QLabel()
        self._subtitle.setObjectName("Subtitle")
        header_row.addWidget(self._subtitle)
        header_row.addStretch(1)
        layout.addLayout(header_row)

        self._banner = BannerWidget()
        layout.addSpacing(16)
        layout.addWidget(self._banner)

        metrics_container = QWidget()
        metrics = QVBoxLayout(metrics_container)
        metrics.setContentsMargins(0, 24, 0, 24)
        metrics.setSpacing(16)

        self._price_card = self._make_metric("Стоимость", "")
        self._accepted_card = self._make_metric("Внесено", "")
        self._remaining_card = self._make_metric("Осталось", "")
        self._change_card = self._make_metric("Сдача", "")

        row1 = QHBoxLayout()
        row1.setSpacing(16)
        row1.addWidget(self._price_card)
        row1.addWidget(self._accepted_card)
        metrics.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(16)
        row2.addWidget(self._remaining_card)
        row2.addWidget(self._change_card)
        metrics.addLayout(row2)

        layout.addWidget(metrics_container)

        self._progress_bar = QProgressBar()
        self._progress_bar.setFixedHeight(8)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setStyleSheet(
            f"QProgressBar {{ background: {BrandColors.GRAY_100}; border-radius: 4px; border: none; }}"
            f"QProgressBar::chunk {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, "
            f"stop:0 {BrandColors.PINK_500}, stop:1 {BrandColors.PURPLE_600}); "
            f"border-radius: 4px; }}"
        )
        self._progress_bar.setVisible(False)
        layout.addWidget(self._progress_bar)
        layout.addSpacing(8)

        self._sim_label = QLabel("Сумма внесения")
        self._sim_label.setObjectName("SectionTitle")
        self._sim_label.setVisible(False)
        self._sim_label.setStyleSheet(
            f"font-size: 16px; font-weight: 600; color: {BrandColors.GRAY_500};"
        )
        layout.addWidget(self._sim_label)

        self._sim_buttons = QWidget()
        self._sim_layout = QHBoxLayout(self._sim_buttons)
        self._sim_layout.setContentsMargins(0, 4, 0, 0)
        self._sim_layout.setSpacing(10)
        self._sim_buttons.setVisible(False)
        layout.addWidget(self._sim_buttons)

        layout.addStretch(1)

        self._help_text = QLabel()
        self._help_text.setWordWrap(True)
        self._help_text.setStyleSheet(
            f"font-size: 16px; color: {BrandColors.GRAY_500}; "
            f"background: #FFFFFF; border-radius: {Radius.XL}px; "
            f"padding: 20px 24px; border: none;"
        )
        layout.addWidget(self._help_text)

        layout.addSpacing(24)

        buttons = QHBoxLayout()
        buttons.setSpacing(16)
        self._cancel_btn = OutlineButton("Отмена")
        self._cancel_btn.clicked.connect(lambda: self.cancel_requested.emit())
        buttons.addWidget(self._cancel_btn)
        buttons.addStretch(1)
        layout.addLayout(buttons)

    def _make_metric(self, caption: str, value: str) -> QFrame:
        card = QFrame()
        card.setObjectName("MetricCard")
        card.setMinimumHeight(100)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        inner = QVBoxLayout(card)
        inner.setContentsMargins(20, 16, 20, 16)
        inner.setSpacing(6)

        cap_lbl = QLabel(caption)
        cap_lbl.setObjectName("MetricCaption")
        inner.addWidget(cap_lbl)

        val_lbl = QLabel(value)
        val_lbl.setObjectName("MetricValue")
        inner.addWidget(val_lbl)

        card._val_label = val_lbl
        return card

    def bind(self, model: PaymentScreenViewModel | object) -> None:
        if not isinstance(model, PaymentScreenViewModel):
            return
        self._product_name.setText(model.product_name)
        self._subtitle.setText(model.subtitle)
        self._banner.bind(model.banner)
        self._help_text.setText(model.help_text)

        self._price_card._val_label.setText(model.price_text)
        self._accepted_card._val_label.setText(model.accepted_text)
        self._remaining_card._val_label.setText(model.remaining_text)
        self._change_card._val_label.setText(model.change_text)

        self._remaining_card._val_label.setProperty("accent", bool(model.remaining_text != "0 ₽"))

        self._cancel_btn.setText(model.cancel_action.label)
        self._cancel_btn.setEnabled(model.cancel_action.enabled)

        has_sim = bool(model.quick_insert_actions)
        is_cash = model.payment_method == "cash" and model.price_text != "0 ₽"
        self._progress_bar.setVisible(is_cash)
        self._sim_label.setVisible(has_sim)
        self._sim_buttons.setVisible(has_sim)

        if is_cash:
            self._update_progress(model)

        for i in reversed(range(self._sim_layout.count())):
            item = self._sim_layout.takeAt(i)
            if item is not None:
                if w := item.widget():
                    w.deleteLater()

        for action in model.quick_insert_actions:
            btn = QPushButton(action.label)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.setMinimumHeight(48)
            btn.setStyleSheet(
                f"QPushButton {{ padding: 10px 20px; border: 2px solid {BrandColors.PURPLE_600}; "
                f"border-radius: {Radius.XL}px; font-size: 15px; font-weight: 700; "
                f"background: #FFFFFF; color: {BrandColors.PURPLE_600}; }}"
                f"QPushButton:hover {{ background: {BrandColors.PURPLE_600}; color: #FFFFFF; }}"
            )
            btn.clicked.connect(
                lambda checked, a=action.action_id: self.simulator_action_requested.emit(a)
            )
            self._sim_layout.addWidget(btn)
        self._sim_layout.addStretch(1)

    def _update_progress(self, model: PaymentScreenViewModel) -> None:
        try:
            price = int(
                model.price_text.replace("\u202f", "")
                .replace("\u00a0", "")
                .replace(" ", "")
                .replace("₽", "")
                .strip()
            )
            accepted = int(
                model.accepted_text.replace("\u202f", "")
                .replace("\u00a0", "")
                .replace(" ", "")
                .replace("₽", "")
                .strip()
            )
        except (ValueError, AttributeError):
            return
        if price <= 0:
            return
        pct = int(min(accepted / price, 1.0) * 100)
        self._progress_bar.setValue(pct)

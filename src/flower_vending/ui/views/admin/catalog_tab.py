"""Admin catalog management tab — product grid with edit/hide/delete."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from flower_vending.ui.design_tokens import BrandColors, Radius, Typography
from flower_vending.ui.icons import IconName, icon
from flower_vending.ui.viewmodels.screens import AdminCatalogItemViewModel, AdminCatalogTabViewModel
from flower_vending.ui.widgets.modern import ToggleSwitch


def _load_photo(photo: QLabel, image_path: str | None) -> None:
    if image_path:
        pix = QPixmap(image_path)
        if not pix.isNull():
            h = photo.height() or 160
            scaled = pix.scaledToHeight(h, Qt.TransformationMode.SmoothTransformation)
            photo.setPixmap(scaled)
            return
    photo.setPixmap(icon(IconName.FLOWER, 48, "#D1D5DB").pixmap(48, 48))


class _ProductDialog(QDialog):
    def __init__(
        self,
        title: str,
        parent: QWidget | None = None,
        product: AdminCatalogItemViewModel | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(400)
        self.setStyleSheet(f"QDialog {{ background: #FFFFFF; border-radius: {Radius.XL}px; }}")

        layout = QFormLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        self._name = QLineEdit()
        self._name.setPlaceholderText("Название букета")
        self._name.setMinimumHeight(36)
        self._price = QSpinBox()
        self._price.setMinimum(1)
        self._price.setMaximum(999999)
        self._price.setSuffix(" ₽")
        self._price.setMinimumHeight(36)
        self._stock = QSpinBox()
        self._stock.setMinimum(0)
        self._stock.setMaximum(999)
        self._stock.setMinimumHeight(36)
        self._category = QLineEdit()
        self._category.setPlaceholderText("Категория")
        self._category.setMinimumHeight(36)

        if product:
            self._name.setText(product.title)
            self._category.setText(product.category)
        else:
            self._price.setValue(2500)
            self._stock.setValue(10)
            self._category.setText("Букеты")

        layout.addRow("Название:", self._name)
        layout.addRow("Цена:", self._price)
        layout.addRow("Остаток:", self._stock)
        layout.addRow("Категория:", self._category)

        btns = QHBoxLayout()
        cancel = QPushButton("Отмена")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Сохранить" if product else "Добавить")
        save.setStyleSheet(
            f"QPushButton {{ padding: 8px 20px; border-radius: {Radius.MD}px; "
            f"border: none; background: {BrandColors.PURPLE_600}; color: #FFFFFF; font-size: 14px; font-weight: 600; }}"
        )
        save.clicked.connect(self._on_save)
        btns.addStretch(1)
        btns.addWidget(cancel)
        btns.addWidget(save)
        layout.addRow(btns)

    def _on_save(self) -> None:
        name = self._name.text().strip()
        if not name:
            return
        self.accept()

    def product_data(self) -> tuple[str, int, int, str]:
        return (
            self._name.text().strip(),
            self._price.value(),
            self._stock.value(),
            self._category.text().strip(),
        )


class CatalogTab(QWidget):
    action_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(24)

        header = QHBoxLayout()
        title = QLabel("Каталог товаров")
        title.setStyleSheet(f"font-size: 24px; font-weight: {Typography.WEIGHTS['bold']};")
        header.addWidget(title)
        header.addStretch(1)

        add_btn = QPushButton("+ Добавить букет")
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setFixedHeight(40)
        add_btn.setStyleSheet(
            f"QPushButton {{ padding: 8px 20px; border-radius: {Radius.XL}px; "
            f"border: none; font-size: 14px; font-weight: {Typography.WEIGHTS['semibold']}; "
            f"background: {BrandColors.PURPLE_600}; color: #FFFFFF; }}"
            f"QPushButton:hover {{ background: {BrandColors.PINK_500}; }}"
        )
        add_btn.clicked.connect(self._open_add_dialog)
        header.addWidget(add_btn)
        layout.addLayout(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self._grid_container = QWidget()
        self._grid = QGridLayout(self._grid_container)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(16)
        self._grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        scroll.setWidget(self._grid_container)
        layout.addWidget(scroll, 1)

    def _open_add_dialog(self) -> None:
        dlg = _ProductDialog("Добавить букет", self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            name, price, stock, cat = dlg.product_data()
            self.action_requested.emit(f"admin_add_product:{name}:{price}:{stock}:{cat}")

    def bind(self, model: AdminCatalogTabViewModel | object) -> None:
        if not isinstance(model, AdminCatalogTabViewModel):
            return

        for i in reversed(range(self._grid.count())):
            item = self._grid.takeAt(i)
            if item is not None:
                if w := item.widget():
                    w.deleteLater()

        for idx, product in enumerate(model.products):
            card = self._make_product_card(product)
            row, col = divmod(idx, 2)
            self._grid.addWidget(card, row, col)

    def _make_product_card(self, product: AdminCatalogItemViewModel) -> QWidget:
        card = QWidget()
        card.setStyleSheet(f"background: #FFFFFF; border-radius: {Radius.XL2}px; border: none;")
        card.setMinimumHeight(340)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        photo = QLabel()
        photo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        photo.setFixedHeight(160)
        photo.setStyleSheet(
            f"background: {BrandColors.GRAY_100}; border-radius: {Radius.XL2}px {Radius.XL2}px 0 0;"
        )
        _load_photo(photo, product.image_path)
        card_layout.addWidget(photo)

        info = QVBoxLayout()
        info.setContentsMargins(16, 12, 16, 16)
        info.setSpacing(6)

        title_row = QHBoxLayout()
        title_lbl = QLabel(product.title)
        title_lbl.setStyleSheet(f"font-size: 16px; font-weight: {Typography.WEIGHTS['semibold']};")
        title_row.addWidget(title_lbl, 1)

        toggle_wrap = QWidget()
        toggle_hl = QHBoxLayout(toggle_wrap)
        toggle_hl.setContentsMargins(0, 0, 0, 0)
        toggle_hl.setSpacing(6)
        active_lbl = QLabel("Активен")
        active_lbl.setStyleSheet(f"font-size: 12px; color: {BrandColors.GRAY_500};")
        toggle_hl.addWidget(active_lbl)
        active_toggle = ToggleSwitch(product.active)
        active_toggle.toggled.connect(
            lambda checked, pid=product.product_id: self.action_requested.emit(
                f"admin_toggle:{pid}:{1 if checked else 0}"
            )
        )
        toggle_hl.addWidget(active_toggle)
        toggle_hl.addStretch(1)
        title_row.addWidget(toggle_wrap)
        info.addLayout(title_row)

        price_lbl = QLabel(product.price_text)
        price_lbl.setStyleSheet(
            f"font-size: 18px; font-weight: {Typography.WEIGHTS['bold']}; color: {BrandColors.PURPLE_600};"
        )
        info.addWidget(price_lbl)

        stock_row = QHBoxLayout()
        stock_row.setSpacing(8)
        stock_lbl = QLabel("Остаток:")
        stock_lbl.setStyleSheet(f"font-size: 13px; color: {BrandColors.GRAY_500};")
        stock_row.addWidget(stock_lbl)
        stock_spin = QSpinBox()
        stock_spin.setValue(product.stock)
        stock_spin.setMinimum(0)
        stock_spin.setMaximum(999)
        stock_spin.setFixedWidth(80)
        stock_spin.setStyleSheet(
            f"QSpinBox {{ padding: 4px 8px; border: 1px solid {BrandColors.GRAY_200}; "
            f"border-radius: 8px; font-size: 14px; background: {BrandColors.GRAY_50}; }}"
            f"QSpinBox::up-button {{ border: none; background: transparent; width: 20px; "
            f"subcontrol-origin: border; subcontrol-position: top right; }}"
            f"QSpinBox::down-button {{ border: none; background: transparent; width: 20px; "
            f"subcontrol-origin: border; subcontrol-position: bottom right; }}"
            f"QSpinBox::up-button:hover {{ background: {BrandColors.GRAY_200}; border-radius: 0 8px 0 0; }}"
            f"QSpinBox::down-button:hover {{ background: {BrandColors.GRAY_200}; border-radius: 0 0 8px 0; }}"
        )
        stock_spin.valueChanged.connect(
            lambda val, pid=product.product_id: self.action_requested.emit(
                f"admin_stock:{pid}:{val}"
            )
        )
        stock_row.addWidget(stock_spin)
        stock_row.addStretch(1)
        info.addLayout(stock_row)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        for act_id, act_label, act_color in [
            ("edit", "Ред.", BrandColors.GRAY_500),
            ("toggle", "Скрыть" if product.active else "Показать", "#CA8A04"),
            ("delete", "Удалить", "#EF4444"),
        ]:
            btn = QPushButton(act_label)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(
                f"QPushButton {{ padding: 6px 12px; border-radius: {Radius.MD}px; "
                f"font-size: 12px; background: #FFFFFF; "
                f"color: {act_color}; border: 1px solid rgba(0,0,0,0.12); }}"
                f"QPushButton:hover {{ background: {BrandColors.GRAY_100}; }}"
            )
            if act_id == "edit":
                btn.clicked.connect(lambda checked=False, p=product: self._open_edit_dialog(p))
            elif act_id == "delete":
                btn.clicked.connect(lambda checked=False, p=product: self._confirm_delete(p))
            else:
                btn.clicked.connect(
                    lambda checked=False, aid=f"admin_{act_id}:{product.product_id}": (
                        self.action_requested.emit(aid)
                    )
                )
            actions.addWidget(btn)
        info.addLayout(actions)

        card_layout.addLayout(info)
        return card

    def _open_edit_dialog(self, product: AdminCatalogItemViewModel) -> None:
        dlg = _ProductDialog("Редактировать букет", self, product=product)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            name, price, stock, cat = dlg.product_data()
            self.action_requested.emit(
                f"admin_edit:{product.product_id}:{name}:{price}:{stock}:{cat}"
            )

    def _confirm_delete(self, product: AdminCatalogItemViewModel) -> None:
        msg = QMessageBox(self)
        msg.setWindowTitle("Удаление товара")
        msg.setText(f"Удалить «{product.title}»?")
        msg.setInformativeText("Это действие нельзя отменить.")
        msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msg.setDefaultButton(QMessageBox.StandardButton.No)
        if msg.exec() == QMessageBox.StandardButton.Yes:
            self.action_requested.emit(f"admin_delete:{product.product_id}")

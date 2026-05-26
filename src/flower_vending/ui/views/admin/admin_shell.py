"""Admin panel shell — sidebar navigation + stacked content tabs."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from flower_vending.ui.design_tokens import BrandColors, Radius, Typography
from flower_vending.ui.icons import IconName, icon
from flower_vending.ui.navigation import ScreenId
from flower_vending.ui.widgets.modern import repolish


NAV_ITEMS = [
    (ScreenId.ADMIN_ORDERS, "Заказы", IconName.PACKAGE),
    (ScreenId.ADMIN_ANALYTICS, "Аналитика", IconName.CHART_BAR),
    (ScreenId.ADMIN_CATALOG, "Каталог", IconName.FLOWER),
    (ScreenId.ADMIN_WINDOWS, "Окна выдачи", IconName.BOX),
    (ScreenId.ADMIN_SETTINGS, "Настройки", IconName.SETTINGS),
]

SIDEBAR_WIDTH = 240


class AdminShell(QWidget):
    nav_clicked = Signal(str)
    exit_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"background: {BrandColors.CREAM_BACKGROUND};")
        self._tabs_by_name: dict[str, QWidget] = {}

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        sidebar = QWidget()
        sidebar.setObjectName("AdminSidebar")
        sidebar.setFixedWidth(SIDEBAR_WIDTH)
        sidebar.setStyleSheet(
            f"QWidget#AdminSidebar {{ background: {BrandColors.TEXT_MAIN}; "
            f"border-right: 1px solid {BrandColors.GRAY_200}; }}"
        )
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)

        logo = QWidget()
        logo.setFixedHeight(72)
        logo_layout = QHBoxLayout(logo)
        logo_layout.setContentsMargins(20, 0, 20, 0)

        logo_icon = QWidget()
        logo_icon.setFixedSize(36, 36)
        logo_icon.setStyleSheet(
            f"background: {BrandColors.ORANGE_PRIMARY}; "
            f"border-radius: {Radius.LG}px;"
        )
        logo_icon_layout = QVBoxLayout(logo_icon)
        logo_icon_layout.setContentsMargins(0, 0, 0, 0)
        shield = QLabel()
        shield.setPixmap(icon(IconName.SHIELD_CHECK, 20, "#FFFFFF").pixmap(20, 20))
        shield.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_icon_layout.addWidget(shield)

        logo_text = QLabel("Админ-панель")
        logo_text.setStyleSheet(
            f"font-size: 16px; font-weight: {Typography.WEIGHTS['semibold']}; margin-left: 10px; color: #FFFFFF;"
        )

        logo_layout.addWidget(logo_icon)
        logo_layout.addWidget(logo_text)
        sidebar_layout.addWidget(logo)

        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: rgba(0,0,0,0.06);")
        sidebar_layout.addWidget(sep)

        self._nav_btns: dict[str, QPushButton] = {}
        for screen_id, label, icon_name in NAV_ITEMS:
            btn = QPushButton()
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(48)
            btn.setStyleSheet(
                f"QPushButton {{ text-align: left; padding: 0 20px; border: none; "
                f"font-size: 14px; font-weight: {Typography.WEIGHTS['medium']}; "
                f"color: rgba(255,255,255,0.60); border-radius: 0; "
                f"min-height: 48px; max-height: 48px; "
                f"background: transparent; }}"
                f"QPushButton:hover {{ background: rgba(255,255,255,0.08); "
                f"color: #FFFFFF; }}"
                f'QPushButton[active="true"] {{ background: rgba(255,255,255,0.10); '
                f"color: #FFFFFF; "
                f"border-left: 4px solid {BrandColors.ORANGE_PRIMARY}; }}"
            )
            btn_layout = QHBoxLayout(btn)
            btn_layout.setContentsMargins(20, 0, 20, 0)
            btn_layout.setSpacing(12)
            ic = QLabel()
            ic.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            ic.setPixmap(icon(icon_name, 20, "rgba(255,255,255,0.60)").pixmap(20, 20))
            ic.setFixedSize(20, 20)
            btn_layout.addWidget(ic)
            lbl = QLabel(label)
            lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            lbl.setStyleSheet(
                f"font-size: 14px; font-weight: {Typography.WEIGHTS['medium']}; color: rgba(255,255,255,0.60); background: transparent;"
            )
            btn_layout.addWidget(lbl)
            btn_layout.addStretch(1)

            if screen_id == ScreenId.ADMIN_ORDERS:
                self._orders_badge = QLabel()
                self._orders_badge.setFixedSize(24, 24)
                self._orders_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self._orders_badge.setStyleSheet(
                    "background: #EF4444; color: #FFFFFF; border-radius: 12px; "
                    "font-size: 12px; font-weight: bold;"
                )
                self._orders_badge.hide()
                btn_layout.addWidget(self._orders_badge)

            btn.clicked.connect(lambda checked, sid=screen_id.value: self.nav_clicked.emit(sid))
            sidebar_layout.addWidget(btn)
            self._nav_btns[screen_id.value] = btn

        sidebar_layout.addStretch(1)

        exit_btn = QPushButton()
        exit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        exit_btn.setFixedHeight(56)
        exit_btn.setStyleSheet(
            f"QPushButton {{ border: none; background: transparent; "
            f"border-radius: {Radius.XL}px; margin: 8px 12px; }}"
            f"QPushButton:hover {{ background: {BrandColors.RED_100}; }}"
        )
        exit_layout = QHBoxLayout(exit_btn)
        exit_layout.setContentsMargins(16, 0, 16, 0)
        exit_layout.setSpacing(12)
        exit_icon = QLabel()
        exit_icon.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        exit_icon.setPixmap(icon(IconName.LOG_OUT, 20, BrandColors.RED_600).pixmap(20, 20))
        exit_layout.addWidget(exit_icon)
        exit_lbl = QLabel("Выйти")
        exit_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        exit_lbl.setStyleSheet(
            f"font-size: 15px; font-weight: {Typography.WEIGHTS['semibold']}; color: {BrandColors.RED_600};"
        )
        exit_layout.addWidget(exit_lbl)
        exit_layout.addStretch(1)
        exit_btn.clicked.connect(lambda: self.exit_requested.emit())
        sidebar_layout.addWidget(exit_btn)

        sidebar_layout.addSpacing(12)

        layout.addWidget(sidebar)

        self._stack = QStackedWidget()
        self._stack.setObjectName("AdminContent")
        layout.addWidget(self._stack, 1)

    def add_tab(self, name: str, widget: QWidget) -> None:
        self._tabs_by_name[name] = widget
        self._stack.addWidget(widget)

    def show_tab(self, name: str) -> None:
        tab = self._tabs_by_name.get(name)
        if tab is not None:
            self._stack.setCurrentWidget(tab)
        for nav_id, btn in self._nav_btns.items():
            btn.setProperty("active", nav_id == name)
            repolish(btn)

    def set_pending_count(self, count: int) -> None:
        if hasattr(self, "_orders_badge"):
            if count > 0:
                self._orders_badge.setText(str(count))
                self._orders_badge.show()
            else:
                self._orders_badge.hide()

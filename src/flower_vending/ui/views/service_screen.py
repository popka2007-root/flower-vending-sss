"""Service mode screen."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from flower_vending.ui.design_tokens import (
    DARK_TOKENS,
    BrandColors,
    current_color_tokens,
)
from flower_vending.ui.viewmodels.screens import (
    ActionButtonViewModel,
    ServiceActionGroupViewModel,
    ServiceScreenViewModel,
    ServiceTabViewModel,
)
from flower_vending.ui.widgets.modern import ToggleSwitch


def _scale(widget: QWidget) -> float:
    return max(0.85, min(1.3, widget.logicalDpiX() / 96.0))


def _px(widget: QWidget, n: float) -> int:
    return round(4 * n * _scale(widget))


def _wrap_card(widget: QWidget, title: str, body: QWidget | None = None) -> QWidget:
    card = QWidget()
    tokens = current_color_tokens()
    card.setStyleSheet(f"background: {tokens.card}; border: none; border-radius: 16px;")
    cl = QVBoxLayout(card)
    cl.setContentsMargins(0, 0, 0, 0)
    cl.setSpacing(0)

    head = QWidget()
    head.setFixedHeight(_px(widget, 12))  # Слегка увеличили высоту шапки карты
    head_bg = "#F8FAFC" if tokens is not DARK_TOKENS else "#2A2422"
    head.setStyleSheet(f"background: {head_bg}; border-radius: 16px 16px 0 0;")
    hl = QHBoxLayout(head)
    hl.setContentsMargins(_px(widget, 4), 0, _px(widget, 4), 0)

    t = QLabel(title.upper())
    t.setStyleSheet(
        f"font-size: 14px; font-weight: 700; color: {tokens.muted_foreground}; letter-spacing: 0.5px;"
    )
    hl.addWidget(t)
    cl.addWidget(head)

    if body is not None:
        bw = QVBoxLayout()
        bw.setContentsMargins(_px(widget, 4), _px(widget, 4), _px(widget, 4), _px(widget, 4))
        bw.setSpacing(_px(widget, 3))
        bw.addWidget(body)
        c = QWidget()
        c.setLayout(bw)
        cl.addWidget(c)
    return card


class ServiceScreenWidget(QWidget):
    action_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ServiceScreen")
        self.setStyleSheet(f"QWidget#ServiceScreen {{ background: {BrandColors.GRAY_50}; }}")

        # Избавились от внешнего QScrollArea, чтобы зафиксировать шапку сверху
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(_px(self, 8), _px(self, 6), _px(self, 8), _px(self, 6))
        self._layout.setSpacing(_px(self, 4))

        self._tab_buttons = []
        self._tab_stack = None

    @staticmethod
    def _clear_layout(layout: QLayout) -> None:
        for i in reversed(range(layout.count())):
            item = layout.takeAt(i)
            if item is not None:
                if w := item.widget():
                    w.setParent(None)
                    w.deleteLater()
                    continue
                subl = item.layout()
                if subl is not None:
                    ServiceScreenWidget._clear_layout(subl)

    def bind(self, model: ServiceScreenViewModel | object) -> None:
        if not isinstance(model, ServiceScreenViewModel):
            return
        self._clear_layout(self._layout)
        tokens = current_color_tokens()

        # Блок заголовков
        title = QLabel(model.title)
        title.setStyleSheet(f"font-size: 44px; font-weight: 800; color: {tokens.foreground};")
        sub = QLabel(model.subtitle)
        sub.setStyleSheet(f"font-size: 16px; color: {tokens.muted_foreground};")
        self._layout.addWidget(title)
        self._layout.addWidget(sub)

        # KPI блоки
        if model.kpi:
            self._layout.addWidget(self._build_kpi_row(model))

        tabs = model.tabs
        if not tabs:
            return

        # Навигация (Табы)
        tab_bar = self._build_tab_bar(tabs)
        self._layout.addWidget(tab_bar)

        # Контентная зона (Стек страниц)
        self._tab_stack = QStackedWidget()
        for tab in tabs:
            page = self._build_tab_page(tab)
            self._tab_stack.addWidget(page)

        self._layout.addWidget(self._tab_stack, 1)

        if self._tab_buttons:
            self._switch_tab(0)

    def _build_tab_bar(self, tabs: tuple[ServiceTabViewModel, ...]) -> QWidget:
        bar = QWidget()
        tokens = current_color_tokens()
        bar.setStyleSheet(f"background: {tokens.card}; border: none; border-radius: 14px;")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(_px(self, 1.5), _px(self, 1.5), _px(self, 1.5), _px(self, 1.5))
        bl.setSpacing(_px(self, 1))

        self._tab_buttons = []
        for i, tab in enumerate(tabs):
            btn = QPushButton(tab.label)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.setFixedHeight(_px(self, 11))  # Слегка увеличили высоту табов для пальцев
            btn.clicked.connect(lambda _checked=False, idx=i: self._switch_tab(idx))
            self._tab_buttons.append(btn)
            bl.addWidget(btn, 1)

        bl.addStretch(2)
        return bar

    def _switch_tab(self, index: int) -> None:
        # Добавлен :pressed эффект для неактивных вкладок
        tokens = current_color_tokens()
        active_style = f"""
            QPushButton {{ border-radius: 12px; font-size: 18px; font-weight: 700; padding: 0 14px; background: {tokens.chart_1}; color: #FFFFFF; border: none; }}
        """
        inactive_bg = "#F1F5F9" if tokens is not DARK_TOKENS else "#2A2422"
        inactive_style = f"""
            QPushButton {{ border-radius: 12px; font-size: 18px; font-weight: 700; padding: 0 14px; background: {inactive_bg}; color: {tokens.muted_foreground}; border: none; }}
            QPushButton:pressed {{ background: {tokens.secondary}; }}
        """
        for i, btn in enumerate(self._tab_buttons):
            btn.setStyleSheet(active_style if i == index else inactive_style)
        if self._tab_stack:
            self._tab_stack.setCurrentIndex(index)

    def _build_tab_page(self, tab: ServiceTabViewModel) -> QWidget:
        # Скролл теперь только здесь — внутри конкретного таба
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        content = QWidget()
        cl = QVBoxLayout(content)
        cl.setContentsMargins(0, _px(self, 2), 0, 0)
        cl.setSpacing(_px(self, 4))

        for group in tab.groups:
            if group.variant == "toggles":
                cl.addWidget(self._build_product_toggles(group.label, group.actions))
            else:
                cl.addWidget(self._build_action_group(group))
        cl.addStretch(1)

        scroll.setWidget(content)
        return scroll

    def _build_kpi_row(self, model: ServiceScreenViewModel) -> QWidget:
        row = QWidget()
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(_px(self, 3))
        k = model.kpi
        assert k is not None
        tokens = current_color_tokens()
        stats = [
            ("Состояние", k.machine_state, tokens.info),
            (
                "Блокировки",
                str(k.blockers_count),
                tokens.error if k.blockers_count else tokens.success,
            ),
            (
                "Транзакции",
                str(k.unresolved_count),
                tokens.error if k.unresolved_count else tokens.success,
            ),
            (
                "Устройства",
                f"{k.devices_ok}/{k.devices_total}",
                tokens.success if k.devices_ok == k.devices_total else tokens.warning,
            ),
        ]
        for cap, val, color in stats:
            card = QWidget()
            card.setStyleSheet(f"background: {tokens.card}; border: none; border-radius: 14px;")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(_px(self, 4), _px(self, 3), _px(self, 4), _px(self, 3))
            v = QLabel(val)
            v.setStyleSheet(f"font-size: 34px; font-weight: 800; color: {color};")
            c = QLabel(cap)
            c.setStyleSheet("font-size: 14px; color: #64748B;")
            cl.addWidget(v)
            cl.addWidget(c)
            rl.addWidget(card, 1)
        return row

    def _style_for_action(self, variant: str) -> tuple[str, str]:
        # Функция возвращает кортеж (базовый_стиль, стиль_при_нажатии)
        tokens = current_color_tokens()
        primary_hover = "#7E22CE" if tokens.chart_1 == "#8B5CF6" else tokens.chart_1
        danger_hover = "#B91C1C" if tokens.error == "#DC2626" else tokens.error
        warning_bg = "#FEF3C7" if tokens is not DARK_TOKENS else "rgba(202, 138, 4, 0.2)"
        warning_fg = "#92400E" if tokens is not DARK_TOKENS else tokens.warning
        warning_hover = "#FDE68A" if tokens is not DARK_TOKENS else "rgba(202, 138, 4, 0.3)"
        default_bg = "#F1F5F9" if tokens is not DARK_TOKENS else "#2A2422"
        default_fg = "#334155" if tokens is not DARK_TOKENS else tokens.foreground
        default_hover = "#E2E8F0" if tokens is not DARK_TOKENS else tokens.secondary

        styles = {
            "primary": (
                f"background: {tokens.chart_1}; color: #FFFFFF;",
                f"background: {primary_hover};",
            ),
            "danger": (
                f"background: {tokens.error}; color: #FFFFFF;",
                f"background: {danger_hover};",
            ),
            "warning": (
                f"background: {warning_bg}; color: {warning_fg};",
                f"background: {warning_hover};",
            ),
            "default": (
                f"background: {default_bg}; color: {default_fg};",
                f"background: {default_hover};",
            ),
        }
        return styles.get(variant, styles["default"])

    def _make_action_button(self, action: ActionButtonViewModel) -> QPushButton:
        btn = QPushButton(action.label)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setEnabled(action.enabled)
        btn.setFixedHeight(_px(self, 11))  # Увеличили высоту кнопок для удобного тапа

        normal_css, pressed_css = self._style_for_action(getattr(action, "variant", "default"))

        btn.setStyleSheet(
            f"""
            QPushButton {{
                border-radius: 12px;
                font-size: 16px;
                font-weight: 600;
                padding: 0 16px;
                border: none;
                {normal_css}
            }}
            QPushButton:pressed {{
                {pressed_css}
            }}
            QPushButton:disabled {{ opacity: 0.40; }}
            """
        )
        aid = action.action_id
        if aid in {"exit_service", "clear_restricted_state", "clear_pending_transactions"}:
            btn.clicked.connect(lambda _checked=False, a=aid: self._confirm_action(a))
        else:
            btn.clicked.connect(lambda _checked=False, a=aid: self.action_requested.emit(a))
        return btn

    def _build_action_group(self, group: ServiceActionGroupViewModel) -> QWidget:
        body = QWidget()
        # Переключились на QGridLayout, чтобы размещать кнопки в 2 колонки
        bl = QGridLayout(body)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(_px(self, 2))

        columns = 2
        for idx, action in enumerate(group.actions):
            if action is None:
                continue
            btn = self._make_action_button(action)
            row = idx // columns
            col = idx % columns
            bl.addWidget(btn, row, col)

        return _wrap_card(self, group.label, body)

    def _build_product_toggles(self, title: str, toggles) -> QWidget:
        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(_px(self, 1.5))
        tokens = current_color_tokens()
        row_bg = "#F8FAFC" if tokens is not DARK_TOKENS else "#2A2422"
        for act in toggles:
            row = QWidget()
            row.setStyleSheet(f"background: {row_bg}; border: none; border-radius: 12px;")
            rl = QHBoxLayout(row)
            # Увеличенные отступы внутри строк переключателей
            rl.setContentsMargins(_px(self, 4), _px(self, 3), _px(self, 4), _px(self, 3))

            lbl = QLabel(act.label)
            lbl.setStyleSheet(f"font-size: 16px; font-weight: 500; color: {tokens.foreground};")

            sw = ToggleSwitch(act.enabled)
            aid = act.action_id
            sw.toggled.connect(lambda _state, a=aid: self.action_requested.emit(a))

            rl.addWidget(lbl, 1)
            rl.addWidget(sw, 0, Qt.AlignmentFlag.AlignVCenter)
            bl.addWidget(row)
        return _wrap_card(self, title, body)

    def _confirm_action(self, action_id: str) -> None:
        labels = {
            "exit_service": ("Выйти из сервисного режима?", "Вы уверены, что хотите выйти?"),
            "clear_restricted_state": (
                "Сбросить все блокировки?",
                "Будут сброшены все активные ограничения.",
            ),
            "clear_pending_transactions": (
                "Сбросить незавершённые транзакции?",
                "Все незавершённые транзакции будут отменены.",
            ),
        }
        title, msg = labels.get(action_id, ("Подтвердите действие", "Вы уверены?"))
        reply = QMessageBox.question(
            self,
            title,
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.action_requested.emit(action_id)

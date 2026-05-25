"""Qt stylesheet and presentation constants for the kiosk UI. Modern premium theme system."""

from __future__ import annotations

from typing import Literal, cast

from PySide6.QtWidgets import QApplication

from flower_vending.ui.design_tokens import (
    BrandColors,
    ColorTokens,
    DARK_TOKENS,
    LIGHT_TOKENS,
    Radius,
    Typography,
)


def _build_stylesheet(tokens: ColorTokens) -> str:
    primary_gradient = f"qlineargradient(x1:0 y1:0, x2:1 y2:0, stop:0 {BrandColors.PINK_500}, stop:1 {BrandColors.PURPLE_600});"
    primary_brighter = f"qlineargradient(x1:0 y1:0, x2:1 y2:0, stop:0 {BrandColors.PINK_500}, stop:0.5 #C026D3, stop:1 {BrandColors.PURPLE_600});"
    primary_darker = "qlineargradient(x1:0 y1:0, x2:1 y2:0, stop:0 #BE185D, stop:1 #6B21A8);"

    return f"""
QWidget {{
    background: {tokens.background};
    color: {tokens.foreground};
    font-family: {Typography.FONT_FAMILY};
    font-size: {Typography.BASE_SIZE}px;
    font-weight: {Typography.WEIGHTS["normal"]};
}}

QMainWindow {{
    background: {tokens.background};
}}

QScrollArea {{
    background: transparent;
    border: none;
}}

QScrollArea > QWidget > QWidget {{
    background: transparent;
}}

QLabel {{
    background: transparent;
}}

QFrame {{
    border: none;
}}

QAbstractButton:focus,
QPushButton:focus,
QCheckBox:focus,
QLineEdit:focus {{
    outline: none;
}}

QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 8px 0 8px 0;
}}

QScrollBar::handle:vertical {{
    background: {tokens.muted};
    border-radius: {Radius.SM}px;
    min-height: 48px;
}}

QScrollBar::handle:vertical:hover {{
    background: {tokens.muted_foreground};
}}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {{
    background: transparent;
    border: none;
    height: 0;
}}

QScrollBar:horizontal {{
    background: transparent;
    height: 8px;
    margin: 0 8px 0 8px;
}}

QScrollBar::handle:horizontal {{
    background: {tokens.muted};
    border-radius: {Radius.SM}px;
    min-width: 48px;
}}

QScrollBar::handle:horizontal:hover {{
    background: {tokens.muted_foreground};
}}

QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal,
QScrollBar::sub-page:horizontal {{
    background: transparent;
    border: none;
    width: 0;
}}

/* ---- Modern Gradient Button ---- */
QPushButton#PrimaryButton {{
    min-height: 56px;
    padding: 12px 28px;
    border: none;
    border-radius: {Radius.XL}px;
    background: {primary_gradient}
    color: #FFFFFF;
    font-size: 18px;
    font-weight: {Typography.WEIGHTS["bold"]};
}}

QPushButton#PrimaryButton:hover {{
    background: {primary_brighter}
}}

QPushButton#PrimaryButton:pressed {{
    background: {primary_darker}
}}

QPushButton#PrimaryButton:disabled {{
    background: {tokens.muted};
    color: {tokens.muted_foreground};
}}

QPushButton#PrimaryButton[compact="true"] {{
    min-height: 44px;
    padding: 8px 18px;
    font-size: 15px;
}}

/* ---- Secondary Outline Button ---- */
QPushButton#SecondaryButton {{
    min-height: 56px;
    padding: 12px 28px;
    border: 2px solid #EC4899;
    border-radius: {Radius.XL}px;
    background: transparent;
    color: #EC4899;
    font-size: 18px;
    font-weight: {Typography.WEIGHTS["semibold"]};
}}

QPushButton#SecondaryButton:hover {{
    background: rgba(236, 72, 153, 0.08);
}}

QPushButton#SecondaryButton:pressed {{
    background: rgba(236, 72, 153, 0.15);
}}

QPushButton#SecondaryButton[compact="true"] {{
    min-height: 44px;
    padding: 8px 18px;
    font-size: 15px;
}}

/* ---- Ghost/Tertiary Button ---- */
QPushButton#GhostButton {{
    min-height: 44px;
    padding: 8px 16px;
    border: none;
    border-radius: {Radius.MD}px;
    background: transparent;
    color: {tokens.muted_foreground};
    font-size: 15px;
    font-weight: {Typography.WEIGHTS["medium"]};
}}

QPushButton#GhostButton:hover {{
    background: {tokens.accent};
    color: {tokens.accent_foreground};
}}

/* ---- Chip / Pill Button ---- */
QPushButton#ChipButton {{
    min-height: 40px;
    max-height: 44px;
    padding: 6px 16px;
    border: none;
    border-radius: {Radius.FULL}px;
    background: transparent;
    color: {tokens.muted_foreground};
    font-size: 14px;
    font-weight: {Typography.WEIGHTS["medium"]};
}}

QPushButton#ChipButton:hover {{
    background: {tokens.accent};
}}

QPushButton#ChipButton:checked {{
    background: #9333EA;
    color: #FFFFFF;
}}

QPushButton#ChipButton[pressed="true"] {{
    background: #9333EA;
    color: #FFFFFF;
}}

/* ---- Icon Button ---- */
QPushButton#IconButton {{
    min-width: 44px;
    min-height: 44px;
    max-width: 44px;
    max-height: 44px;
    border-radius: {Radius.MD}px;
    border: none;
    background: transparent;
    padding: 0;
}}

QPushButton#IconButton:hover {{
    background: {tokens.accent};
}}

/* ---- Money / Denomination Button ---- */
QPushButton#MoneyButton {{
    min-height: 52px;
    padding: 10px 20px;
    border: 2px solid {BrandColors.PURPLE_50};
    border-radius: {Radius.XL}px;
    background: #FFFFFF;
    color: #9333EA;
    font-size: 17px;
    font-weight: {Typography.WEIGHTS["bold"]};
}}

QPushButton#MoneyButton:hover {{
    background: {BrandColors.PURPLE_50};
    border-color: #9333EA;
}}

/* ---- Destructive/Danger Button ---- */
QPushButton#DangerButton {{
    min-height: 48px;
    padding: 10px 20px;
    border: none;
    border-radius: {Radius.MD}px;
    background: {tokens.destructive};
    color: {tokens.destructive_foreground};
    font-size: 16px;
    font-weight: {Typography.WEIGHTS["semibold"]};
}}

QPushButton#DangerButton:hover {{
    background: #B31234;
}}

/* ==========================
   CARDS & CONTAINERS
   ========================== */

QFrame#Card {{
    background: {tokens.card};
    border-radius: {Radius.XL}px;
}}

QFrame#KPICard {{
    background: #FFFFFF;
    border-radius: {Radius.XL}px;
    padding: 0;
}}

QFrame#ProductCard {{
    background: #FFFFFF;
    border-radius: {Radius.XL2}px;
    padding: 0;
}}

QFrame#ProductCard:hover {{
    background: #FDF2F8;
}}

QFrame#Banner {{
    border: none;
    border-radius: {Radius.LG}px;
    padding: 14px 18px;
}}

QFrame#Banner[tone="info"] {{
    background: #F3F4F6;
}}

QFrame#Banner[tone="success"] {{
    background: {BrandColors.GREEN_100};
}}

QFrame#Banner[tone="warning"] {{
    background: {BrandColors.YELLOW_100};
}}

QFrame#Banner[tone="error"] {{
    background: {BrandColors.RED_100};
}}

QLabel#BannerTitle {{
    font-size: 16px;
    font-weight: {Typography.WEIGHTS["bold"]};
}}

QLabel#BannerMessage {{
    font-size: 14px;
    color: {tokens.muted_foreground};
}}

/* ==========================
   PRODUCT ELEMENTS
   ========================== */

QLabel#ProductPhoto {{
    background: {tokens.accent};
    border: none;
    border-radius: {Radius.XL}px;
    color: {tokens.muted_foreground};
    font-size: 16px;
    font-weight: {Typography.WEIGHTS["bold"]};
}}

QLabel#ProductTitle {{
    font-size: 18px;
    font-weight: {Typography.WEIGHTS["bold"]};
    color: {tokens.foreground};
}}

QLabel#ProductDescription {{
    font-size: 14px;
    color: {tokens.muted_foreground};
}}

QLabel#ProductPrice {{
    font-size: 24px;
    font-weight: {Typography.WEIGHTS["bold"]};
    color: #EC4899;
}}

QLabel#ProductCategory {{
    font-size: 13px;
    color: {tokens.muted_foreground};
    font-weight: {Typography.WEIGHTS["medium"]};
}}

QLabel#Badge {{
    padding: 2px 10px;
    border-radius: {Radius.FULL}px;
    font-size: 12px;
    font-weight: {Typography.WEIGHTS["semibold"]};
}}

QLabel#Badge[status="success"] {{
    background: {BrandColors.GREEN_100};
    color: {BrandColors.GREEN_600};
}}

QLabel#Badge[status="warning"] {{
    background: {BrandColors.YELLOW_100};
    color: {BrandColors.YELLOW_600};
}}

QLabel#Badge[status="error"] {{
    background: {BrandColors.RED_100};
    color: {BrandColors.RED_600};
}}

QLabel#Badge[status="info"] {{
    background: #EEF2FF;
    color: #4338CA;
}}

/* ==========================
   PANEL ELEMENTS
   ========================== */

QFrame#DetailsPanel {{
    background: #FFFFFF;
    border-radius: {Radius.XL}px;
}}

QLabel#PanelCaption {{
    color: {tokens.muted_foreground};
    font-size: 13px;
    font-weight: {Typography.WEIGHTS["semibold"]};
    text-transform: uppercase;
}}

/* ==========================
   PAYMENT METRICS
   ========================== */

QFrame#MetricCard {{
    background: {BrandColors.PURPLE_50};
    border: none;
    border-radius: {Radius.XL}px;
}}

QLabel#MetricCaption {{
    color: {tokens.muted_foreground};
    font-size: 14px;
    font-weight: {Typography.WEIGHTS["medium"]};
}}

QLabel#MetricValue {{
    color: #9333EA;
    font-size: 32px;
    font-weight: {Typography.WEIGHTS["bold"]};
}}

QLabel#MetricValue[accent="true"] {{
    color: #EC4899;
}}

/* ==========================
   HERO / HEADINGS
   ========================== */

QLabel#HeroTitle {{
    font-size: 36px;
    font-weight: {Typography.WEIGHTS["black"]};
    color: {tokens.foreground};
}}

QLabel#HeroSubtitle {{
    font-size: 18px;
    color: {tokens.muted_foreground};
}}

QLabel#Title {{
    font-size: 28px;
    font-weight: {Typography.WEIGHTS["bold"]};
}}

QLabel#Subtitle {{
    font-size: 18px;
    color: {tokens.muted_foreground};
}}

QLabel#SectionTitle {{
    font-size: 15px;
    font-weight: {Typography.WEIGHTS["semibold"]};
    color: {tokens.muted_foreground};
    text-transform: uppercase;
}}

QLabel#StatusMessage {{
    font-size: 28px;
    font-weight: {Typography.WEIGHTS["bold"]};
    color: {tokens.foreground};
}}

QLabel#HumanMessage {{
    font-size: 16px;
    color: {tokens.muted_foreground};
    line-height: 1.5;
}}

/* ==========================
   PROCESSING / DELIVERY
   ========================== */

QProgressBar {{
    background: {tokens.muted};
    border: none;
    border-radius: 5px;
    height: 8px;
    text-align: center;
    font-size: 0;
}}

QProgressBar::chunk {{
    background: #9333EA;
    border-radius: 5px;
}}

QLabel#ProcessingLabel {{
    font-size: 20px;
    font-weight: {Typography.WEIGHTS["semibold"]};
    color: {tokens.foreground};
}}

/* ==========================
   THANK YOU SCREEN
   ========================== */

QWidget#ThankYouScreen {{
    background: qlineargradient(x1:0 y1:0, x2:1 y2:1,
        stop:0 #FDF2F8, stop:0.5 #FAF5FF, stop:1 #EFF6FF);
}}

QLabel#ThankYouTitle {{
    color: {tokens.foreground};
    font-size: 40px;
    font-weight: {Typography.WEIGHTS["black"]};
}}

QLabel#ThankYouSubtitle {{
    color: {tokens.muted_foreground};
    font-size: 20px;
}}

/* ==========================
   SERVICE / ADMIN
   ========================== */

QWidget#ServiceScreen {{
    background: {BrandColors.GRAY_50};
    color: {tokens.foreground};
}}

QGroupBox {{
    background: #FFFFFF;
    border: none;
    border-radius: {Radius.XL}px;
    margin-top: 18px;
    padding: 16px 12px 12px 12px;
    font-size: 15px;
    font-weight: {Typography.WEIGHTS["semibold"]};
    color: {tokens.foreground};
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 6px;
    background: {BrandColors.GRAY_50};
}}

QCheckBox {{
    color: {tokens.foreground};
    font-size: 15px;
    font-weight: {Typography.WEIGHTS["medium"]};
    spacing: 10px;
}}

QCheckBox::indicator {{
    width: 22px;
    height: 22px;
}}

/* ==========================
   ADMIN PANEL
   ========================== */

QWidget#AdminSidebar {{
    background: #1E1B4B;
}}

QWidget#AdminContent {{
    background: {BrandColors.GRAY_50};
}}

/* ==========================
   INPUTS & FORMS
   ========================== */

QLineEdit[class="adminInput"] {{
    min-height: 42px;
    padding: 8px 12px;
    border: 1px solid {tokens.input_border};
    border-radius: {Radius.XL}px;
    background: {tokens.input_bg};
    color: {tokens.foreground};
    font-size: 14px;
    selection-background-color: {BrandColors.PURPLE_600};
}}

QLineEdit[class="adminInput"]:focus {{
    border-color: {BrandColors.PURPLE_600};
}}

/* ==========================
   TRANSITIONS / STATES
   ========================== */

QFrame[selected="true"] {{
    background: #F3E8FF;
}}

QFrame[available="false"] {{
    opacity: 0.5;
}}

QWidget[danger="true"] {{
    color: {tokens.destructive};
}}
"""


ThemeName = Literal["light", "dark", "auto"]

_LIGHT_SHEET: str | None = None
_DARK_SHEET: str | None = None


def light_stylesheet() -> str:
    global _LIGHT_SHEET
    if _LIGHT_SHEET is None:
        _LIGHT_SHEET = _build_stylesheet(LIGHT_TOKENS)
    return _LIGHT_SHEET


def dark_stylesheet() -> str:
    global _DARK_SHEET
    if _DARK_SHEET is None:
        _DARK_SHEET = _build_stylesheet(DARK_TOKENS)
    return _DARK_SHEET


def is_dark_theme_time() -> bool:
    from datetime import datetime

    hour = datetime.now().hour
    return hour >= 20 or hour < 6


def _app_theme() -> ThemeName:
    app = cast(QApplication | None, QApplication.instance())
    if app is None:
        return "auto"
    value = app.property("flower_vending_theme")
    if value in ("light", "dark", "auto"):
        return cast(ThemeName, value)
    return "auto"


def set_theme(name: ThemeName) -> None:
    app = cast(QApplication | None, QApplication.instance())
    if app is not None:
        app.setProperty("flower_vending_theme", name)
        app.setStyleSheet(current_stylesheet())


def current_stylesheet() -> str:
    theme = _app_theme()
    if theme == "dark":
        return dark_stylesheet()
    if theme == "light":
        return light_stylesheet()
    if is_dark_theme_time():
        return dark_stylesheet()
    return light_stylesheet()

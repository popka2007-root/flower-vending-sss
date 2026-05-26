"""Qt stylesheet and presentation constants for the kiosk UI. Modern premium theme system."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, cast

from PySide6.QtWidgets import QApplication

from flower_vending.ui.design_tokens import (
    DARK_TOKENS,
    LIGHT_TOKENS,
    BrandColors,
    ColorTokens,
    Radius,
    Typography,
)


def _build_stylesheet(tokens: ColorTokens) -> str:
    qss_path = Path(__file__).parent / "assets" / "main.qss"
    try:
        with open(qss_path, encoding="utf-8") as f:
            template = f.read()
    except Exception:
        # Fallback if asset is missing in development
        return ""

    context = {
        "background": tokens.background,
        "foreground": tokens.foreground,
        "font_family": Typography.FONT_FAMILY,
        "base_size": Typography.BASE_SIZE,
        "weight_normal": Typography.WEIGHTS["normal"],
        "weight_medium": Typography.WEIGHTS["medium"],
        "weight_semibold": Typography.WEIGHTS["semibold"],
        "weight_bold": Typography.WEIGHTS["bold"],
        "weight_black": Typography.WEIGHTS["black"],
        "weight_light": Typography.WEIGHTS["light"],
        "radius_sm": Radius.SM,
        "radius_md": Radius.MD,
        "radius_lg": Radius.LG,
        "radius_xl": Radius.XL,
        "radius_full": Radius.FULL,
        "primary": tokens.primary,
        "primary_hover": "#F08A1A" if tokens.primary == "#EF7D00" else tokens.primary,
        "muted": tokens.muted,
        "muted_foreground": tokens.muted_foreground,
        "accent": tokens.accent,
        "accent_foreground": tokens.accent_foreground,
        "secondary": tokens.secondary,
        "destructive": tokens.destructive,
        "destructive_foreground": tokens.destructive_foreground,
        "destructive_hover": "#B31234" if tokens.destructive == "#D4183D" else tokens.destructive,
        "card": tokens.card,
        "input_bg": tokens.input_bg,
        "input_border": tokens.input_border,
        "chart_1": tokens.chart_1,
        "chart_2": tokens.chart_2,
        "chart_3": tokens.chart_3,
        "chart_2_alpha_08": "rgba(236, 72, 153, 0.08)"
        if tokens.chart_2 == "#EC4899"
        else "rgba(239, 125, 0, 0.08)",
        "chart_2_alpha_15": "rgba(236, 72, 153, 0.15)"
        if tokens.chart_2 == "#EC4899"
        else "rgba(239, 125, 0, 0.15)",
        "product_card_hover": "#FDF2F8" if tokens is not DARK_TOKENS else "#3A322F",
        "gray_50": BrandColors.GRAY_50,
        "gray_100": BrandColors.GRAY_100,
        "success": tokens.success,
        "success_bg": BrandColors.GREEN_100
        if tokens is not DARK_TOKENS
        else "rgba(22, 163, 74, 0.2)",
        "warning": tokens.warning,
        "warning_bg": BrandColors.YELLOW_100
        if tokens is not DARK_TOKENS
        else "rgba(202, 138, 4, 0.2)",
        "error": tokens.error,
        "error_bg": BrandColors.RED_100 if tokens is not DARK_TOKENS else "rgba(220, 38, 38, 0.2)",
        "info_bg": "#EEF2FF" if tokens is not DARK_TOKENS else "rgba(37, 99, 235, 0.2)",
        "info_fg": "#4338CA" if tokens is not DARK_TOKENS else "#93C5FD",
        "thank_you_stop_0": "#FDF2F8" if tokens is not DARK_TOKENS else "#2A2422",
        "thank_you_stop_1": "#FAF5FF" if tokens is not DARK_TOKENS else "#2A2422",
        "thank_you_stop_2": "#EFF6FF" if tokens is not DARK_TOKENS else "#2A2422",
        "selected_bg": "#F3E8FF" if tokens is not DARK_TOKENS else "#453833",
    }

    return template.format(**context)


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
        # Force re-rendering of sheets
        global _LIGHT_SHEET, _DARK_SHEET
        _LIGHT_SHEET = None
        _DARK_SHEET = None
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

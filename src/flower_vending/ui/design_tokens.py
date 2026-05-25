"""Design tokens matching the Figma shadcn/ui design system."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from PySide6.QtGui import QColor


@dataclass(frozen=True, slots=True)
class ColorTokens:
    background: str = "#FAF6EE"
    foreground: str = "#332A26"
    card: str = "#FFFFFF"
    card_foreground: str = "#332A26"
    popover: str = "#FFFFFF"
    popover_foreground: str = "#332A26"
    primary: str = "#EF7D00"
    primary_foreground: str = "#FFFFFF"
    secondary: str = "#F2EADB"
    secondary_foreground: str = "#332A26"
    muted: str = "#ECECF0"
    muted_foreground: str = "#8C7B73"
    accent: str = "#EF7D00"
    accent_foreground: str = "#FFFFFF"
    destructive: str = "#D4183D"
    destructive_foreground: str = "#FFFFFF"
    border: str = "rgba(0,0,0,0.05)"
    input_border: str = "#D1D5DB"
    input_bg: str = "#FFFFFF"
    ring: str = "#EF7D00"


LIGHT_TOKENS = ColorTokens()


@dataclass(frozen=True, slots=True)
class DarkColorTokens(ColorTokens):
    background: str = "#2A2422"
    foreground: str = "#FAF6EE"
    card: str = "#332A26"
    card_foreground: str = "#FAF6EE"
    popover: str = "#332A26"
    popover_foreground: str = "#FAF6EE"
    primary: str = "#EF7D00"
    primary_foreground: str = "#FFFFFF"
    secondary: str = "#453833"
    secondary_foreground: str = "#FAF6EE"
    muted: str = "#453833"
    muted_foreground: str = "#B0A8A4"
    accent: str = "#EF7D00"
    accent_foreground: str = "#FFFFFF"
    destructive: str = "#7D1C32"
    destructive_foreground: str = "#FFFFFF"
    border: str = "rgba(255,255,255,0.05)"
    input_bg: str = "#2A2422"
    input_border: str = "#4A4A4A"
    ring: str = "#EF7D00"


DARK_TOKENS = DarkColorTokens()


class BrandColors:
    ORANGE_PRIMARY: ClassVar[str] = "#EF7D00"
    ORANGE_SHADOW: ClassVar[str] = "rgba(239, 125, 0, 0.3)"
    CREAM_BACKGROUND: ClassVar[str] = "#FAF6EE"
    CREAM_CARD: ClassVar[str] = "#FFFFFF"
    TEXT_MAIN: ClassVar[str] = "#332A26"
    TEXT_MUTED: ClassVar[str] = "#8C7B73"
    TEXT_LIGHT: ClassVar[str] = "#6D635E"

    PINK_500: ClassVar[str] = "#EF7D00"  # Aliased to prevent breaks
    PURPLE_600: ClassVar[str] = "#EF7D00"  # Aliased
    PURPLE_50: ClassVar[str] = "#F2EADB"  # Aliased
    GREEN_600: ClassVar[str] = "#16A34A"
    GREEN_100: ClassVar[str] = "#DCFCE7"
    YELLOW_600: ClassVar[str] = "#CA8A04"
    YELLOW_100: ClassVar[str] = "#FEF9C3"
    RED_600: ClassVar[str] = "#DC2626"
    RED_100: ClassVar[str] = "#FEE2E2"
    GRAY_50: ClassVar[str] = "#FAF6EE"
    GRAY_100: ClassVar[str] = "#F3F4F6"
    GRAY_200: ClassVar[str] = "#E5E7EB"
    GRAY_300: ClassVar[str] = "#D1D5DB"
    GRAY_500: ClassVar[str] = "#6D635E"
    PINK_50: ClassVar[str] = "#F2EADB"
    BLUE_50: ClassVar[str] = "#EFF6FF"
    CYAN_500: ClassVar[str] = "#06B6D4"

    KPI_GREEN: ClassVar[str] = "#059669"
    KPI_YELLOW: ClassVar[str] = "#D97706"
    KPI_BLUE: ClassVar[str] = "#2563EB"
    KPI_RED: ClassVar[str] = "#DC2626"


class Typography:
    BASE_SIZE: ClassVar[int] = 16
    SCALE: ClassVar[dict[str, int]] = {
        "xs": 12,
        "sm": 14,
        "base": 16,
        "lg": 18,
        "xl": 20,
        "2xl": 24,
        "3xl": 30,
        "4xl": 36,
        "5xl": 40,
    }
    WEIGHTS: ClassVar[dict[str, int]] = {
        "light": 300,
        "normal": 400,
        "medium": 500,
        "semibold": 600,
        "bold": 700,
        "extrabold": 800,
        "black": 900,
    }
    LINE_HEIGHT: ClassVar[float] = 1.5
    FONT_FAMILY: ClassVar[str] = (
        '"Segoe UI", "Arial", "DejaVu Sans", "Noto Sans", system-ui, sans-serif'
    )


class Spacing:
    UNIT: ClassVar[int] = 4
    SCALE: ClassVar[dict[str, int]] = {
        "px": 1,
        "0.5": 2,
        "1": 4,
        "1.5": 6,
        "2": 8,
        "2.5": 10,
        "3": 12,
        "4": 16,
        "5": 20,
        "6": 24,
        "8": 32,
        "12": 48,
        "16": 64,
    }


class Radius:
    SM: ClassVar[int] = 6
    MD: ClassVar[int] = 8
    LG: ClassVar[int] = 10
    XL: ClassVar[int] = 14
    XL2: ClassVar[int] = 16
    FULL: ClassVar[int] = 9999


class Shadows:
    SM: ClassVar[str] = "0 1px 2px rgba(0,0,0,0.05)"
    MD: ClassVar[str] = "0 4px 6px -1px rgba(0,0,0,0.1)"
    LG: ClassVar[str] = "0 10px 15px -3px rgba(0,0,0,0.1)"
    XL: ClassVar[str] = "0 20px 25px -5px rgba(0,0,0,0.1)"


class IconSizes:
    XS: ClassVar[int] = 12
    SM: ClassVar[int] = 16
    MD: ClassVar[int] = 20
    LG: ClassVar[int] = 24
    XL: ClassVar[int] = 32
    XL2: ClassVar[int] = 48


def current_color_tokens(dark: bool = False) -> ColorTokens:
    return DARK_TOKENS if dark else LIGHT_TOKENS


def qcolor(hex_color: str) -> QColor:
    return QColor(hex_color)

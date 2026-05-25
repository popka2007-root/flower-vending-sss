"""Design tokens matching the Figma shadcn/ui design system."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from PySide6.QtGui import QColor


@dataclass(frozen=True, slots=True)
class ColorTokens:
    background: str = "#FFFFFF"
    foreground: str = "#0A0A0A"
    card: str = "#FFFFFF"
    card_foreground: str = "#0A0A0A"
    popover: str = "#FFFFFF"
    popover_foreground: str = "#0A0A0A"
    primary: str = "#030213"
    primary_foreground: str = "#FFFFFF"
    secondary: str = "#F0F0F5"
    secondary_foreground: str = "#030213"
    muted: str = "#ECECF0"
    muted_foreground: str = "#717182"
    accent: str = "#E9EBEF"
    accent_foreground: str = "#030213"
    destructive: str = "#D4183D"
    destructive_foreground: str = "#FFFFFF"
    border: str = "rgba(0,0,0,0.10)"
    input_border: str = "#D1D5DB"
    input_bg: str = "#F3F3F5"
    ring: str = "#B0B0B0"


LIGHT_TOKENS = ColorTokens()


@dataclass(frozen=True, slots=True)
class DarkColorTokens(ColorTokens):
    background: str = "#1C1C1C"
    foreground: str = "#FAFAFA"
    card: str = "#1E1E1E"
    card_foreground: str = "#FAFAFA"
    popover: str = "#1E1E1E"
    popover_foreground: str = "#FAFAFA"
    primary: str = "#FAFAFA"
    primary_foreground: str = "#0A0A0A"
    secondary: str = "#3A3A3A"
    secondary_foreground: str = "#FAFAFA"
    muted: str = "#3A3A3A"
    muted_foreground: str = "#B0B0B0"
    accent: str = "#3A3A3A"
    accent_foreground: str = "#FAFAFA"
    destructive: str = "#7D1C32"
    destructive_foreground: str = "#FFFFFF"
    border: str = "rgba(255,255,255,0.10)"
    input_bg: str = "#2A2A2A"
    input_border: str = "#4A4A4A"
    ring: str = "#6A6A6A"


DARK_TOKENS = DarkColorTokens()


class BrandColors:
    PINK_500: ClassVar[str] = "#EC4899"
    PURPLE_600: ClassVar[str] = "#9333EA"
    PURPLE_50: ClassVar[str] = "#FAF5FF"
    GREEN_600: ClassVar[str] = "#16A34A"
    GREEN_100: ClassVar[str] = "#DCFCE7"
    YELLOW_600: ClassVar[str] = "#CA8A04"
    YELLOW_100: ClassVar[str] = "#FEF9C3"
    RED_600: ClassVar[str] = "#DC2626"
    RED_100: ClassVar[str] = "#FEE2E2"
    GRAY_50: ClassVar[str] = "#F9FAFB"
    GRAY_100: ClassVar[str] = "#F3F4F6"
    GRAY_200: ClassVar[str] = "#E5E7EB"
    GRAY_300: ClassVar[str] = "#D1D5DB"
    GRAY_500: ClassVar[str] = "#6B7280"
    PINK_50: ClassVar[str] = "#FDF2F8"
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

"""Platform abstraction descriptors for kiosk/runtime deployment."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from flower_vending.infrastructure.config.models import PlatformConfig


class PlatformIntegrationStatus(StrEnum):
    IMPLEMENTED = "implemented"
    EXTENSION_POINT = "extension_point"


@dataclass(frozen=True, slots=True)
class PlatformExtensionPoint:
    name: str
    mode: str
    status: PlatformIntegrationStatus
    description: str
    config: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PlatformProfile:
    target_os: str
    common_components: tuple[str, ...]
    extension_points: tuple[PlatformExtensionPoint, ...]


def common_components() -> tuple[str, ...]:
    return (
        "domain and application core",
        "simulator devices and deterministic fault injection",
        "Qt presenter/view-model UI layer",
        "SQLite persistence and transaction journal",
        "structured logging and bootstrap validation",
    )


def build_generic_profile(config: PlatformConfig) -> PlatformProfile:
    return PlatformProfile(
        target_os=config.target_os,
        common_components=common_components(),
        extension_points=(
            PlatformExtensionPoint(
                name="kiosk_mode",
                mode="generic",
                status=PlatformIntegrationStatus.EXTENSION_POINT,
                description="Fullscreen shell integration remains platform-specific.",
                config={"enabled": config.kiosk_mode},
            ),
            PlatformExtensionPoint(
                name="autostart",
                mode=config.autostart_mode,
                status=PlatformIntegrationStatus.EXTENSION_POINT,
                description="Autostart wiring is intentionally left as an OS-specific extension point.",
                config={},
            ),
            PlatformExtensionPoint(
                name="kiosk_lock",
                mode="generic",
                status=PlatformIntegrationStatus.EXTENSION_POINT,
                description="Kiosk lock/unlock is a software-only stub until OS integration is confirmed.",
                config={"adapter": "SimulatorKioskLock"},
            ),
            PlatformExtensionPoint(
                name="watchdog",
                mode=config.watchdog.adapter,
                status=PlatformIntegrationStatus.EXTENSION_POINT,
                description="Watchdog integration requires OS or hardware confirmation.",
                config=config.watchdog.settings,
            ),
        ),
    )

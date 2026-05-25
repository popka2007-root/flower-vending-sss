"""Windows-specific platform abstraction descriptors."""

from __future__ import annotations

from flower_vending.infrastructure.config.models import PlatformConfig
from flower_vending.platform.common import (
    PlatformExtensionPoint,
    PlatformIntegrationStatus,
    PlatformProfile,
    common_components,
)


def build_profile(config: PlatformConfig) -> PlatformProfile:
    return PlatformProfile(
        target_os="windows",
        common_components=common_components(),
        extension_points=(
            PlatformExtensionPoint(
                name="kiosk_mode",
                mode="windows_shell",
                status=PlatformIntegrationStatus.EXTENSION_POINT,
                description="Windows kiosk shell or assigned-access setup must be confirmed on the target image.",
                config={"enabled": config.kiosk_mode},
            ),
            PlatformExtensionPoint(
                name="autostart",
                mode=config.autostart_mode,
                status=PlatformIntegrationStatus.EXTENSION_POINT,
                description="Windows autostart and service registration stay outside the simulator-safe baseline.",
                config={},
            ),
            PlatformExtensionPoint(
                name="service_manager",
                mode="windows_service",
                status=PlatformIntegrationStatus.EXTENSION_POINT,
                description="Windows Service wrapper is represented as a deployment extension point only.",
                config={},
            ),
            PlatformExtensionPoint(
                name="kiosk_lock",
                mode="windows_service",
                status=PlatformIntegrationStatus.EXTENSION_POINT,
                description="Windows kiosk lock can be backed by a local service or scheduled task.",
                config={"adapter": "SimulatorKioskLock"},
            ),
            PlatformExtensionPoint(
                name="watchdog",
                mode=config.watchdog.adapter,
                status=PlatformIntegrationStatus.EXTENSION_POINT,
                description="Watchdog heartbeat can be mapped to a Windows host service after bench confirmation.",
                config=config.watchdog.settings,
            ),
        ),
    )

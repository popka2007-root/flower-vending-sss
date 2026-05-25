"""Linux-specific platform abstraction descriptors."""

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
        target_os="linux",
        common_components=common_components(),
        extension_points=(
            PlatformExtensionPoint(
                name="kiosk_mode",
                mode="linux_shell",
                status=PlatformIntegrationStatus.EXTENSION_POINT,
                description="Window-manager lockdown and kiosk shell setup remain deployment-specific.",
                config={"enabled": config.kiosk_mode},
            ),
            PlatformExtensionPoint(
                name="autostart",
                mode=config.autostart_mode,
                status=PlatformIntegrationStatus.EXTENSION_POINT,
                description="Linux autostart is expected to be provided by systemd or the desktop session.",
                config={},
            ),
            PlatformExtensionPoint(
                name="service_manager",
                mode="systemd",
                status=PlatformIntegrationStatus.EXTENSION_POINT,
                description="systemd unit wiring is modeled, but not installed by the simulator-safe baseline.",
                config={},
            ),
            PlatformExtensionPoint(
                name="kiosk_lock",
                mode="logind",
                status=PlatformIntegrationStatus.EXTENSION_POINT,
                description="Linux kiosk lock can use logind Inhibit or a custom session manager.",
                config={"adapter": "SimulatorKioskLock"},
            ),
            PlatformExtensionPoint(
                name="watchdog",
                mode=config.watchdog.adapter,
                status=PlatformIntegrationStatus.EXTENSION_POINT,
                description="systemd or external watchdog integration requires target-host confirmation.",
                config=config.watchdog.settings,
            ),
        ),
    )

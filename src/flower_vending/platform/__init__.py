"""Platform abstraction entrypoints."""

from __future__ import annotations

from flower_vending.infrastructure.config.models import PlatformConfig
from flower_vending.platform.common import PlatformProfile, build_generic_profile
from flower_vending.platform.kiosk_lock import KioskLock, SimulatorKioskLock  # noqa: F401
from flower_vending.platform.linux import build_profile as build_linux_profile
from flower_vending.platform.windows import build_profile as build_windows_profile


def build_platform_profile(config: PlatformConfig) -> PlatformProfile:
    if config.target_os == "windows":
        return build_windows_profile(config)
    if config.target_os == "linux":
        return build_linux_profile(config)
    return build_generic_profile(config)

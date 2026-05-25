"""YAML-backed application configuration models and loaders."""

from flower_vending.infrastructure.config.models import (
    AppConfig,
    BillValidatorConfig,
    GenericDeviceConfig,
    LoggingConfig,
    MachineConfig,
    PersistenceConfig,
    PlatformConfig,
)


def load_machine_config(path: str) -> AppConfig:
    from flower_vending.infrastructure.config.loader import (
        load_machine_config as _load_machine_config,
    )

    return _load_machine_config(path)


def build_device_settings_snapshot(config: AppConfig) -> dict[str, dict[str, object]]:
    from flower_vending.infrastructure.config.loader import (
        build_device_settings_snapshot as _build_device_settings_snapshot,
    )

    return _build_device_settings_snapshot(config)


__all__ = [
    "AppConfig",
    "BillValidatorConfig",
    "GenericDeviceConfig",
    "LoggingConfig",
    "MachineConfig",
    "PersistenceConfig",
    "PlatformConfig",
    "build_device_settings_snapshot",
    "load_machine_config",
]

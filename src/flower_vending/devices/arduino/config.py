"""Configuration models for Arduino/ESP32 device adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ArduinoMapping:
    relay_door: int = 1
    relay_drum: int = 4
    sensor_button: str = "BUTTON"
    sensor_drum: str = "DRUM"


@dataclass(frozen=True, slots=True)
class ArduinoDeviceConfig:
    port: str = ""
    baudrate: int = 115200
    read_timeout_s: float = 0.5
    write_timeout_s: float = 0.5
    mapping: ArduinoMapping = field(default_factory=ArduinoMapping)
    pulse_ms_door: int = 700
    pulse_ms_drum: int = 700
    settings: dict[str, Any] = field(default_factory=dict)


DEFAULT_ARDUINO_CONFIG = ArduinoDeviceConfig()

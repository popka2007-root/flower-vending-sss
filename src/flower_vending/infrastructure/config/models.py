"""Pydantic models for machine runtime configuration."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from flower_vending.devices.contracts import DeviceCommandPolicy, DeviceFaultCode
from flower_vending.devices.dbv300sd.config import (
    DBV300ProtocolKind,
    DBV300TransportKind,
    SerialTransportSettings,
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class MachinePoliciesConfig(StrictModel):
    critical_temperature_celsius: float = 8.0
    pickup_timeout_s: float = 60.0
    idle_timeout_s: float = 120.0


class PaymentTerminalConfigModel(StrictModel):
    enabled: bool = False
    driver: str = "mock"
    device_name: str = "payment_terminal"
    port: str = ""
    baudrate: int = 9600
    timeout_s: float = 30.0
    settings: dict[str, Any] = Field(default_factory=dict)


class ServiceModeConfig(StrictModel):
    pin: str
    lock_purchase_button: bool = False
    visible_button: bool = False


class PaymentMethodsConfig(StrictModel):
    cash: bool = True
    card: bool = False
    qr: bool = False
    sbp: bool = False


class MachineConfig(StrictModel):
    machine_id: str = "flower-vending-001"
    currency: str = "RUB"
    startup_state: str = "SELF_TEST"
    policies: MachinePoliciesConfig = Field(default_factory=MachinePoliciesConfig)
    service_mode: ServiceModeConfig
    payment_methods: PaymentMethodsConfig = Field(default_factory=PaymentMethodsConfig)

    @field_validator("machine_id", "currency", "startup_state")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized


class PersistenceConfig(StrictModel):
    sqlite_path: str = "var/data/flower_vending.db"
    busy_timeout_ms: int = 5_000
    enable_wal: bool = True
    synchronous: Literal["FULL", "NORMAL", "OFF"] = "FULL"

    @field_validator("sqlite_path")
    @classmethod
    def _path_not_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("sqlite_path must not be blank")
        return normalized


class LogRotationConfig(StrictModel):
    max_bytes: int = 10 * 1024 * 1024
    backup_count: int = 7


class LoggingConfig(StrictModel):
    level: str = "INFO"
    directory: str = "var/log"
    filename: str = "flower_vending.jsonl"
    json_logs: bool = Field(default=True, alias="json")
    stderr: bool = True
    async_log: bool = True
    rotation: LogRotationConfig = Field(default_factory=LogRotationConfig)
    sensitive_fields: tuple[str, ...] = (
        "bill_minor_units",
        "price_minor_units",
        "accepted_minor_units",
        "change_due_minor_units",
        "refund_minor_units",
        "reserved_minor_units",
        "remaining_minor_units",
    )


class DeviceCommandPolicyConfig(StrictModel):
    timeout_s: float | None = 1.0
    retry_count: int = 0
    retryable_faults: tuple[str, ...] = (
        DeviceFaultCode.COMMAND_TIMEOUT.value,
        DeviceFaultCode.TRANSIENT_COMMAND_FAILURE.value,
        DeviceFaultCode.COMMUNICATION_ERROR.value,
    )
    non_retryable_faults: tuple[str, ...] = (
        DeviceFaultCode.AMBIGUOUS_PHYSICAL_RESULT.value,
        DeviceFaultCode.PHYSICAL_STATE_MISMATCH.value,
        DeviceFaultCode.RECONCILIATION_REQUIRED.value,
        DeviceFaultCode.UNSUPPORTED_OPERATION.value,
        DeviceFaultCode.CONFIGURATION_ERROR.value,
    )
    require_manual_review_on_ambiguous_result: bool = True

    @field_validator("timeout_s")
    @classmethod
    def _timeout_positive(cls, value: float | None) -> float | None:
        if value is not None and value <= 0:
            raise ValueError("timeout_s must be positive when provided")
        return value

    @field_validator("retry_count")
    @classmethod
    def _retry_count_non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("retry_count must be non-negative")
        return value

    @field_validator("retryable_faults", "non_retryable_faults")
    @classmethod
    def _fault_codes_not_blank(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values)
        if any(not value for value in normalized):
            raise ValueError("fault codes must not be blank")
        return normalized

    def to_runtime_policy(self) -> DeviceCommandPolicy:
        return DeviceCommandPolicy(
            timeout_s=self.timeout_s,
            retry_count=self.retry_count,
            retryable_faults=self.retryable_faults,
            non_retryable_faults=self.non_retryable_faults,
            require_manual_review_on_ambiguous_result=(
                self.require_manual_review_on_ambiguous_result
            ),
        )


class WatchdogRuntimeConfig(StrictModel):
    enabled: bool = True
    adapter: str = "requires_hardware_confirmation"
    policy: DeviceCommandPolicyConfig = Field(default_factory=DeviceCommandPolicyConfig)
    settings: dict[str, Any] = Field(default_factory=dict)


class PlatformConfig(StrictModel):
    target_os: Literal["windows", "linux", "generic"] = "generic"
    kiosk_mode: bool = True
    autostart_mode: str = "none"
    watchdog: WatchdogRuntimeConfig = Field(default_factory=WatchdogRuntimeConfig)


class RuntimeConfig(StrictModel):
    health_poll_interval_s: float = 0.5
    validator_event_timeout_s: float = 0.05
    watchdog_timeout_s: float = 30.0
    event_log_limit: int = 100
    persist_applied_config: bool = True
    seed_demo_data: bool = True


class UiConfig(StrictModel):
    window_title: str = "ЭКСПРЕСС БУКЕТ"
    kiosk_fullscreen: bool = True

    @field_validator("window_title")
    @classmethod
    def _ui_values_not_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized


class CatalogSeedItemConfig(StrictModel):
    product_id: str
    slot_id: str
    name: str
    display_name: str
    category: str = "flowers"
    price_minor_units: int
    quantity: int = 1
    capacity: int = 6
    is_bouquet: bool = False
    enabled: bool = True
    temperature_profile: str = "cooled"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "product_id", "slot_id", "name", "display_name", "category", "temperature_profile"
    )
    @classmethod
    def _seed_fields_not_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized


def _default_catalog_items() -> tuple[CatalogSeedItemConfig, ...]:
    return (
        CatalogSeedItemConfig(
            product_id="roses_ecuador_7",
            slot_id="A1",
            name="roses_ecuador_7",
            display_name="Розы Эквадор 7 шт.",
            category="roses",
            price_minor_units=249_000,
            quantity=4,
            capacity=8,
            metadata={
                "short_description": "Классические крупные розы в лаконичной упаковке.",
                "image_path": "products/roses-ecuador-7.jpg",
                "freshness_note": "Собран сегодня",
                "size_label": "7 стеблей",
            },
        ),
        CatalogSeedItemConfig(
            product_id="white_tulips_9",
            slot_id="A2",
            name="white_tulips_9",
            display_name="Тюльпаны белые 9 шт.",
            category="tulips",
            price_minor_units=199_000,
            quantity=3,
            capacity=8,
            metadata={
                "short_description": "Светлый весенний букет для дома или комплимента.",
                "image_path": "products/white-tulips-9.jpg",
                "freshness_note": "Поставка утро",
                "size_label": "9 стеблей",
            },
        ),
        CatalogSeedItemConfig(
            product_id="gentle_mix",
            slot_id="B1",
            name="gentle_mix",
            display_name="Нежный микс",
            category="bouquets",
            price_minor_units=299_000,
            quantity=3,
            capacity=6,
            is_bouquet=True,
            metadata={
                "short_description": "Розы и сезонные цветы в мягкой пастельной гамме.",
                "image_path": "products/gentle-mix.jpg",
                "freshness_note": "Собран сегодня",
                "size_label": "Средний букет",
            },
        ),
    )


class CatalogConfig(StrictModel):
    items: tuple[CatalogSeedItemConfig, ...] = Field(default_factory=_default_catalog_items)


class SimulatorFaultConfig(StrictModel):
    target_device: Literal[
        "validator",
        "change_dispenser",
        "motor",
        "window",
        "watchdog",
    ]
    code: str
    remaining_hits: int = 1
    message: str | None = None
    critical: bool = True
    details: dict[str, Any] = Field(default_factory=dict)

    @field_validator("code")
    @classmethod
    def _code_not_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("code must not be blank")
        return normalized


class SimulatorConfig(StrictModel):
    enabled: bool = True
    startup_scenario: str | None = None
    scenario_suite: tuple[str, ...] = ()
    accepted_bill_denominations_minor: tuple[int, ...] = (100, 500, 1000)
    quick_insert_bill_denominations_minor: tuple[int, ...] = (100, 500, 1000)
    change_inventory: dict[int, int] = Field(default_factory=lambda: {100: 10, 50: 10})
    initial_temperature_celsius: float = 4.0
    initial_service_door_open: bool = False
    initial_inventory_presence: bool = True
    initial_inventory_confidence: float = 1.0
    initial_faults: tuple[SimulatorFaultConfig, ...] = ()

    @field_validator("startup_scenario")
    @classmethod
    def _normalize_optional_scenario(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class BillValidatorSerialConfig(StrictModel):
    port: str
    baudrate: int = 9600
    bytesize: int = 8
    parity: str = "N"
    stopbits: int = 1
    read_timeout_s: float = 0.2
    write_timeout_s: float = 0.2

    def to_runtime_settings(self) -> SerialTransportSettings:
        return SerialTransportSettings(
            port=self.port,
            baudrate=self.baudrate,
            bytesize=self.bytesize,
            parity=self.parity,
            stopbits=self.stopbits,
            read_timeout_s=self.read_timeout_s,
            write_timeout_s=self.write_timeout_s,
        )


class BillValidatorConfig(StrictModel):
    enabled: bool = True
    driver: Literal["dbv300sd"] = "dbv300sd"
    device_name: str = "jcm_dbv300sd"
    requires_hardware_confirmation: bool = True
    transport_kind: DBV300TransportKind = DBV300TransportKind.SERIAL
    protocol_kind: DBV300ProtocolKind = DBV300ProtocolKind.SERIAL
    poll_interval_s: float = 0.2
    startup_disable_acceptance: bool = True
    fallback_disable_on_fault: bool = True
    accepted_denominations_minor: tuple[int, ...] = ()
    policy: DeviceCommandPolicyConfig = Field(default_factory=DeviceCommandPolicyConfig)
    serial: BillValidatorSerialConfig | None = None

    @model_validator(mode="after")
    def _validate_serial(self) -> "BillValidatorConfig":
        if self.transport_kind is DBV300TransportKind.SERIAL and self.serial is None:
            raise ValueError("serial settings are required for serial transport")
        return self


class GenericDeviceConfig(StrictModel):
    enabled: bool = True
    driver: str
    device_name: str
    mapping: str | None = None
    timeouts_ms: dict[str, int] = Field(default_factory=dict)
    policy: DeviceCommandPolicyConfig = Field(default_factory=DeviceCommandPolicyConfig)
    settings: dict[str, Any] = Field(default_factory=dict)
    requires_hardware_confirmation: bool = True


class DevicesConfig(StrictModel):
    bill_validator: BillValidatorConfig
    change_dispenser: GenericDeviceConfig
    motor_controller: GenericDeviceConfig
    cooling_controller: GenericDeviceConfig
    window_controller: GenericDeviceConfig
    temperature_sensor: GenericDeviceConfig
    door_sensor: GenericDeviceConfig
    inventory_sensor: GenericDeviceConfig
    position_sensor: GenericDeviceConfig
    payment_terminal: PaymentTerminalConfigModel = Field(default_factory=PaymentTerminalConfigModel)


class AppConfig(StrictModel):
    machine: MachineConfig = Field(default_factory=MachineConfig)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    ui: UiConfig = Field(default_factory=UiConfig)
    catalog: CatalogConfig = Field(default_factory=CatalogConfig)
    simulator: SimulatorConfig = Field(default_factory=SimulatorConfig)
    persistence: PersistenceConfig = Field(default_factory=PersistenceConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    platform: PlatformConfig = Field(default_factory=PlatformConfig)
    devices: DevicesConfig

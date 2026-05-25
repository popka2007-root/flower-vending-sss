"""Bootstrap helpers for simulator-safe runtime entrypoints."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal, cast

from flower_vending.app import ApplicationCore, build_application_core
from flower_vending.app.fsm import MachineState, StateTransitionRecord
from flower_vending.app.services import InventoryService
from flower_vending.domain.entities import MoneyInventory, Product, Slot, Transaction
from flower_vending.domain.events import DomainEvent
from flower_vending.domain.exceptions import ManualInterventionRequiredError
from flower_vending.domain.value_objects import Amount, Currency, ProductId, SlotId
from flower_vending.app.logging import ApplicationLogger
from flower_vending.infrastructure.config.loader import (
    build_device_settings_snapshot,
    load_machine_config,
)
from flower_vending.infrastructure.config.models import (
    AppConfig,
    CatalogSeedItemConfig,
    SimulatorFaultConfig,
)
from flower_vending.infrastructure.logging.setup import (
    StructuredLoggerAdapter,
    close_logging,
    configure_logging,
    set_log_context,
)
from flower_vending.infrastructure.persistence.journal import SQLiteTransactionJournal
from flower_vending.infrastructure.persistence.sqlite import (
    AppliedConfigRepository,
    DeviceFaultLogRepository,
    DeviceSettingsRepository,
    MachineStatusRepository,
    MoneyInventoryRepository,
    OperationalEventRepository,
    ProductRepository,
    SQLiteDatabase,
    SlotRepository,
    TransactionRepository,
    ensure_sqlite_schema,
)
from flower_vending.platform import build_platform_profile
from flower_vending.platform.common import PlatformProfile
from flower_vending.runtime.paths import bundle_root, discover_source_root, state_root
from flower_vending.simulators.control import RecentEventStore, SimulatorControlService
from flower_vending.simulators.devices import (
    MockBillValidator,
    MockChangeDispenser,
    MockCoolingController,
    MockDoorSensor,
    MockInventorySensor,
    MockMotorController,
    MockPositionSensor,
    MockTemperatureSensor,
    MockWatchdogAdapter,
    MockWindowController,
)
from flower_vending.simulators.faults import SimulatorFaultCode
from flower_vending.simulators.scenarios.catalog import SCENARIO_REGISTRY
from flower_vending.ui.facade import UiApplicationFacade
from flower_vending.devices.arduino import (
    ArduinoDoorSensor,
    ArduinoMotorController,
    ArduinoPositionSensor,
    ArduinoSerialTransport,
    ArduinoTemperatureSensor,
    ArduinoWindowController,
)
from flower_vending.devices.dbv300sd.adapter import build_dbv300sd_validator
from flower_vending.devices.dbv300sd.config import (
    DBV300ProtocolKind,
    DBV300SDValidatorConfig,
    DBV300TransportKind,
    SerialTransportSettings,
)
from flower_vending.devices.interfaces import (
    BillValidator,
    ChangeDispenser,
    DoorSensor,
    ManagedDevice,
    MotorController,
    PositionSensor,
    TemperatureSensor,
    WatchdogAdapter,
    WindowController,
)


Severity = Literal["info", "warning", "error"]

PERSISTENCE_EVENT_TYPES: tuple[str, ...] = (
    "transaction_completed",
    "transaction_cancelled",
    "payment_confirmed",
    "machine_faulted",
    "critical_temperature_detected",
    "service_door_opened",
    "service_mode_entered",
    "service_mode_exited",
    "refund_dispensed",
    "refund_failed",
    "change_dispensed",
    "product_dispensed",
    "pickup_timeout_elapsed",
    "recovery_started",
    "delivery_window_opened",
    "pickup_confirmed",
)


@dataclass(frozen=True, slots=True)
class BootstrapMessage:
    severity: Severity
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class BootstrapReport:
    config_path: Path
    project_root: Path
    state_root: Path
    created_directories: tuple[Path, ...]
    messages: tuple[BootstrapMessage, ...]
    platform_profile: PlatformProfile

    @property
    def valid(self) -> bool:
        return not any(message.severity == "error" for message in self.messages)

    @property
    def hardware_warnings(self) -> tuple[str, ...]:
        return tuple(
            message.message
            for message in self.messages
            if message.code == "hardware_confirmation_required"
        )


@dataclass(slots=True)
class RuntimeRepositories:
    database: SQLiteDatabase
    products: ProductRepository
    slots: SlotRepository
    machine_status: MachineStatusRepository
    money_inventory: MoneyInventoryRepository
    transactions: TransactionRepository
    journal: SQLiteTransactionJournal
    device_faults: DeviceFaultLogRepository
    device_settings: DeviceSettingsRepository
    applied_config: AppliedConfigRepository
    operational_events: OperationalEventRepository


@dataclass(slots=True)
class SimulatorDevices:
    validator: MockBillValidator
    change_dispenser: MockChangeDispenser
    motor_controller: MockMotorController
    cooling_controller: MockCoolingController
    window_controller: MockWindowController
    temperature_sensor: MockTemperatureSensor
    door_sensor: MockDoorSensor
    inventory_sensor: MockInventorySensor
    position_sensor: MockPositionSensor
    watchdog: MockWatchdogAdapter

    def managed(self) -> dict[str, Any]:
        return {
            "validator": self.validator,
            "change_dispenser": self.change_dispenser,
            "motor": self.motor_controller,
            "cooling": self.cooling_controller,
            "window": self.window_controller,
            "temperature": self.temperature_sensor,
            "door": self.door_sensor,
            "inventory": self.inventory_sensor,
            "watchdog": self.watchdog,
        }

    def startup_order(self) -> tuple[Any, ...]:
        return (
            self.validator,
            self.change_dispenser,
            self.motor_controller,
            self.cooling_controller,
            self.window_controller,
            self.temperature_sensor,
            self.door_sensor,
            self.inventory_sensor,
            self.position_sensor,
            self.watchdog,
        )


@dataclass(slots=True)
class SimulatorRuntimeEnvironment:
    config: AppConfig
    config_path: Path
    project_root: Path
    report: BootstrapReport
    logger: ApplicationLogger
    repositories: RuntimeRepositories
    devices: SimulatorDevices
    inventory_service: InventoryService
    money_inventory: MoneyInventory
    core: ApplicationCore
    ui_facade: UiApplicationFacade
    simulator_controls: SimulatorControlService
    event_store: RecentEventStore
    platform_profile: PlatformProfile
    yaml_text: str
    _started: bool = False

    async def start(self) -> None:
        if self._started:
            return
        self.logger.info(
            "runtime_starting",
            extra={
                "config_path": str(self.config_path),
                "machine_id": self.config.machine.machine_id,
            },
        )
        for device in self.devices.startup_order():
            await device.start()
        await self._restore_runtime_state()
        await self.core.start_runtime()
        await self._complete_startup_flow()
        self._persist_runtime_snapshot()
        self._started = True
        self.logger.info(
            "runtime_started", extra={"machine_state": self.core.fsm.current_state.value}
        )

    async def stop(self) -> None:
        if not self._started:
            self.repositories.database.close()
            close_logging(cast(StructuredLoggerAdapter, self.logger))
            return
        self.logger.info(
            "runtime_stopping", extra={"machine_state": self.core.fsm.current_state.value}
        )
        await self.core.stop_runtime()
        for device in reversed(self.devices.startup_order()):
            await device.stop()
        self._persist_runtime_snapshot()
        self.repositories.database.close()
        close_logging(cast(StructuredLoggerAdapter, self.logger))
        self._started = False

    def diagnostics_report(self) -> dict[str, Any]:
        diagnostics = self.ui_facade.diagnostics_snapshot()
        return {
            "machine": asdict(diagnostics.machine),
            "devices": [asdict(device) for device in diagnostics.devices],
            "unresolved_transaction_ids": list(diagnostics.unresolved_transaction_ids),
            "recent_events": [asdict(entry) for entry in diagnostics.recent_events],
            "platform": {
                "target_os": self.platform_profile.target_os,
                "common_components": list(self.platform_profile.common_components),
                "extension_points": [
                    {
                        "name": item.name,
                        "mode": item.mode,
                        "status": item.status.value,
                        "description": item.description,
                        "config": item.config,
                    }
                    for item in self.platform_profile.extension_points
                ],
            },
            "hardware_warnings": list(self.report.hardware_warnings),
        }

    async def service_report(self, *, operator_id: str) -> dict[str, Any]:
        correlation_id = self.ui_facade.new_correlation_id()
        try:
            await self.ui_facade.enter_service_mode(
                operator_id=operator_id,
                correlation_id=correlation_id,
                pin=self.config.machine.service_mode.pin,
            )
        except ManualInterventionRequiredError:
            pass
        diagnostics = self.ui_facade.diagnostics_snapshot()
        return {
            "operator_id": operator_id,
            "machine_state": diagnostics.machine.machine_state,
            "sale_blockers": list(diagnostics.machine.sale_blockers),
            "unresolved_transaction_ids": list(diagnostics.unresolved_transaction_ids),
            "recent_events": [asdict(entry) for entry in diagnostics.recent_events],
        }

    async def _restore_runtime_state(self) -> None:
        unresolved_by_id = {
            transaction.transaction_id.value: transaction
            for transaction in self.repositories.transactions.list_unresolved()
        }
        for transaction_id in self.repositories.journal.unresolved_intent_transaction_ids():
            if transaction_id in unresolved_by_id:
                continue
            transaction = self.repositories.transactions.get(transaction_id)
            if transaction is not None:
                unresolved_by_id[transaction_id] = transaction
        unresolved = tuple(unresolved_by_id.values())
        self.core.transaction_coordinator.restore_transactions(unresolved)
        intent_plans = await self.core.recovery_manager.detect_unresolved_intents(
            "startup-recovery"
        )
        if unresolved:
            active_transaction = unresolved[0]
            self.core.machine_status_service.set_active_transaction(
                active_transaction.transaction_id.value
            )
            self.core.machine_status_service.block_sales("recovery_pending")
            self.core.fsm.force_state(
                MachineState.RECOVERY_PENDING, "restored_unresolved_transaction"
            )
            self.core.machine_status_service.set_machine_state(self.core.fsm.current_state)
            self.logger.warning(
                "runtime_restored_unresolved_transactions",
                extra={
                    "transaction_ids": [item.transaction_id.value for item in unresolved],
                    "active_transaction_id": active_transaction.transaction_id.value,
                },
            )
        if intent_plans:
            for transaction in self.core.transaction_coordinator.unresolved_transactions():
                self.repositories.transactions.save(transaction)
            self.repositories.machine_status.save(
                self.core.machine_status_service.runtime.status,
                machine_id=self.config.machine.machine_id,
            )
            self.logger.warning(
                "runtime_restored_unresolved_intents",
                extra={
                    "transaction_ids": [plan.transaction_id for plan in intent_plans],
                    "actions": [plan.action for plan in intent_plans],
                },
            )

    async def _complete_startup_flow(self) -> None:
        if self.core.fsm.current_state in {MachineState.BOOT, MachineState.SELF_TEST}:
            self.core.fsm.force_state(MachineState.IDLE, "startup_self_test_completed")
            self.core.machine_status_service.set_machine_state(self.core.fsm.current_state)
        await self.core.health_monitor.poll_once(correlation_id="startup-self-test")

    def _persist_runtime_snapshot(self) -> None:
        with self.repositories.database.transaction() as connection:
            self.repositories.machine_status.save(
                self.core.machine_status_service.runtime.status,
                machine_id=self.config.machine.machine_id,
                _connection=connection,
            )
            self.repositories.money_inventory.save(
                self.money_inventory,
                _connection=connection,
            )
            for transaction in _transactions_to_persist(self.core):
                self.repositories.transactions.save(
                    transaction,
                    _connection=connection,
                )


class RuntimePersistenceProjector:
    def __init__(
        self,
        *,
        repositories: RuntimeRepositories,
        config: AppConfig,
        core: ApplicationCore,
        money_inventory: MoneyInventory,
        logger: ApplicationLogger,
    ) -> None:
        self._repositories = repositories
        self._config = config
        self._core = core
        self._money_inventory = money_inventory
        self._logger = logger

    async def handle_domain_event(self, event: DomainEvent) -> None:
        transaction = (
            self._core.transaction_coordinator.get(event.transaction_id)
            if event.transaction_id is not None
            else self._core.transaction_coordinator.active()
        )
        with self._repositories.database.transaction() as connection:
            for persisted in _transactions_to_persist(self._core, primary=transaction):
                self._repositories.transactions.save(persisted, _connection=connection)
            self._repositories.machine_status.save(
                self._core.machine_status_service.runtime.status,
                machine_id=self._config.machine.machine_id,
                _connection=connection,
            )
            self._repositories.money_inventory.save(self._money_inventory, _connection=connection)
            self._repositories.journal.append_event(
                event,
                machine_state=self._core.fsm.current_state.value,
                transaction_status=(transaction.status.value if transaction is not None else None),
                _connection=connection,
            )
        if event.event_type in {"service_mode_entered", "service_mode_exited"}:
            self._repositories.operational_events.record_service_event(
                event_type=event.event_type,
                correlation_id=event.correlation_id,
                operator_id=str(event.payload.get("operator_id"))
                if event.payload.get("operator_id")
                else None,
                payload=dict(event.payload),
            )
        if event.event_type in {"critical_temperature_detected"}:
            self._repositories.operational_events.record_temperature_event(
                sensor_name="temperature_sensor",
                celsius=float(event.payload.get("celsius", 0.0)),
                event_type=event.event_type,
                correlation_id=event.correlation_id,
                details=dict(event.payload),
            )
        set_log_context(
            correlation_id=event.correlation_id,
            transaction_id=event.transaction_id,
        )
        self._logger.info(
            "domain_event",
            extra={
                "event_type": event.event_type,
                "payload": dict(event.payload),
                "machine_state": self._core.fsm.current_state.value,
            },
        )

    def handle_transition(self, record: StateTransitionRecord) -> None:
        active_transaction = self._core.transaction_coordinator.active()
        correlation_id = (
            active_transaction.correlation_id.value if active_transaction is not None else None
        )
        transaction_id = (
            active_transaction.transaction_id.value if active_transaction is not None else None
        )
        set_log_context(
            correlation_id=correlation_id,
            transaction_id=transaction_id,
        )
        self._logger.info(
            "fsm_transition",
            extra={
                "previous_state": record.previous_state.value,
                "new_state": record.new_state.value,
                "reason": record.reason,
            },
        )


def discover_project_root(start: Path | None = None) -> Path:
    return discover_source_root(start)


def validate_config_file(
    config_path: str | Path, *, prepare_directories: bool = False
) -> tuple[AppConfig, str, BootstrapReport]:
    path = Path(config_path).resolve()
    project_root = (
        bundle_root()
        if path.is_file() and path.is_relative_to(bundle_root())
        else discover_project_root(path)
    )
    runtime_state_root = (
        state_root() if path.is_file() and path.is_relative_to(bundle_root()) else project_root
    )
    yaml_text = path.read_text(encoding="utf-8")
    config = load_machine_config(path)
    messages: list[BootstrapMessage] = []
    created_directories: list[Path] = []

    try:
        MachineState(config.machine.startup_state)
    except ValueError:
        messages.append(
            BootstrapMessage(
                severity="error",
                code="invalid_startup_state",
                message=f"Unsupported startup state: {config.machine.startup_state}",
            )
        )

    for name in config.simulator.scenario_suite:
        if name not in SCENARIO_REGISTRY:
            messages.append(
                BootstrapMessage(
                    severity="error",
                    code="unknown_scenario",
                    message=f"Unknown simulator scenario '{name}'.",
                )
            )
    if (
        config.simulator.startup_scenario
        and config.simulator.startup_scenario not in SCENARIO_REGISTRY
    ):
        messages.append(
            BootstrapMessage(
                severity="error",
                code="unknown_startup_scenario",
                message=f"Unknown simulator startup scenario '{config.simulator.startup_scenario}'.",
            )
        )

    for directory in {
        resolve_runtime_path(runtime_state_root, config.persistence.sqlite_path).parent,
        resolve_runtime_path(runtime_state_root, config.logging.directory),
        runtime_state_root / "var" / "data",
        runtime_state_root / "var" / "log",
    }:
        if prepare_directories:
            directory.mkdir(parents=True, exist_ok=True)
            created_directories.append(directory)

    for device_name, device_config in build_device_settings_snapshot(config).items():
        if device_name == "watchdog":
            continue
        requires_confirmation = bool(device_config.get("requires_hardware_confirmation", False))
        if requires_confirmation:
            messages.append(
                BootstrapMessage(
                    severity="warning",
                    code="hardware_confirmation_required",
                    message=f"{device_name} is still an extension point that requires hardware confirmation.",
                )
            )
    if config.platform.watchdog.enabled and config.platform.watchdog.adapter != "simulator":
        messages.append(
            BootstrapMessage(
                severity="warning",
                code="hardware_confirmation_required",
                message="watchdog is still an extension point that requires hardware confirmation.",
            )
        )
    if not config.simulator.enabled:
        messages.append(
            BootstrapMessage(
                severity="warning",
                code="simulator_disabled",
                message="Simulator mode is disabled in this configuration.",
            )
        )

    if set(config.simulator.quick_insert_bill_denominations_minor) - set(
        config.simulator.accepted_bill_denominations_minor
    ):
        messages.append(
            BootstrapMessage(
                severity="warning",
                code="quick_insert_denominations",
                message="Some quick-insert denominations are not accepted by the simulator validator.",
            )
        )

    platform_profile = build_platform_profile(config.platform)
    return (
        config,
        yaml_text,
        BootstrapReport(
            config_path=path,
            project_root=project_root,
            state_root=runtime_state_root,
            created_directories=tuple(created_directories),
            messages=tuple(messages),
            platform_profile=platform_profile,
        ),
    )


def resolve_runtime_path(project_root: Path, raw_path: str) -> Path:
    candidate = Path(raw_path)
    if candidate.is_absolute():
        return candidate
    return project_root / candidate


def open_runtime_repositories(
    config_path: str | Path,
    *,
    prepare_directories: bool = False,
) -> tuple[AppConfig, BootstrapReport, RuntimeRepositories]:
    config, _, report = validate_config_file(
        config_path,
        prepare_directories=prepare_directories,
    )
    if not report.valid:
        errors = [message.message for message in report.messages if message.severity == "error"]
        raise ValueError("; ".join(errors))
    database = SQLiteDatabase(
        resolve_runtime_path(report.state_root, config.persistence.sqlite_path),
        busy_timeout_ms=config.persistence.busy_timeout_ms,
        enable_wal=config.persistence.enable_wal,
        synchronous=config.persistence.synchronous,
    )
    ensure_sqlite_schema(database)
    repositories = RuntimeRepositories(
        database=database,
        products=ProductRepository(database),
        slots=SlotRepository(database),
        machine_status=MachineStatusRepository(database),
        money_inventory=MoneyInventoryRepository(database),
        transactions=TransactionRepository(database),
        journal=SQLiteTransactionJournal(database),
        device_faults=DeviceFaultLogRepository(database),
        device_settings=DeviceSettingsRepository(database),
        applied_config=AppliedConfigRepository(database),
        operational_events=OperationalEventRepository(database),
    )
    return config, report, repositories


def read_runtime_status(config_path: str | Path) -> dict[str, Any]:
    config, report, repositories = open_runtime_repositories(
        config_path,
        prepare_directories=True,
    )
    try:
        unresolved_intents = repositories.journal.unresolved_intents()
        latest_applied_config = repositories.applied_config.latest()
        if latest_applied_config is not None:
            latest_applied_config.pop("yaml_text", None)
        return {
            "config_path": str(report.config_path),
            "database_path": str(repositories.database.path),
            "machine_id": config.machine.machine_id,
            "platform": {
                "target_os": report.platform_profile.target_os,
                "extension_points": [
                    {
                        "name": item.name,
                        "mode": item.mode,
                        "status": item.status.value,
                        "description": item.description,
                    }
                    for item in report.platform_profile.extension_points
                ],
            },
            "machine": repositories.machine_status.snapshot(machine_id=config.machine.machine_id),
            "money_inventory": repositories.money_inventory.snapshot(),
            "unresolved_transactions": list(repositories.transactions.list_unresolved_summaries()),
            "unresolved_intents": [
                {
                    "entry_name": intent.entry_name,
                    "correlation_id": intent.correlation_id,
                    "transaction_id": intent.transaction_id,
                    "machine_state": intent.machine_state,
                    "transaction_status": intent.transaction_status,
                    "payload": intent.payload,
                    "created_at": intent.created_at.isoformat(),
                }
                for intent in unresolved_intents
            ],
            "unacknowledged_faults": list(repositories.device_faults.list_unacknowledged()),
            "latest_applied_config": latest_applied_config,
            "hardware_warnings": list(report.hardware_warnings),
        }
    finally:
        repositories.database.close()


def read_runtime_events(config_path: str | Path, *, limit: int = 50) -> dict[str, Any]:
    config, report, repositories = open_runtime_repositories(
        config_path,
        prepare_directories=True,
    )
    try:
        events = [
            *repositories.journal.list_recent(limit=limit),
            *repositories.operational_events.list_recent(limit=limit),
        ]
        events.sort(key=lambda item: str(item["occurred_at"]), reverse=True)
        return {
            "config_path": str(report.config_path),
            "database_path": str(repositories.database.path),
            "machine_id": config.machine.machine_id,
            "limit": limit,
            "events": events[:limit],
        }
    finally:
        repositories.database.close()


def _transactions_to_persist(
    core: ApplicationCore,
    *,
    primary: Transaction | None = None,
) -> tuple[Transaction, ...]:
    transactions: dict[str, Transaction] = {}
    if primary is None:
        primary = core.transaction_coordinator.active()
    if primary is not None:
        transactions[primary.transaction_id.value] = primary
    for transaction in core.transaction_coordinator.unresolved_transactions():
        transactions[transaction.transaction_id.value] = transaction
    return tuple(transactions.values())


async def build_simulator_environment(
    *,
    config_path: str | Path,
    prepare_directories: bool = True,
) -> SimulatorRuntimeEnvironment:
    config, yaml_text, report = validate_config_file(
        config_path, prepare_directories=prepare_directories
    )
    if not report.valid:
        errors = [message.message for message in report.messages if message.severity == "error"]
        raise ValueError("; ".join(errors))
    if not config.simulator.enabled:
        raise ValueError("This entrypoint only supports simulator-enabled configurations.")

    project_root = report.project_root
    runtime_state_root = report.state_root
    database = SQLiteDatabase(
        resolve_runtime_path(runtime_state_root, config.persistence.sqlite_path),
        busy_timeout_ms=config.persistence.busy_timeout_ms,
        enable_wal=config.persistence.enable_wal,
        synchronous=config.persistence.synchronous,
    )
    ensure_sqlite_schema(database)
    repositories = RuntimeRepositories(
        database=database,
        products=ProductRepository(database),
        slots=SlotRepository(database),
        machine_status=MachineStatusRepository(database),
        money_inventory=MoneyInventoryRepository(database),
        transactions=TransactionRepository(database),
        journal=SQLiteTransactionJournal(database),
        device_faults=DeviceFaultLogRepository(database),
        device_settings=DeviceSettingsRepository(database),
        applied_config=AppliedConfigRepository(database),
        operational_events=OperationalEventRepository(database),
    )
    logger = configure_logging(
        config.logging.model_copy(
            update={
                "directory": str(resolve_runtime_path(runtime_state_root, config.logging.directory))
            }
        )
    )
    if config.runtime.persist_applied_config:
        repositories.applied_config.save_snapshot(
            source_path=str(report.config_path),
            yaml_text=yaml_text,
        )
    for device_name, device_config in build_device_settings_snapshot(config).items():
        repositories.device_settings.save(
            logical_device_name=device_name,
            driver_name=str(device_config.get("driver", device_config.get("adapter", "unknown"))),
            config=device_config,
        )

    _seed_catalog(
        repositories,
        config.catalog.items,
        currency_code=config.machine.currency,
        enabled=config.runtime.seed_demo_data,
    )
    inventory_service = _load_inventory_service(repositories)
    money_inventory = _load_money_inventory(repositories, config)
    devices = _build_simulator_devices(config, money_inventory)
    _apply_initial_faults(config.simulator.initial_faults, devices)

    core = build_application_core(
        validator=devices.validator,
        change_dispenser=devices.change_dispenser,
        motor_controller=devices.motor_controller,
        window_controller=devices.window_controller,
        inventory_service=inventory_service,
        money_inventory=money_inventory,
        devices=devices.managed(),
        accepted_bill_denominations=config.simulator.accepted_bill_denominations_minor,
        door_sensor=devices.door_sensor,
        temperature_sensor=devices.temperature_sensor,
        inventory_sensor=devices.inventory_sensor,
        initial_state=MachineState(config.machine.startup_state),
        critical_temperature_celsius=config.machine.policies.critical_temperature_celsius,
        health_poll_interval_s=config.runtime.health_poll_interval_s,
        validator_event_timeout_s=config.runtime.validator_event_timeout_s,
        watchdog_timeout_s=config.runtime.watchdog_timeout_s,
        pickup_timeout_s=config.machine.policies.pickup_timeout_s,
        journal=repositories.journal,
        service_pin=config.machine.service_mode.pin,
        idle_timeout_s=config.machine.policies.idle_timeout_s,
    )
    event_store = RecentEventStore(limit=config.runtime.event_log_limit)
    projector = RuntimePersistenceProjector(
        repositories=repositories,
        config=config,
        core=core,
        money_inventory=money_inventory,
        logger=logger,
    )
    core.event_bus.subscribe_best_effort("*", event_store.handle)
    for event_type in PERSISTENCE_EVENT_TYPES:
        core.event_bus.subscribe_critical(event_type, projector.handle_domain_event)
    core.fsm.subscribe(projector.handle_transition)

    simulator_controls = SimulatorControlService(
        core=core,
        validator=devices.validator,
        change_dispenser=devices.change_dispenser,
        motor_controller=devices.motor_controller,
        window_controller=devices.window_controller,
        temperature_sensor=devices.temperature_sensor,
        door_sensor=devices.door_sensor,
        inventory_sensor=devices.inventory_sensor,
        watchdog=devices.watchdog,
        quick_insert_denominations=config.simulator.quick_insert_bill_denominations_minor,
        default_slot_id=config.catalog.items[0].slot_id,
    )
    ui_facade = UiApplicationFacade(
        core,
        event_store=event_store,
        simulator_controls=simulator_controls,
        platform_profile=report.platform_profile,
        repositories=repositories,
        machine_id=config.machine.machine_id,
    )
    return SimulatorRuntimeEnvironment(
        config=config,
        config_path=report.config_path,
        project_root=project_root,
        report=report,
        logger=logger,
        repositories=repositories,
        devices=devices,
        inventory_service=inventory_service,
        money_inventory=money_inventory,
        core=core,
        ui_facade=ui_facade,
        simulator_controls=simulator_controls,
        event_store=event_store,
        platform_profile=report.platform_profile,
        yaml_text=yaml_text,
    )


def _seed_catalog(
    repositories: RuntimeRepositories,
    items: tuple[CatalogSeedItemConfig, ...],
    *,
    currency_code: str,
    enabled: bool,
) -> None:
    if not enabled:
        return
    existing_products = repositories.products.list_all()
    if existing_products and not _should_replace_demo_catalog(existing_products):
        return
    if existing_products:
        repositories.slots.delete_all()
        repositories.products.delete_all()
    for item in items:
        repositories.products.save(_seed_product(item, currency_code=currency_code))
        repositories.slots.save(_seed_slot(item))


def _should_replace_demo_catalog(existing_products: tuple[Product, ...]) -> bool:
    legacy_ids = {"rose_red", "tulip_white", "spring_bouquet"}
    existing_ids = {product.product_id.value for product in existing_products}
    if existing_ids == legacy_ids:
        return True
    if any(
        product.display_name in {"Red Roses", "White Tulips", "Spring Bouquet"}
        for product in existing_products
    ):
        return True
    return False


def _load_inventory_service(repositories: RuntimeRepositories) -> InventoryService:
    service = InventoryService()
    for product in repositories.products.list_all():
        service.register_product(product)
    for slot in repositories.slots.list_all():
        service.register_slot(slot)
    return service


def _load_money_inventory(repositories: RuntimeRepositories, config: AppConfig) -> MoneyInventory:
    stored = repositories.money_inventory.get()
    if stored is not None:
        return stored
    inventory = MoneyInventory(
        currency=Currency(config.machine.currency),
        accounting_counts_by_denomination=dict(config.simulator.change_inventory),
    )
    repositories.money_inventory.save(inventory)
    return inventory


def _seed_product(item: CatalogSeedItemConfig, *, currency_code: str) -> Product:
    return Product(
        product_id=ProductId(item.product_id),
        name=item.name,
        display_name=item.display_name,
        price=Amount(item.price_minor_units, Currency(currency_code)),
        category=item.category,
        is_bouquet=item.is_bouquet,
        enabled=item.enabled,
        temperature_profile=item.temperature_profile,
        metadata=dict(item.metadata),
    )


def _seed_slot(item: CatalogSeedItemConfig) -> Slot:
    return Slot(
        slot_id=SlotId(item.slot_id),
        product_id=ProductId(item.product_id),
        capacity=item.capacity,
        quantity=item.quantity,
        is_enabled=item.enabled,
    )


def _build_simulator_devices(
    config: AppConfig,
    money_inventory: MoneyInventory,
) -> SimulatorDevices:
    return SimulatorDevices(
        validator=MockBillValidator(
            name=config.devices.bill_validator.device_name,
            supported_bill_values=config.simulator.accepted_bill_denominations_minor,
            command_policy=config.devices.bill_validator.policy.to_runtime_policy(),
        ),
        change_dispenser=MockChangeDispenser(
            name=config.devices.change_dispenser.device_name,
            inventory=dict(money_inventory.accounting_counts_by_denomination),
            command_policy=config.devices.change_dispenser.policy.to_runtime_policy(),
        ),
        motor_controller=MockMotorController(
            name=config.devices.motor_controller.device_name,
            command_policy=config.devices.motor_controller.policy.to_runtime_policy(),
        ),
        cooling_controller=MockCoolingController(
            name=config.devices.cooling_controller.device_name,
            command_policy=config.devices.cooling_controller.policy.to_runtime_policy(),
        ),
        window_controller=MockWindowController(
            name=config.devices.window_controller.device_name,
            command_policy=config.devices.window_controller.policy.to_runtime_policy(),
        ),
        temperature_sensor=MockTemperatureSensor(
            name=config.devices.temperature_sensor.device_name,
            celsius=config.simulator.initial_temperature_celsius,
            command_policy=config.devices.temperature_sensor.policy.to_runtime_policy(),
        ),
        door_sensor=MockDoorSensor(
            name=config.devices.door_sensor.device_name,
            is_open=config.simulator.initial_service_door_open,
            command_policy=config.devices.door_sensor.policy.to_runtime_policy(),
        ),
        inventory_sensor=MockInventorySensor(
            name=config.devices.inventory_sensor.device_name,
            slot_states={
                item.slot_id: (
                    config.simulator.initial_inventory_presence,
                    config.simulator.initial_inventory_confidence,
                )
                for item in config.catalog.items
            },
            command_policy=config.devices.inventory_sensor.policy.to_runtime_policy(),
        ),
        position_sensor=MockPositionSensor(
            name=config.devices.position_sensor.device_name,
            command_policy=config.devices.position_sensor.policy.to_runtime_policy(),
        ),
        watchdog=MockWatchdogAdapter(
            name=config.platform.watchdog.adapter,
            command_policy=config.platform.watchdog.policy.to_runtime_policy(),
        ),
    )


@dataclass(slots=True)
class ProductionDevices:
    validator: BillValidator
    change_dispenser: ChangeDispenser
    motor_controller: MotorController
    window_controller: WindowController
    temperature_sensor: TemperatureSensor
    door_sensor: DoorSensor
    position_sensor: PositionSensor
    watchdog: WatchdogAdapter

    def managed(self) -> dict[str, ManagedDevice]:
        return {
            "validator": self.validator,
            "change_dispenser": self.change_dispenser,
            "motor": self.motor_controller,
            "window": self.window_controller,
            "temperature": self.temperature_sensor,
            "door": self.door_sensor,
            "position": self.position_sensor,
            "watchdog": self.watchdog,
        }

    def startup_order(self) -> tuple[ManagedDevice, ...]:
        return (
            self.validator,
            self.change_dispenser,
            self.motor_controller,
            self.window_controller,
            self.temperature_sensor,
            self.door_sensor,
            self.position_sensor,
            self.watchdog,
        )


def _resolve_port(raw_port: str) -> str:
    if raw_port and raw_port.upper() != "AUTO":
        return raw_port
    from flower_vending.runtime.discover import find_esp32_port, find_jcm_port

    jcm = find_jcm_port()
    if jcm:
        return jcm
    esp = find_esp32_port()
    if esp:
        return esp
    return ""


def _build_production_devices(config: AppConfig) -> ProductionDevices:
    serial = config.devices.bill_validator.serial
    bv_port = _resolve_port(serial.port) if serial is not None else ""
    bv_settings = (
        SerialTransportSettings(
            port=bv_port,
            baudrate=serial.baudrate if serial else 9600,
            bytesize=serial.bytesize if serial else 8,
            parity=serial.parity if serial else "N",
            stopbits=serial.stopbits if serial else 1,
            read_timeout_s=serial.read_timeout_s if serial else 0.2,
            write_timeout_s=serial.write_timeout_s if serial else 0.2,
        )
        if serial
        else None
    )

    bv_config = DBV300SDValidatorConfig(
        device_name=config.devices.bill_validator.device_name,
        transport_kind=DBV300TransportKind(config.devices.bill_validator.transport_kind),
        protocol_kind=DBV300ProtocolKind(config.devices.bill_validator.protocol_kind),
        serial_transport=bv_settings,
        poll_interval_s=config.devices.bill_validator.poll_interval_s,
        startup_disable_acceptance=config.devices.bill_validator.startup_disable_acceptance,
        fallback_disable_on_fault=config.devices.bill_validator.fallback_disable_on_fault,
        accepted_denominations_minor=tuple(
            config.devices.bill_validator.accepted_denominations_minor
        ),
        command_policy=config.devices.bill_validator.policy.to_runtime_policy(),
    )
    validator = build_dbv300sd_validator(bv_config)

    arduino_port = _resolve_port(config.devices.motor_controller.settings.get("port", "AUTO"))
    arduino = ArduinoSerialTransport(
        port=arduino_port,
        baudrate=config.devices.motor_controller.settings.get("baudrate", 115200),
    )

    return ProductionDevices(
        validator=validator,
        change_dispenser=MockChangeDispenser(
            name=config.devices.change_dispenser.device_name,
            inventory={},
            command_policy=config.devices.change_dispenser.policy.to_runtime_policy(),
        ),
        motor_controller=ArduinoMotorController(
            transport=arduino,
            name=config.devices.motor_controller.device_name,
            command_policy=config.devices.motor_controller.policy.to_runtime_policy(),
        ),
        window_controller=ArduinoWindowController(
            transport=arduino,
            name=config.devices.window_controller.device_name,
            pulse_ms=config.devices.window_controller.timeouts_ms.get("pulse", 700),
            command_policy=config.devices.window_controller.policy.to_runtime_policy(),
        ),
        temperature_sensor=ArduinoTemperatureSensor(
            transport=arduino,
            name=config.devices.temperature_sensor.device_name,
            command_policy=config.devices.temperature_sensor.policy.to_runtime_policy(),
        ),
        door_sensor=ArduinoDoorSensor(
            transport=arduino,
            name=config.devices.door_sensor.device_name,
            command_policy=config.devices.door_sensor.policy.to_runtime_policy(),
        ),
        position_sensor=ArduinoPositionSensor(
            transport=arduino,
            name=config.devices.position_sensor.device_name,
            command_policy=config.devices.position_sensor.policy.to_runtime_policy(),
        ),
        watchdog=MockWatchdogAdapter(
            name=config.platform.watchdog.adapter,
            command_policy=config.platform.watchdog.policy.to_runtime_policy(),
        ),
    )


def _apply_initial_faults(
    faults: tuple[SimulatorFaultConfig, ...], devices: SimulatorDevices
) -> None:
    target_map = {
        "validator": devices.validator,
        "change_dispenser": devices.change_dispenser,
        "motor": devices.motor_controller,
        "window": devices.window_controller,
        "watchdog": devices.watchdog,
    }
    for plan in faults:
        target = target_map[plan.target_device]
        target.inject_fault(
            SimulatorFaultCode(plan.code),
            remaining_hits=plan.remaining_hits,
            message=plan.message,
            critical=plan.critical,
            **plan.details,
        )

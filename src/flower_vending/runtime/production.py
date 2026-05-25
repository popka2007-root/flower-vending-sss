"""Production runtime environment builder for real hardware."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from flower_vending.app import ApplicationCore, build_application_core
from flower_vending.app.fsm import MachineState
from flower_vending.app.services import InventoryService
from flower_vending.domain.entities import MoneyInventory
from flower_vending.infrastructure.config.loader import build_device_settings_snapshot
from flower_vending.infrastructure.config.models import AppConfig
from flower_vending.app.logging import ApplicationLogger

from flower_vending.infrastructure.logging.setup import (
    StructuredLoggerAdapter,
    close_logging,
    configure_logging,
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
from flower_vending.platform.common import PlatformProfile
from flower_vending.runtime.bootstrap import (
    BootstrapReport,
    PERSISTENCE_EVENT_TYPES,
    ProductionDevices,
    RuntimePersistenceProjector,
    RuntimeRepositories,
    _build_production_devices,
    _load_inventory_service,
    _load_money_inventory,
    _seed_catalog,
    resolve_runtime_path,
    validate_config_file,
)
from flower_vending.simulators.control import RecentEventStore
from flower_vending.ui.facade import UiApplicationFacade


@dataclass(slots=True)
class ProductionRuntimeEnvironment:
    config: AppConfig
    config_path: Path
    report: BootstrapReport
    logger: ApplicationLogger
    repositories: RuntimeRepositories
    devices: ProductionDevices
    inventory_service: InventoryService
    money_inventory: MoneyInventory
    core: ApplicationCore
    ui_facade: UiApplicationFacade
    event_store: RecentEventStore
    platform_profile: PlatformProfile
    yaml_text: str
    _started: bool = False

    async def start(self) -> None:
        if self._started:
            return
        self.logger.info(
            "production_runtime_starting", extra={"machine_id": self.config.machine.machine_id}
        )

        startup_ok = True
        for device in self.devices.startup_order():
            try:
                await device.start()
                self.logger.info("device_started", extra={"device": device.name})
            except Exception as exc:
                self.logger.warning(
                    "device_start_failed",
                    extra={
                        "device": device.name,
                        "error": str(exc),
                    },
                )
                startup_ok = False

        if not startup_ok:
            self.logger.warning(
                "production_startup_degraded",
                extra={
                    "message": "Some devices failed to start. Continuing in degraded mode.",
                },
            )

        await self._restore_runtime_state()
        await self.core.start_runtime()
        await self._complete_startup_flow()
        self._persist_runtime_snapshot()
        self._started = True
        self.logger.info(
            "production_runtime_started", extra={"state": self.core.fsm.current_state.value}
        )

    async def stop(self) -> None:
        if not self._started:
            self.repositories.database.close()
            close_logging(cast(StructuredLoggerAdapter, self.logger))
            return
        self.logger.info("production_runtime_stopping")
        await self.core.stop_runtime()
        for device in reversed(self.devices.startup_order()):
            try:
                await device.stop()
            except Exception:
                pass
        self._persist_runtime_snapshot()
        self.repositories.database.close()
        close_logging(cast(StructuredLoggerAdapter, self.logger))
        self._started = False

    def diagnostics_report(self) -> dict[str, Any]:
        diagnostics = self.ui_facade.diagnostics_snapshot()
        return {
            "machine": {
                "machine_state": diagnostics.machine.machine_state,
                "sale_blockers": list(diagnostics.machine.sale_blockers),
                "service_mode": diagnostics.machine.service_mode,
            },
            "devices": [
                {"device_name": d.device_name, "state": d.state} for d in diagnostics.devices
            ],
            "recent_events": [
                {
                    "event_type": e.event_type,
                    "correlation_id": e.correlation_id,
                    "summary": str(e.summary)[:100],
                }
                for e in diagnostics.recent_events
            ],
        }

    async def _restore_runtime_state(self) -> None:
        unresolved = tuple(self.repositories.transactions.list_unresolved())
        self.core.transaction_coordinator.restore_transactions(unresolved)
        if unresolved:
            self.core.machine_status_service.set_active_transaction(
                unresolved[0].transaction_id.value
            )
            self.core.machine_status_service.block_sales("recovery_pending")
            self.core.fsm.force_state(MachineState.RECOVERY_PENDING, "restored")
            self.core.machine_status_service.set_machine_state(self.core.fsm.current_state)

    async def _complete_startup_flow(self) -> None:
        if self.core.fsm.current_state in {MachineState.BOOT, MachineState.SELF_TEST}:
            self.core.fsm.force_state(MachineState.IDLE, "startup_complete")
            self.core.machine_status_service.set_machine_state(self.core.fsm.current_state)
        await self.core.health_monitor.poll_once(correlation_id="startup")

    def _persist_runtime_snapshot(self) -> None:
        with self.repositories.database.transaction() as connection:
            self.repositories.machine_status.save(
                self.core.machine_status_service.runtime.status,
                machine_id=self.config.machine.machine_id,
                _connection=connection,
            )
            self.repositories.money_inventory.save(self.money_inventory, _connection=connection)


async def build_production_environment(
    *,
    config_path: str | Path,
    prepare_directories: bool = True,
) -> ProductionRuntimeEnvironment:
    config, yaml_text, report = validate_config_file(
        config_path, prepare_directories=prepare_directories
    )
    if not report.valid:
        errors = [m.message for m in report.messages if m.severity == "error"]
        raise ValueError("; ".join(errors))

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
            source_path=str(report.config_path), yaml_text=yaml_text
        )
    for device_name, device_config in build_device_settings_snapshot(config).items():
        repositories.device_settings.save(
            logical_device_name=device_name,
            driver_name=str(device_config.get("driver", "unknown")),
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
    devices = _build_production_devices(config)

    core = build_application_core(
        validator=devices.validator,
        change_dispenser=devices.change_dispenser,
        motor_controller=devices.motor_controller,
        window_controller=devices.window_controller,
        inventory_service=inventory_service,
        money_inventory=money_inventory,
        devices=devices.managed(),
        accepted_bill_denominations=tuple(
            config.devices.bill_validator.accepted_denominations_minor
        ),
        door_sensor=devices.door_sensor,
        temperature_sensor=devices.temperature_sensor,
        inventory_sensor=None,
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

    ui_facade = UiApplicationFacade(
        core,
        event_store=event_store,
        simulator_controls=None,
        platform_profile=report.platform_profile,
        repositories=repositories,
        machine_id=config.machine.machine_id,
    )

    return ProductionRuntimeEnvironment(
        config=config,
        config_path=report.config_path,
        report=report,
        logger=logger,
        repositories=repositories,
        devices=devices,
        inventory_service=inventory_service,
        money_inventory=money_inventory,
        core=core,
        ui_facade=ui_facade,
        event_store=event_store,
        platform_profile=report.platform_profile,
        yaml_text=yaml_text,
    )

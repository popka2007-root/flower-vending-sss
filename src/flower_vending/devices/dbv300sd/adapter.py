"""Domain-facing JCM DBV-300-SD validator adapter."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import Final

from flower_vending.devices.command_policy import DeviceCommandRunner
from flower_vending.devices.contracts import (
    BillValidatorEvent,
    BillValidatorEventType,
    DeviceFault,
    DeviceHealth,
    DeviceOperationalState,
    ValidatorProtocolEvent,
    utc_now,
)
from flower_vending.devices.dbv300sd.config import (
    DBV300ProtocolKind,
    DBV300SDValidatorConfig,
    DBV300TransportKind,
)
from flower_vending.devices.dbv300sd.protocol import (
    DBV300Protocol,
    DeferredMDBProtocol,
    DeferredPulseProtocol,
)
from flower_vending.devices.dbv300sd.protocol.jcm_serial import (
    JCMSerialDBV300Protocol,
    JcmProtocolConfig,
)
from flower_vending.devices.dbv300sd.transport import DBV300Transport, SerialDBV300Transport
from flower_vending.devices.exceptions import (
    DeviceNotStartedError,
    HardwareConfirmationRequiredError,
    UnsupportedDeviceOperationError,
)
from flower_vending.devices.interfaces import BillValidator

_POLL_TASK_NAME_SUFFIX: Final[str] = "-poll"


class DBV300SDValidator(BillValidator):
    """Translate a transport/protocol pair into a domain-facing validator adapter.

    The adapter lifecycle and polling loop are fully implemented here. What remains
    intentionally deferred is the actual JCM protocol implementation, because those
    details must come from vendor documentation and real bench validation.
    """

    def __init__(
        self,
        config: DBV300SDValidatorConfig,
        transport: DBV300Transport,
        protocol: DBV300Protocol,
    ) -> None:
        self._config = config
        self._transport = transport
        self._protocol = protocol
        self._events: asyncio.Queue[BillValidatorEvent] = asyncio.Queue()
        self._lock = asyncio.Lock()
        self._poll_task: asyncio.Task[None] | None = None
        self._stop_requested = asyncio.Event()
        self._started = False
        self._acceptance_enabled = False
        self._command_runner = DeviceCommandRunner(
            device_name=config.device_name,
            default_policy=config.command_policy,
            activate_fault=self._activate_command_fault,
            heartbeat=self._heartbeat,
        )
        self._health = DeviceHealth(
            name=config.device_name,
            state=DeviceOperationalState.UNKNOWN,
            details={
                "transport_kind": config.transport_kind.value,
                "protocol_kind": config.protocol_kind.value,
            },
        )
        self._consecutive_faults = 0
        self._backoff_factor = 2.0
        self._max_backoff_s = 30.0

    @property
    def name(self) -> str:
        return self._config.device_name

    def supports_escrow(self) -> bool:
        return self._protocol.capabilities.escrow_supported

    async def start(self) -> None:
        async with self._lock:
            if self._started:
                return
            self._health = replace(self._health, state=DeviceOperationalState.INITIALIZING)
            await self._transport.open()
            # FIX: Zombie poll task guard — if start() fails AFTER create_task
            # but BEFORE _started = True, the poll task runs on a half-initialized
            # transport. We create the task last and track it so the except
            # handler can cancel it.
            try:
                await self._protocol.initialize(self._transport)
                if self._config.startup_disable_acceptance:
                    await self._protocol.set_acceptance_enabled(self._transport, False)
                self._acceptance_enabled = False
                self._stop_requested.clear()
                self._health = replace(
                    self._health,
                    state=DeviceOperationalState.READY,
                    last_heartbeat_at=utc_now(),
                )
                self._poll_task = asyncio.create_task(
                    self._poll_loop(),
                    name=f"{self.name}{_POLL_TASK_NAME_SUFFIX}",
                )
                self._started = True
            except Exception as exc:
                self._health = self._fault_health("startup_failed", str(exc))
                raise
            finally:
                if not self._started:
                    if self._poll_task is not None:
                        self._poll_task.cancel()
                        try:
                            await self._poll_task
                        except asyncio.CancelledError:
                            pass
                        self._poll_task = None
                    await self._safe_shutdown_transport()

    async def stop(self) -> None:
        async with self._lock:
            self._stop_requested.set()
            if self._poll_task is not None:
                self._poll_task.cancel()
                try:
                    await self._poll_task
                except asyncio.CancelledError:
                    pass
                finally:
                    self._poll_task = None
            await self._safe_shutdown_transport()
            self._started = False
            self._acceptance_enabled = False
            self._health = replace(
                self._health,
                state=DeviceOperationalState.DISABLED,
                last_heartbeat_at=utc_now(),
            )

    async def get_health(self) -> DeviceHealth:
        return self._health

    async def enable_acceptance(self, correlation_id: str | None = None) -> None:
        self._require_started()

        async def operation() -> None:
            await self._protocol.set_acceptance_enabled(self._transport, True)
            self._acceptance_enabled = True

        await self._command_runner.run(
            "enable_acceptance",
            operation,
            correlation_id=correlation_id,
            idempotency_key=correlation_id,
        )

    async def disable_acceptance(self, correlation_id: str | None = None) -> None:
        self._require_started()

        async def operation() -> None:
            await self._protocol.set_acceptance_enabled(self._transport, False)
            self._acceptance_enabled = False
            await self._emit_event(
                BillValidatorEvent(
                    event_type=BillValidatorEventType.VALIDATOR_DISABLED,
                    validator_name=self.name,
                    correlation_id=correlation_id,
                )
            )

        await self._command_runner.run(
            "disable_acceptance",
            operation,
            correlation_id=correlation_id,
            idempotency_key=correlation_id,
            success_state=DeviceOperationalState.DISABLED,
        )

    async def accept_escrow(self, correlation_id: str | None = None) -> None:
        self._require_started()
        if not self.supports_escrow():
            raise UnsupportedDeviceOperationError(
                f"{self.name} protocol {self._protocol.name} does not confirm escrow support"
            )

        async def operation() -> None:
            await self._protocol.stack_escrow(self._transport)

        await self._command_runner.run(
            "accept_escrow",
            operation,
            correlation_id=correlation_id,
            idempotency_key=correlation_id,
        )

    async def return_escrow(self, correlation_id: str | None = None) -> None:
        self._require_started()
        if not self.supports_escrow():
            raise UnsupportedDeviceOperationError(
                f"{self.name} protocol {self._protocol.name} does not confirm escrow support"
            )

        async def operation() -> None:
            await self._protocol.return_escrow(self._transport)

        await self._command_runner.run(
            "return_escrow",
            operation,
            correlation_id=correlation_id,
            idempotency_key=correlation_id,
        )

    async def read_event(self, timeout_s: float | None = None) -> BillValidatorEvent | None:
        if timeout_s is None:
            return await self._events.get()
        try:
            return await asyncio.wait_for(self._events.get(), timeout=timeout_s)
        except asyncio.TimeoutError:
            return None

    def _reset_fault_counter(self) -> None:
        self._consecutive_faults = 0

    def _increment_fault_counter(self) -> None:
        self._consecutive_faults += 1

    async def _apply_backoff(self) -> None:
        poll_interval = self._config.poll_interval_s
        if self._consecutive_faults > 0:
            poll_interval = min(
                poll_interval * (self._backoff_factor ** min(self._consecutive_faults, 5)),
                self._max_backoff_s,
            )
        await asyncio.sleep(poll_interval)

    async def _poll_loop(self) -> None:
        self._reset_fault_counter()
        while not self._stop_requested.is_set():
            try:
                protocol_events = await self._protocol.poll(self._transport)
                now = utc_now()
                self._health = replace(
                    self._health,
                    state=DeviceOperationalState.READY,
                    last_heartbeat_at=now,
                )
                for event in protocol_events:
                    await self._emit_event(self._translate_event(event))
                self._reset_fault_counter()
            except asyncio.CancelledError:
                raise
            except HardwareConfirmationRequiredError as exc:
                self._health = self._fault_health("hardware_confirmation_required", str(exc))
                return
            except Exception as exc:
                await self._handle_fault(exc)
                self._increment_fault_counter()
            await self._apply_backoff()

    async def _emit_event(self, event: BillValidatorEvent) -> None:
        if event.event_type is BillValidatorEventType.VALIDATOR_DISABLED:
            self._acceptance_enabled = False
        await self._events.put(event)

    async def _handle_fault(self, exc: Exception) -> None:
        self._acceptance_enabled = False
        self._health = self._fault_health("validator_fault", str(exc))
        await self._emit_event(
            BillValidatorEvent(
                event_type=BillValidatorEventType.VALIDATOR_FAULT,
                validator_name=self.name,
                details={"error": str(exc)},
            )
        )
        if self._config.fallback_disable_on_fault:
            try:
                await self._protocol.set_acceptance_enabled(self._transport, False)
            except Exception:
                return

    def _translate_event(self, event: ValidatorProtocolEvent) -> BillValidatorEvent:
        if event.event_type is BillValidatorEventType.VALIDATOR_DISABLED:
            self._acceptance_enabled = False
        return BillValidatorEvent(
            event_type=event.event_type,
            validator_name=self.name,
            occurred_at=event.occurred_at,
            correlation_id=event.correlation_id,
            bill_value=event.bill_value,
            sequence_number=event.sequence_number,
            raw_payload=event.raw_payload,
            details=event.details,
        )

    async def _safe_shutdown_transport(self) -> None:
        try:
            if self._transport.is_open:
                await self._protocol.shutdown(self._transport)
        finally:
            if self._transport.is_open:
                await self._transport.close()

    def _require_started(self) -> None:
        if not self._started:
            raise DeviceNotStartedError(f"{self.name} has not been started")

    def _fault_health(self, code: str, message: str) -> DeviceHealth:
        return DeviceHealth(
            name=self.name,
            state=DeviceOperationalState.FAULT,
            last_heartbeat_at=utc_now(),
            faults=(DeviceFault(code=code, message=message),),
            details={
                "transport_kind": self._config.transport_kind.value,
                "protocol_kind": self._config.protocol_kind.value,
            },
        )

    def _activate_command_fault(
        self,
        code: str,
        message: str,
        *,
        critical: bool = True,
        **details: object,
    ) -> None:
        self._health = DeviceHealth(
            name=self.name,
            state=DeviceOperationalState.FAULT if critical else DeviceOperationalState.DEGRADED,
            last_heartbeat_at=utc_now(),
            faults=(DeviceFault(code=code, message=message, critical=critical, details=details),),
            details={
                "transport_kind": self._config.transport_kind.value,
                "protocol_kind": self._config.protocol_kind.value,
                **details,
            },
        )

    def _heartbeat(self, *, state: DeviceOperationalState | None = None, **details: object) -> None:
        self._health = DeviceHealth(
            name=self.name,
            state=state or self._health.state,
            last_heartbeat_at=utc_now(),
            faults=self._health.faults,
            details={
                "transport_kind": self._config.transport_kind.value,
                "protocol_kind": self._config.protocol_kind.value,
                **details,
            },
        )


def build_dbv300sd_validator(config: DBV300SDValidatorConfig) -> DBV300SDValidator:
    """Build the validator adapter from configuration.

    The known lab fact that the device is connected through a Windows `COM3` port
    belongs in `config.serial_transport.port`, not in domain logic and not in this
    function as a hardcoded value.
    """

    transport = _build_transport(config)
    protocol = _build_protocol(config)
    return DBV300SDValidator(config=config, transport=transport, protocol=protocol)


def _build_transport(config: DBV300SDValidatorConfig) -> DBV300Transport:
    if config.transport_kind is DBV300TransportKind.SERIAL:
        return SerialDBV300Transport(config.require_serial_transport())
    raise HardwareConfirmationRequiredError(
        f"{config.transport_kind.value} transport requires real hardware integration work"
    )


def _build_protocol(config: DBV300SDValidatorConfig) -> DBV300Protocol:
    if config.protocol_kind is DBV300ProtocolKind.SERIAL:
        protocol_config = JcmProtocolConfig(
            poll_interval_s=config.poll_interval_s,
            denomination_map=None,
        )
        return JCMSerialDBV300Protocol(protocol_config)
    if config.protocol_kind is DBV300ProtocolKind.MDB:
        return DeferredMDBProtocol()
    if config.protocol_kind is DBV300ProtocolKind.PULSE:
        return DeferredPulseProtocol()
    raise HardwareConfirmationRequiredError(
        f"unsupported DBV-300-SD protocol kind: {config.protocol_kind.value}"
    )

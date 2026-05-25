"""Hardware abstraction interfaces for the vending machine."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Mapping

from flower_vending.devices.contracts import (
    BillValidatorEvent,
    ChangeDispenseRequest,
    ChangeDispenseResult,
    DeviceHealth,
    DoorStatus,
    InventoryPresence,
    PositionReading,
    TemperatureReading,
    WindowStatus,
)


class ManagedDevice(ABC):
    """Base lifecycle contract for any device adapter."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the configured device name."""

    @abstractmethod
    async def start(self) -> None:
        """Start the adapter and acquire external resources."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop the adapter and release external resources."""

    @abstractmethod
    async def get_health(self) -> DeviceHealth:
        """Return the latest normalized device health snapshot."""


class BillValidator(ManagedDevice):
    """Domain-facing contract for banknote validators."""

    @abstractmethod
    def supports_escrow(self) -> bool:
        """Return whether explicit escrow actions are supported."""

    @abstractmethod
    async def enable_acceptance(self, correlation_id: str | None = None) -> None:
        """Enable customer bill acceptance."""

    @abstractmethod
    async def disable_acceptance(self, correlation_id: str | None = None) -> None:
        """Disable customer bill acceptance."""

    @abstractmethod
    async def accept_escrow(self, correlation_id: str | None = None) -> None:
        """Move the currently escrowed bill into stacked cash when supported."""

    @abstractmethod
    async def return_escrow(self, correlation_id: str | None = None) -> None:
        """Return the currently escrowed bill when supported."""

    @abstractmethod
    async def read_event(self, timeout_s: float | None = None) -> BillValidatorEvent | None:
        """Read the next normalized validator event."""

    async def events(self, timeout_s: float | None = None) -> AsyncIterator[BillValidatorEvent]:
        """Iterate over normalized validator events."""
        while True:
            event = await self.read_event(timeout_s=timeout_s)
            if event is None:
                return
            yield event


class ChangeDispenser(ManagedDevice):
    """Contract for the change payout subsystem."""

    @abstractmethod
    async def can_dispense(self, request: ChangeDispenseRequest) -> bool:
        """Check whether the requested payout is safe and feasible."""

    @abstractmethod
    async def dispense(self, request: ChangeDispenseRequest) -> ChangeDispenseResult:
        """Attempt to dispense the requested change."""

    @abstractmethod
    async def get_accounting_inventory(self) -> Mapping[int, int]:
        """Return the device-facing accounting view of available denominations."""


class MotorController(ManagedDevice):
    """Contract for vend motor or carousel control."""

    @abstractmethod
    async def home(self, correlation_id: str | None = None) -> None:
        """Move the mechanism to a defined home position."""

    @abstractmethod
    async def vend_slot(self, slot_id: str, correlation_id: str | None = None) -> None:
        """Run the vend motion for the given slot."""

    @abstractmethod
    async def stop_motion(self) -> None:
        """Stop motion as safely as the device allows."""

    @abstractmethod
    async def start_motion(self) -> None:
        """Start continuous motion (display rotation / showcase mode)."""


class CoolingController(ManagedDevice):
    """Contract for compressor or cooling control."""

    @abstractmethod
    async def set_enabled(self, enabled: bool) -> None:
        """Enable or disable cooling output."""

    @abstractmethod
    async def set_target_celsius(self, target_celsius: float) -> None:
        """Set the desired chamber temperature target."""


class WindowController(ManagedDevice):
    """Contract for the delivery window actuator."""

    @abstractmethod
    async def open_window(self, correlation_id: str | None = None) -> None:
        """Open the customer delivery window."""

    @abstractmethod
    async def close_window(self, correlation_id: str | None = None) -> None:
        """Close the customer delivery window."""

    @abstractmethod
    async def get_window_status(self) -> WindowStatus:
        """Return the latest delivery window state."""


class TemperatureSensor(ManagedDevice):
    """Contract for chamber temperature sensing."""

    @abstractmethod
    async def read_temperature(self) -> TemperatureReading:
        """Return the current chamber temperature."""


class DoorSensor(ManagedDevice):
    """Contract for the service door sensor."""

    @abstractmethod
    async def read_service_door(self) -> DoorStatus:
        """Return whether the service door is open."""


class InventorySensor(ManagedDevice):
    """Contract for slot-level inventory sensing."""

    @abstractmethod
    async def read_slot(self, slot_id: str) -> InventoryPresence:
        """Return the sensed presence for a slot."""


class PositionSensor(ManagedDevice):
    """Contract for mechanism position sensing."""

    @abstractmethod
    async def read_position(self) -> PositionReading:
        """Return the current normalized mechanism position."""


class WatchdogAdapter(ManagedDevice):
    """Contract for OS or hardware watchdog integration."""

    @abstractmethod
    async def arm(self, timeout_s: float) -> None:
        """Arm the watchdog with the requested timeout."""

    @abstractmethod
    async def kick(self) -> None:
        """Refresh the watchdog heartbeat."""

    @abstractmethod
    async def disarm(self) -> None:
        """Disarm the watchdog when supported."""

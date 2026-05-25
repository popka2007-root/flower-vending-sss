"""Protocol-level abstractions for the JCM DBV-300-SD."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from flower_vending.devices.contracts import ProtocolCapabilities, ValidatorProtocolEvent
from flower_vending.devices.dbv300sd.transport.base import DBV300Transport
from flower_vending.devices.exceptions import HardwareConfirmationRequiredError


class DBV300Protocol(ABC):
    """Semantic protocol contract above raw transport and below device adapter."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the protocol implementation name."""

    @property
    @abstractmethod
    def capabilities(self) -> ProtocolCapabilities:
        """Return protocol capabilities confirmed by implementation."""

    @abstractmethod
    async def initialize(self, transport: DBV300Transport) -> None:
        """Initialize the validator on the configured transport."""

    @abstractmethod
    async def shutdown(self, transport: DBV300Transport) -> None:
        """Gracefully stop protocol activity where supported."""

    @abstractmethod
    async def set_acceptance_enabled(self, transport: DBV300Transport, enabled: bool) -> None:
        """Enable or disable bill acceptance on the device."""

    @abstractmethod
    async def poll(self, transport: DBV300Transport) -> Sequence[ValidatorProtocolEvent]:
        """Poll the device and return normalized protocol events."""

    @abstractmethod
    async def stack_escrow(self, transport: DBV300Transport) -> None:
        """Accept the current escrowed bill when supported."""

    @abstractmethod
    async def return_escrow(self, transport: DBV300Transport) -> None:
        """Return the current escrowed bill when supported."""


class _DeferredProtocol(DBV300Protocol):
    """Placeholder used until the real JCM protocol is confirmed."""

    def __init__(self, name: str, confirmation_topic: str) -> None:
        self._name = name
        self._confirmation_topic = confirmation_topic

    @property
    def name(self) -> str:
        return self._name

    @property
    def capabilities(self) -> ProtocolCapabilities:
        return ProtocolCapabilities()

    async def initialize(self, transport: DBV300Transport) -> None:
        raise self._hardware_confirmation_error()

    async def shutdown(self, transport: DBV300Transport) -> None:
        return None

    async def set_acceptance_enabled(self, transport: DBV300Transport, enabled: bool) -> None:
        raise self._hardware_confirmation_error()

    async def poll(self, transport: DBV300Transport) -> Sequence[ValidatorProtocolEvent]:
        raise self._hardware_confirmation_error()

    async def stack_escrow(self, transport: DBV300Transport) -> None:
        raise self._hardware_confirmation_error()

    async def return_escrow(self, transport: DBV300Transport) -> None:
        raise self._hardware_confirmation_error()

    def _hardware_confirmation_error(self) -> HardwareConfirmationRequiredError:
        return HardwareConfirmationRequiredError(
            f"{self._name} requires confirmed JCM DBV-300-SD documentation and bench validation "
            f"for {self._confirmation_topic}"
        )


class DeferredMDBProtocol(_DeferredProtocol):
    def __init__(self) -> None:
        super().__init__(
            name="dbv300sd-mdb-protocol",
            confirmation_topic="MDB bus command set, addressing, and state mapping",
        )


class DeferredPulseProtocol(_DeferredProtocol):
    def __init__(self) -> None:
        super().__init__(
            name="dbv300sd-pulse-protocol",
            confirmation_topic="pulse timing, denomination mapping, and escrow semantics",
        )

from __future__ import annotations

import unittest
from collections.abc import Sequence

from flower_vending.devices.contracts import (
    BillValidatorEventType,
    MoneyValue,
    ProtocolCapabilities,
    ValidatorProtocolEvent,
)
from flower_vending.devices.dbv300sd.adapter import _build_protocol
from flower_vending.devices.dbv300sd.config import DBV300ProtocolKind, DBV300SDValidatorConfig, DBV300TransportKind, SerialTransportSettings
from flower_vending.devices.dbv300sd.protocol import (
    DBV300Protocol,
    DeferredMDBProtocol,
    DeferredPulseProtocol,
)
from flower_vending.devices.dbv300sd.transport import DBV300Transport
from flower_vending.devices.exceptions import (
    DeviceAdapterError,
    HardwareConfirmationRequiredError,
    ProtocolDecodeError,
)


class FakeTransport(DBV300Transport):
    def __init__(self, read_payloads: Sequence[bytes] = ()) -> None:
        self.calls: list[str | tuple[str, bytes] | tuple[str, int]] = []
        self.read_payloads = list(read_payloads)
        self._is_open = False

    @property
    def name(self) -> str:
        return "fake-transport"

    @property
    def is_open(self) -> bool:
        return self._is_open

    async def open(self) -> None:
        self.calls.append("open")
        self._is_open = True

    async def close(self) -> None:
        self.calls.append("close")
        self._is_open = False

    async def write(self, payload: bytes) -> None:
        self.calls.append(("write", payload))

    async def read(self, size: int = 1) -> bytes:
        self.calls.append(("read", size))
        if self.read_payloads:
            return self.read_payloads.pop(0)
        return b""

    async def flush_input(self) -> None:
        self.calls.append("flush_input")


class FakeConfirmedDBV300Protocol(DBV300Protocol):
    """Test-only protocol used to define DBV300Protocol conformance expectations."""

    @property
    def name(self) -> str:
        return "fake-confirmed-dbv300-protocol"

    @property
    def capabilities(self) -> ProtocolCapabilities:
        return ProtocolCapabilities(escrow_supported=True)

    async def initialize(self, transport: DBV300Transport) -> None:
        await transport.flush_input()
        await transport.write(b"fake-init")

    async def shutdown(self, transport: DBV300Transport) -> None:
        await transport.write(b"fake-shutdown")

    async def set_acceptance_enabled(self, transport: DBV300Transport, enabled: bool) -> None:
        await transport.write(b"fake-enable" if enabled else b"fake-disable")

    async def poll(self, transport: DBV300Transport) -> Sequence[ValidatorProtocolEvent]:
        raw = await transport.read(64)
        if raw == b"":
            return ()
        if raw == b"hardware-unconfirmed":
            raise HardwareConfirmationRequiredError("fake hardware detail is not confirmed")
        if raw == b"decode-fault":
            raise ProtocolDecodeError("fake protocol event could not be decoded")
        if raw.startswith(b"bill-validated:"):
            minor_units = int(raw.split(b":", maxsplit=1)[1])
            return (
                ValidatorProtocolEvent(
                    event_type=BillValidatorEventType.BILL_VALIDATED,
                    bill_value=MoneyValue(minor_units),
                    raw_payload=raw,
                    details={"source": "fake_protocol"},
                ),
            )
        raise ProtocolDecodeError("unknown fake protocol event")

    async def stack_escrow(self, transport: DBV300Transport) -> None:
        await transport.write(b"fake-stack-escrow")

    async def return_escrow(self, transport: DBV300Transport) -> None:
        await transport.write(b"fake-return-escrow")


class DBV300ProtocolConformanceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.protocol = FakeConfirmedDBV300Protocol()

    async def test_initialize_calls_expected_transport_methods(self) -> None:
        transport = FakeTransport()
        await self.protocol.initialize(transport)
        self.assertEqual(transport.calls, ["flush_input", ("write", b"fake-init")])

    async def test_poll_maps_raw_protocol_events_to_validator_protocol_event(self) -> None:
        transport = FakeTransport(read_payloads=[b"bill-validated:500"])
        events = await self.protocol.poll(transport)
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event.event_type, BillValidatorEventType.BILL_VALIDATED)
        self.assertEqual(event.bill_value, MoneyValue(500))
        self.assertEqual(event.raw_payload, b"bill-validated:500")
        self.assertEqual(event.details["source"], "fake_protocol")
        self.assertEqual(transport.calls, [("read", 64)])

    async def test_poll_fault_paths_raise_confirmation_or_adapter_errors(self) -> None:
        with self.assertRaises(HardwareConfirmationRequiredError):
            await self.protocol.poll(FakeTransport(read_payloads=[b"hardware-unconfirmed"]))
        with self.assertRaises(DeviceAdapterError):
            await self.protocol.poll(FakeTransport(read_payloads=[b"decode-fault"]))

    def test_build_protocol_returns_correct_types(self) -> None:
        from flower_vending.devices.dbv300sd.protocol.jcm_serial import JCMSerialDBV300Protocol

        config = DBV300SDValidatorConfig(
            device_name="test",
            transport_kind=DBV300TransportKind.SERIAL,
            protocol_kind=DBV300ProtocolKind.SERIAL,
            serial_transport=SerialTransportSettings(port="COM_TEST"),
            poll_interval_s=0.2,
        )
        self.assertIsInstance(_build_protocol(config), JCMSerialDBV300Protocol)
        object.__setattr__(config, "protocol_kind", DBV300ProtocolKind.MDB)
        self.assertIsInstance(_build_protocol(config), DeferredMDBProtocol)
        object.__setattr__(config, "protocol_kind", DBV300ProtocolKind.PULSE)
        self.assertIsInstance(_build_protocol(config), DeferredPulseProtocol)


if __name__ == "__main__":
    unittest.main()

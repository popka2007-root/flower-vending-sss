from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any

from tests._support import workspace_temp_dir

from flower_vending.devices.dbv300sd.bench import DBV300SDSerialSmokeBench, parse_hex_bytes
from flower_vending.devices.dbv300sd.config import SerialTransportSettings
from flower_vending.devices.exceptions import ConfigurationError


class _FakeSerialPort:
    def __init__(self, *, read_payload: bytes = b"") -> None:
        self.is_open = True
        self.read_payload = read_payload
        self.writes: list[bytes] = []
        self.reset_input_buffer_called = False
        self.closed = False

    def write(self, payload: bytes) -> int:
        self.writes.append(payload)
        return len(payload)

    def flush(self) -> None:
        return None

    def read(self, size: int) -> bytes:
        return self.read_payload[:size]

    def reset_input_buffer(self) -> None:
        self.reset_input_buffer_called = True

    def close(self) -> None:
        self.is_open = False
        self.closed = True


class _FakeSerialModule:
    def __init__(self, port: _FakeSerialPort) -> None:
        self.port = port
        self.open_kwargs: dict[str, Any] | None = None

    def Serial(self, **kwargs: Any) -> _FakeSerialPort:
        self.open_kwargs = kwargs
        return self.port


class DBV300SDBenchTests(unittest.IsolatedAsyncioTestCase):
    async def test_serial_smoke_opens_port_and_logs_settings_without_raw_io(self) -> None:
        fake_port = _FakeSerialPort()
        fake_module = _FakeSerialModule(fake_port)
        settings = SerialTransportSettings(port="BENCH")

        with workspace_temp_dir(prefix="dbv-bench-") as tmp:
            trace_log = Path(tmp) / "trace.jsonl"
            bench = DBV300SDSerialSmokeBench(
                settings=settings,
                trace_log=trace_log,
                serial_module=fake_module,
            )
            result = await bench.run(correlation_id="smoke-1")
            lines = trace_log.read_text(encoding="utf-8").splitlines()

        self.assertTrue(result.opened)
        self.assertEqual(result.wrote_bytes, 0)
        self.assertEqual(result.read_bytes, 0)
        self.assertEqual(fake_port.writes, [])
        self.assertTrue(fake_port.closed)
        self.assertIsNotNone(fake_module.open_kwargs)
        open_kwargs = fake_module.open_kwargs
        assert open_kwargs is not None
        self.assertEqual(open_kwargs["port"], "BENCH")

        self.assertEqual(len(lines), 1)
        payload = json.loads(lines[0])
        self.assertEqual(payload["event"], "serial_parameters")
        self.assertEqual(payload["serial_settings"]["port"], "BENCH")
        self.assertEqual(payload["correlation_id"], "smoke-1")

    async def test_serial_smoke_records_explicit_tx_and_rx_frames(self) -> None:
        fake_port = _FakeSerialPort(read_payload=b"\x10\x20")
        settings = SerialTransportSettings(port="BENCH")

        with workspace_temp_dir(prefix="dbv-bench-") as tmp:
            trace_log = Path(tmp) / "trace.jsonl"
            bench = DBV300SDSerialSmokeBench(
                settings=settings,
                trace_log=trace_log,
                serial_module=_FakeSerialModule(fake_port),
            )
            result = await bench.run(
                tx_payload=b"\x01\xff",
                read_size=2,
                correlation_id="exchange-1",
            )
            records = [
                json.loads(line) for line in trace_log.read_text(encoding="utf-8").splitlines()
            ]

        self.assertEqual(result.wrote_bytes, 2)
        self.assertEqual(result.read_bytes, 2)
        self.assertEqual(fake_port.writes, [b"\x01\xff"])
        self.assertTrue(fake_port.reset_input_buffer_called)

        self.assertEqual(records[1]["direction"], "tx")
        self.assertEqual(records[1]["raw_bytes_hex"], "01 FF")
        self.assertEqual(records[1]["correlation_id"], "exchange-1")
        self.assertEqual(records[2]["direction"], "rx")
        self.assertEqual(records[2]["raw_bytes_hex"], "10 20")

    async def test_serial_smoke_rejects_read_without_explicit_raw_tx(self) -> None:
        settings = SerialTransportSettings(port="BENCH")

        with workspace_temp_dir(prefix="dbv-bench-") as tmp:
            bench = DBV300SDSerialSmokeBench(
                settings=settings,
                trace_log=Path(tmp) / "trace.jsonl",
                serial_module=_FakeSerialModule(_FakeSerialPort()),
            )
            with self.assertRaises(ConfigurationError):
                await bench.run(read_size=1)

    def test_parse_hex_bytes_requires_explicit_valid_hex(self) -> None:
        self.assertEqual(parse_hex_bytes("0x01, 02 FF"), b"\x01\x02\xff")
        with self.assertRaises(ConfigurationError):
            parse_hex_bytes("")
        with self.assertRaises(ConfigurationError):
            parse_hex_bytes("not-hex")


if __name__ == "__main__":
    unittest.main()

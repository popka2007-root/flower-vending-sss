from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock

from flower_vending.devices.contracts import DeviceOperationalState
from flower_vending.devices.dbv300sd.adapter import DBV300SDValidator
from flower_vending.devices.dbv300sd.config import (
    DBV300ProtocolKind,
    DBV300SDValidatorConfig,
    DBV300TransportKind,
    SerialTransportSettings,
)
from flower_vending.devices.dbv300sd.protocol import DBV300Protocol
from flower_vending.devices.dbv300sd.transport import DBV300Transport


class DBV300SDAdapterLifecycleTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.config = DBV300SDValidatorConfig(
            device_name="test-validator",
            transport_kind=DBV300TransportKind.SERIAL,
            protocol_kind=DBV300ProtocolKind.SERIAL,
            serial_transport=SerialTransportSettings(port="COM_TEST"),
            poll_interval_s=0.01,
        )
        self.transport = MagicMock(spec=DBV300Transport)
        self.transport.open = AsyncMock()
        self.transport.close = AsyncMock()
        self.transport.is_open = False

        self.protocol = MagicMock(spec=DBV300Protocol)
        self.protocol.initialize = AsyncMock()
        self.protocol.shutdown = AsyncMock()
        self.protocol.poll = AsyncMock(return_value=[])
        self.protocol.set_acceptance_enabled = AsyncMock()
        self.protocol.capabilities.escrow_supported = True

        self.validator = DBV300SDValidator(
            config=self.config,
            transport=self.transport,
            protocol=self.protocol,
        )

    async def test_start_failure_cancels_poll_task_and_closes_transport(self) -> None:
        # Arrange: simulate failure during protocol initialization
        self.transport.open.side_effect = lambda: setattr(self.transport, "is_open", True)
        self.protocol.initialize.side_effect = Exception("init failed")

        # Act & Assert
        with self.assertRaisesRegex(Exception, "init failed"):
            await self.validator.start()

        # Verify: health is FAULT
        health = await self.validator.get_health()
        self.assertEqual(health.state, DeviceOperationalState.FAULT)
        self.assertEqual(health.faults[0].code, "startup_failed")

        # Verify: transport was closed
        self.transport.close.assert_called_once()

        # Verify: poll task is not running
        self.assertIsNone(self.validator._poll_task)

    async def test_start_success_sets_ready_and_starts_poll_task(self) -> None:
        # Arrange
        self.transport.open.side_effect = lambda: setattr(self.transport, "is_open", True)

        # Act
        await self.validator.start()

        # Assert
        health = await self.validator.get_health()
        self.assertEqual(health.state, DeviceOperationalState.READY)
        self.assertIsNotNone(self.validator._poll_task)
        self.assertFalse(self.validator._poll_task.done())

        # Cleanup
        await self.validator.stop()

    async def test_stop_cancels_poll_task_and_closes_transport(self) -> None:
        # Arrange
        self.transport.open.side_effect = lambda: setattr(self.transport, "is_open", True)
        await self.validator.start()
        poll_task = self.validator._poll_task
        assert poll_task is not None

        # Act
        await self.validator.stop()

        # Assert
        self.assertTrue(poll_task.cancelled() or poll_task.done())
        self.assertIsNone(self.validator._poll_task)
        self.transport.close.assert_called()
        health = await self.validator.get_health()
        self.assertEqual(health.state, DeviceOperationalState.DISABLED)

if __name__ == "__main__":
    unittest.main()

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from flower_vending.app.event_bus import EventBus
from flower_vending.app.orchestrators.health_monitor import HealthMonitor
from flower_vending.app.services.machine_status_service import MachineStatusService
from flower_vending.devices.interfaces import ManagedDevice
from flower_vending.domain.value_objects import DeviceState


@pytest.mark.asyncio
async def test_health_monitor_device_timeout():
    # Arrange
    mock_device = MagicMock(spec=ManagedDevice)
    # Simulate the device hanging and causing a TimeoutError
    mock_device.get_health = AsyncMock(side_effect=asyncio.TimeoutError)

    mock_machine_status_service = MagicMock(spec=MachineStatusService)
    mock_event_bus = MagicMock(spec=EventBus)
    mock_event_bus.publish = AsyncMock()

    monitor = HealthMonitor(
        devices={"validator": mock_device},
        machine_status_service=mock_machine_status_service,
        event_bus=mock_event_bus,
    )

    # Act
    snapshot = await monitor.poll_once(correlation_id="test-corr-id")

    # Assert
    # 1. Device marked as FAULT
    assert snapshot.validator_state == DeviceState.FAULT

    # 2. Faults list contains the timeout fault
    assert "validator_timeout" in snapshot.faults

    # 3. MachineStatusService block_sales was called
    mock_machine_status_service.block_sales.assert_called_with("device_fault:validator")

    # 4. EventBus publish was called with machine_faulted
    mock_event_bus.publish.assert_called_once()
    published_event = mock_event_bus.publish.call_args[0][0]
    assert published_event.event_type == "machine_faulted"
    assert published_event.correlation_id == "test-corr-id"
    assert "validator_timeout" in published_event.payload["faults"]

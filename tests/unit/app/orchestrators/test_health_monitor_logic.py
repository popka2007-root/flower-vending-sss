import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from flower_vending.app.event_bus import EventBus
from flower_vending.app.orchestrators.health_monitor import HealthMonitor
from flower_vending.app.services.machine_status_service import MachineStatusService
from flower_vending.devices.interfaces import DoorSensor, ManagedDevice, TemperatureSensor
from flower_vending.domain.value_objects import DeviceState
from flower_vending.devices.contracts import DoorStatus, TemperatureReading, DeviceOperationalState


@pytest.mark.asyncio
async def test_health_monitor_device_explicit_timeout_error():
    """Test that HealthMonitor handles explicit asyncio.TimeoutError from devices."""
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
    assert snapshot.validator_state == DeviceState.FAULT
    assert "validator_timeout" in snapshot.faults
    mock_machine_status_service.block_sales.assert_called_with("device_fault:validator")
    mock_event_bus.publish.assert_called_once()


@pytest.mark.asyncio
async def test_health_monitor_sensor_timeout_marks_fault():
    """Test that HealthMonitor enforces its own internal timeout for sensors."""
    # Arrange
    mock_device = MagicMock(spec=ManagedDevice)
    mock_device.get_health = AsyncMock(return_value=MagicMock(state=DeviceOperationalState.READY))

    mock_door_sensor = MagicMock(spec=DoorSensor)
    # Simulate door sensor hanging
    async def hanging_read():
        await asyncio.sleep(1.0)
        return DoorStatus(sensor_name="door", is_open=False)
    mock_door_sensor.read_service_door = AsyncMock(side_effect=hanging_read)

    mock_temp_sensor = MagicMock(spec=TemperatureSensor)
    mock_temp_sensor.read_temperature = AsyncMock(return_value=TemperatureReading(sensor_name="temp", celsius=5.0))

    mock_machine_status_service = MagicMock(spec=MachineStatusService)
    mock_event_bus = MagicMock(spec=EventBus)
    mock_event_bus.publish = AsyncMock()

    # Set a very short timeout for testing
    monitor = HealthMonitor(
        devices={"validator": mock_device},
        machine_status_service=mock_machine_status_service,
        event_bus=mock_event_bus,
        door_sensor=mock_door_sensor,
        temperature_sensor=mock_temp_sensor,
        device_health_timeout_s=0.1,
    )

    # Act
    snapshot = await monitor.poll_once(correlation_id="test-timeout")

    # Assert
    assert snapshot.validator_state == DeviceState.READY
    assert snapshot.door_sensor_state == DeviceState.FAULT
    assert "door_sensor_timeout" in snapshot.faults
    mock_machine_status_service.block_sales.assert_called_with("device_fault:door")


@pytest.mark.asyncio
async def test_health_monitor_device_timeout_reports_fault():
    """Test that HealthMonitor enforces its own internal timeout for devices."""
    # Arrange
    mock_device = MagicMock(spec=ManagedDevice)
    async def hanging_health():
        await asyncio.sleep(1.0)
        return MagicMock()
    mock_device.get_health = AsyncMock(side_effect=hanging_health)

    mock_machine_status_service = MagicMock(spec=MachineStatusService)
    mock_event_bus = MagicMock(spec=EventBus)
    mock_event_bus.publish = AsyncMock()

    monitor = HealthMonitor(
        devices={"validator": mock_device},
        machine_status_service=mock_machine_status_service,
        event_bus=mock_event_bus,
        device_health_timeout_s=0.1,
    )

    # Act
    snapshot = await monitor.poll_once(correlation_id="test-device-timeout")

    # Assert
    assert snapshot.validator_state == DeviceState.FAULT
    assert "validator_timeout" in snapshot.faults
    mock_machine_status_service.block_sales.assert_called_with("device_fault:validator")

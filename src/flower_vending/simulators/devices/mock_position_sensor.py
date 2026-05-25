"""Deterministic mock position sensor."""

from __future__ import annotations

from flower_vending.devices.contracts import DeviceCommandPolicy, PositionReading
from flower_vending.devices.interfaces import PositionSensor
from flower_vending.simulators.devices.base import MockManagedDevice


class MockPositionSensor(MockManagedDevice, PositionSensor):
    def __init__(
        self,
        name: str = "mock_position_sensor",
        *,
        position_id: str = "home",
        in_position: bool = True,
        is_home: bool = True,
        command_policy: DeviceCommandPolicy | None = None,
    ) -> None:
        super().__init__(name, command_policy=command_policy)
        self._position_id = position_id
        self._in_position = in_position
        self._is_home = is_home

    async def read_position(self) -> PositionReading:
        self._heartbeat(
            position_id=self._position_id, in_position=self._in_position, is_home=self._is_home
        )
        return PositionReading(
            sensor_name=self.name,
            position_id=self._position_id,
            in_position=self._in_position,
            is_home=self._is_home,
        )

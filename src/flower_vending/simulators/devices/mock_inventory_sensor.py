"""Deterministic mock inventory sensor."""

from __future__ import annotations

from flower_vending.devices.contracts import DeviceCommandPolicy, InventoryPresence
from flower_vending.devices.interfaces import InventorySensor
from flower_vending.simulators.devices.base import MockManagedDevice


class MockInventorySensor(MockManagedDevice, InventorySensor):
    def __init__(
        self,
        name: str = "mock_inventory_sensor",
        *,
        slot_states: dict[str, tuple[bool, float]] | None = None,
        command_policy: DeviceCommandPolicy | None = None,
    ) -> None:
        super().__init__(name, command_policy=command_policy)
        self._slot_states = dict(slot_states or {})

    def set_slot_presence(
        self, slot_id: str, *, has_product: bool, confidence: float = 1.0
    ) -> None:
        self._slot_states[slot_id] = (has_product, confidence)
        self._heartbeat(slot_id=slot_id, has_product=has_product, confidence=confidence)

    async def read_slot(self, slot_id: str) -> InventoryPresence:
        has_product, confidence = self._slot_states.get(slot_id, (False, 0.0))
        self._heartbeat(slot_id=slot_id, has_product=has_product, confidence=confidence)
        return InventoryPresence(
            sensor_name=self.name,
            slot_id=slot_id,
            has_product=has_product,
            confidence=confidence,
        )

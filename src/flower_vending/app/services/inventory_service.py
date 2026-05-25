"""Inventory service used by application orchestrators."""

from __future__ import annotations

from flower_vending.domain.entities import Product, Slot
from flower_vending.domain.exceptions import ProductUnavailableError, SlotUnavailableError


class InventoryService:
    def __init__(
        self,
        products: dict[str, Product] | None = None,
        slots: dict[str, Slot] | None = None,
    ) -> None:
        self._products = products or {}
        self._slots = slots or {}

    def register_product(self, product: Product) -> None:
        self._products[product.product_id.value] = product

    def register_slot(self, slot: Slot) -> None:
        self._slots[slot.slot_id.value] = slot

    def list_slots(self) -> tuple[Slot, ...]:
        return tuple(self._slots[slot_id] for slot_id in sorted(self._slots.keys()))

    def list_catalog(self) -> tuple[tuple[Product, Slot], ...]:
        catalog: list[tuple[Product, Slot]] = []
        for slot in self._slots.values():
            product = self._products.get(slot.product_id.value)
            if product is None:
                continue
            catalog.append((product, slot))

        # Sort by slot_id to ensure predictable ordering
        catalog.sort(key=lambda item: item[1].slot_id.value)
        return tuple(catalog)

    def get_product(self, product_id: str) -> Product:
        try:
            product = self._products[product_id]
        except KeyError as exc:
            raise ProductUnavailableError(f"unknown product: {product_id}") from exc
        if not product.enabled:
            raise ProductUnavailableError(f"product {product_id} is disabled")
        return product

    def get_slot(self, slot_id: str) -> Slot:
        try:
            return self._slots[slot_id]
        except KeyError as exc:
            raise SlotUnavailableError(f"unknown slot: {slot_id}") from exc

    def ensure_selection(self, product_id: str, slot_id: str) -> tuple[Product, Slot]:
        product = self.get_product(product_id)
        slot = self.get_slot(slot_id)
        if slot.product_id.value != product.product_id.value:
            raise SlotUnavailableError(f"slot {slot_id} does not serve product {product_id}")
        slot.ensure_sellable()
        return product, slot

    def mark_vended(self, slot_id: str) -> None:
        self.get_slot(slot_id).decrement()

    def set_product_enabled(self, product_id: str, enabled: bool) -> tuple[Product, Slot | None]:
        if product_id not in self._products:
            raise ProductUnavailableError(f"unknown product: {product_id}")
        product = self._products[product_id]
        product.enabled = enabled
        slot = next(
            (s for s in self._slots.values() if s.product_id.value == product_id),
            None,
        )
        return product, slot

    def set_product_stock(self, slot_id: str, quantity: int) -> Slot:
        if slot_id not in self._slots:
            raise SlotUnavailableError(f"unknown slot: {slot_id}")
        slot = self._slots[slot_id]
        slot.quantity = max(0, min(quantity, slot.capacity))
        return slot

    def remove_product(self, product_id: str) -> bool:
        if product_id not in self._products:
            return False
        del self._products[product_id]
        slots_to_remove = [
            sid for sid, s in self._slots.items() if s.product_id.value == product_id
        ]
        for sid in slots_to_remove:
            del self._slots[sid]
        return True

    def add_product(self, product: Product, slot: Slot) -> None:
        self._products[product.product_id.value] = product
        self._slots[slot.slot_id.value] = slot

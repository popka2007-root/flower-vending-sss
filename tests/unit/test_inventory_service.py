import pytest

from flower_vending.app.services.inventory_service import InventoryService
from flower_vending.domain.entities import Product, Slot
from flower_vending.domain.value_objects import Amount, ProductId, SlotId
from flower_vending.domain.exceptions import ProductUnavailableError, SlotUnavailableError


def create_product(pid: str, enabled: bool = True) -> Product:
    return Product(
        product_id=ProductId(pid),
        name=f"Product {pid}",
        display_name=f"Display {pid}",
        price=Amount(minor_units=1000),
        category="flowers",
        enabled=enabled,
    )


def create_slot(
    sid: str, pid: str, capacity: int = 10, quantity: int = 5, enabled: bool = True
) -> Slot:
    return Slot(
        slot_id=SlotId(sid),
        product_id=ProductId(pid),
        capacity=capacity,
        quantity=quantity,
        is_enabled=enabled,
    )


class TestInventoryService:
    def test_get_product_unknown(self) -> None:
        service = InventoryService()
        with pytest.raises(ProductUnavailableError, match="unknown product: p1"):
            service.get_product("p1")

    def test_ensure_selection_unknown_product(self) -> None:
        service = InventoryService()
        service.register_slot(create_slot("s1", "p1"))
        with pytest.raises(ProductUnavailableError, match="unknown product: p1"):
            service.ensure_selection("p1", "s1")

    def test_ensure_selection_slot_mismatch(self) -> None:
        service = InventoryService()
        service.register_product(create_product("p1"))
        # Slot s1 serves p2, not p1
        service.register_slot(create_slot("s1", "p2"))
        with pytest.raises(SlotUnavailableError, match="slot s1 does not serve product p1"):
            service.ensure_selection("p1", "s1")

    def test_ensure_selection_happy_path(self) -> None:
        service = InventoryService()
        p = create_product("p1")
        s = create_slot("s1", "p1")
        service.register_product(p)
        service.register_slot(s)
        prod, slot = service.ensure_selection("p1", "s1")
        assert prod == p
        assert slot == s

    def test_set_product_stock_boundaries(self) -> None:
        service = InventoryService()
        s = create_slot("s1", "p1", capacity=10, quantity=5)
        service.register_slot(s)

        # Set below 0 clamps to 0
        service.set_product_stock("s1", -5)
        assert service.get_slot("s1").quantity == 0

        # Set above capacity clamps to capacity
        service.set_product_stock("s1", 15)
        assert service.get_slot("s1").quantity == 10

        # Normal setting
        service.set_product_stock("s1", 8)
        assert service.get_slot("s1").quantity == 8

    def test_set_product_stock_unknown_slot(self) -> None:
        service = InventoryService()
        with pytest.raises(SlotUnavailableError, match="unknown slot: s1"):
            service.set_product_stock("s1", 5)

    def test_get_product_disabled(self) -> None:
        service = InventoryService()
        service.register_product(create_product("p1", enabled=False))
        with pytest.raises(ProductUnavailableError, match="product p1 is disabled"):
            service.get_product("p1")

    def test_get_slot_unknown(self) -> None:
        service = InventoryService()
        with pytest.raises(SlotUnavailableError, match="unknown slot: s1"):
            service.get_slot("s1")

    def test_list_catalog(self) -> None:
        service = InventoryService()
        p1 = create_product("p1")
        p2 = create_product("p2")
        s1 = create_slot("s1", "p1")
        s2 = create_slot("s2", "p2")

        service.add_product(p1, s1)
        service.add_product(p2, s2)

        catalog = service.list_catalog()
        assert len(catalog) == 2
        assert catalog[0] == (p1, s1)
        assert catalog[1] == (p2, s2)

    def test_mark_vended(self) -> None:
        service = InventoryService()
        s1 = create_slot("s1", "p1", quantity=5)
        service.register_slot(s1)

        service.mark_vended("s1")
        assert service.get_slot("s1").quantity == 4

    def test_set_product_enabled(self) -> None:
        service = InventoryService()
        p1 = create_product("p1", enabled=False)
        s1 = create_slot("s1", "p1")
        service.add_product(p1, s1)

        service.set_product_enabled("p1", True)
        assert service.get_product("p1").enabled is True

    def test_set_product_enabled_unknown(self) -> None:
        service = InventoryService()
        with pytest.raises(ProductUnavailableError, match="unknown product: p1"):
            service.set_product_enabled("p1", True)

    def test_remove_product(self) -> None:
        service = InventoryService()
        p1 = create_product("p1")
        s1 = create_slot("s1", "p1")
        s2 = create_slot("s2", "p1")
        service.add_product(p1, s1)
        service.register_slot(s2)

        assert service.remove_product("p1") is True

        # Verify product and both slots were removed
        with pytest.raises(ProductUnavailableError):
            service.get_product("p1")
        with pytest.raises(SlotUnavailableError):
            service.get_slot("s1")
        with pytest.raises(SlotUnavailableError):
            service.get_slot("s2")

    def test_remove_product_unknown(self) -> None:
        service = InventoryService()
        assert service.remove_product("p1") is False

    def test_list_slots(self) -> None:
        service = InventoryService()
        s1 = create_slot("s1", "p1")
        s2 = create_slot("s2", "p2")
        # Register out of order to ensure sorting works
        service.register_slot(s2)
        service.register_slot(s1)

        slots = service.list_slots()
        assert len(slots) == 2
        assert slots[0] == s1
        assert slots[1] == s2

    def test_list_catalog_missing_product(self) -> None:
        service = InventoryService()
        # Create a slot that points to an unregistered product
        s1 = create_slot("s1", "p1")
        service.register_slot(s1)

        p2 = create_product("p2")
        s2 = create_slot("s2", "p2")
        service.add_product(p2, s2)

        catalog = service.list_catalog()
        # s1 should be skipped
        assert len(catalog) == 1
        assert catalog[0] == (p2, s2)

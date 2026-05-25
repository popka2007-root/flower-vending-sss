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


@pytest.fixture
def service() -> InventoryService:
    return InventoryService()


@pytest.fixture
def product_p1() -> Product:
    return create_product("p1")


@pytest.fixture
def slot_s1() -> Slot:
    return create_slot("s1", "p1")


class TestInventoryService:
    def test_get_product_unknown(self, service: InventoryService) -> None:
        with pytest.raises(ProductUnavailableError, match="unknown product: p1"):
            service.get_product("p1")

    def test_ensure_selection_unknown_product(self, service: InventoryService, slot_s1: Slot) -> None:
        service.register_slot(slot_s1)
        with pytest.raises(ProductUnavailableError, match="unknown product: p1"):
            service.ensure_selection("p1", "s1")

    def test_ensure_selection_slot_mismatch(self, service: InventoryService, product_p1: Product) -> None:
        service.register_product(product_p1)
        # Slot s1 serves p2, not p1
        service.register_slot(create_slot("s1", "p2"))
        with pytest.raises(SlotUnavailableError, match="slot s1 does not serve product p1"):
            service.ensure_selection("p1", "s1")

    def test_ensure_selection_happy_path(self, service: InventoryService, product_p1: Product, slot_s1: Slot) -> None:
        service.register_product(product_p1)
        service.register_slot(slot_s1)
        prod, slot = service.ensure_selection("p1", "s1")
        assert prod == product_p1
        assert slot == slot_s1

    def test_set_product_stock_boundaries(self, service: InventoryService, slot_s1: Slot) -> None:
        service.register_slot(slot_s1)

        # Set below 0 clamps to 0
        service.set_product_stock("s1", -5)
        assert service.get_slot("s1").quantity == 0

        # Set above capacity clamps to capacity
        service.set_product_stock("s1", 15)
        assert service.get_slot("s1").quantity == 10

        # Normal setting
        service.set_product_stock("s1", 8)
        assert service.get_slot("s1").quantity == 8

    def test_set_product_stock_unknown_slot(self, service: InventoryService) -> None:
        with pytest.raises(SlotUnavailableError, match="unknown slot: s1"):
            service.set_product_stock("s1", 5)

    def test_get_product_disabled(self, service: InventoryService) -> None:
        service.register_product(create_product("p1", enabled=False))
        with pytest.raises(ProductUnavailableError, match="product p1 is disabled"):
            service.get_product("p1")

    def test_get_slot_unknown(self, service: InventoryService) -> None:
        with pytest.raises(SlotUnavailableError, match="unknown slot: s1"):
            service.get_slot("s1")

    def test_list_catalog(self, service: InventoryService, product_p1: Product, slot_s1: Slot) -> None:
        p2 = create_product("p2")
        s2 = create_slot("s2", "p2")

        service.add_product(product_p1, slot_s1)
        service.add_product(p2, s2)

        catalog = service.list_catalog()
        assert len(catalog) == 2
        assert catalog[0] == (product_p1, slot_s1)
        assert catalog[1] == (p2, s2)

    def test_mark_vended(self, service: InventoryService, slot_s1: Slot) -> None:
        service.register_slot(slot_s1)
        assert service.get_slot("s1").quantity == 5

        service.mark_vended("s1")
        assert service.get_slot("s1").quantity == 4

    def test_set_product_enabled(self, service: InventoryService, slot_s1: Slot) -> None:
        p1 = create_product("p1", enabled=False)
        service.add_product(p1, slot_s1)

        service.set_product_enabled("p1", True)
        assert service.get_product("p1").enabled is True

    def test_set_product_enabled_unknown(self, service: InventoryService) -> None:
        with pytest.raises(ProductUnavailableError, match="unknown product: p1"):
            service.set_product_enabled("p1", True)

    def test_remove_product(self, service: InventoryService, product_p1: Product, slot_s1: Slot) -> None:
        s2 = create_slot("s2", "p1")
        service.add_product(product_p1, slot_s1)
        service.register_slot(s2)

        assert service.remove_product("p1") is True

        # Verify product and both slots were removed
        with pytest.raises(ProductUnavailableError):
            service.get_product("p1")
        with pytest.raises(SlotUnavailableError):
            service.get_slot("s1")
        with pytest.raises(SlotUnavailableError):
            service.get_slot("s2")

    def test_remove_product_unknown(self, service: InventoryService) -> None:
        assert service.remove_product("p1") is False

    def test_list_slots(self, service: InventoryService, slot_s1: Slot) -> None:
        s2 = create_slot("s2", "p2")
        # Register out of order to ensure sorting works
        service.register_slot(s2)
        service.register_slot(slot_s1)

        slots = service.list_slots()
        assert len(slots) == 2
        assert slots[0] == slot_s1
        assert slots[1] == s2

    def test_list_catalog_missing_product(self, service: InventoryService, slot_s1: Slot) -> None:
        # Create a slot that points to an unregistered product
        service.register_slot(slot_s1)

        p2 = create_product("p2")
        s2 = create_slot("s2", "p2")
        service.add_product(p2, s2)

        catalog = service.list_catalog()
        # s1 should be skipped
        assert len(catalog) == 1
        assert catalog[0] == (p2, s2)

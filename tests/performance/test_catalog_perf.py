import time
from flower_vending.app.services.inventory_service import InventoryService
from flower_vending.domain.entities.product import Product
from flower_vending.domain.entities.slot import Slot
from flower_vending.domain.value_objects import Amount, ProductId, SlotId

def setup_inventory(num_slots=10000, num_products=5000):
    service = InventoryService()
    for i in range(num_products):
        product_id = ProductId(f"prod_{i}")
        product = Product(
            product_id=product_id,
            name=f"Product {i}",
            display_name=f"Display {i}",
            price=Amount(100),
            category="test"
        )
        service.register_product(product)

    for i in range(num_slots):
        slot_id = SlotId(f"slot_{i:05d}")
        product_id = ProductId(f"prod_{i % num_products}")
        slot = Slot(
            slot_id=slot_id,
            product_id=product_id,
            capacity=10,
            quantity=10
        )
        service.register_slot(slot)
    return service

def benchmark():
    service = setup_inventory(num_slots=20000, num_products=10000)

    # OLD IMPLEMENTATION
    def list_catalog_old() -> tuple[tuple[Product, Slot], ...]:
        catalog: list[tuple[Product, Slot]] = []
        for slot in service.list_slots():
            product = service._products.get(slot.product_id.value)
            if product is None:
                continue
            catalog.append((product, slot))
        return tuple(catalog)

    # NEW IMPLEMENTATION
    def list_catalog_new() -> tuple[tuple[Product, Slot], ...]:
        # Direct iteration on the service dictionary
        catalog: list[tuple[Product, Slot]] = []
        for slot in service._slots.values():
            product = service._products.get(slot.product_id.value)
            if product is None:
                continue
            catalog.append((product, slot))

        # Sort by slot_id to ensure predictable ordering
        catalog.sort(key=lambda item: item[1].slot_id.value)
        return tuple(catalog)


    iterations = 50

    # Benchmark old
    # Warm up
    list_catalog_old()
    start_time_old = time.perf_counter()
    for _ in range(iterations):
        list_catalog_old()
    end_time_old = time.perf_counter()
    avg_old = (end_time_old - start_time_old) / iterations

    # Benchmark new
    # Warm up
    list_catalog_new()
    start_time_new = time.perf_counter()
    for _ in range(iterations):
        list_catalog_new()
    end_time_new = time.perf_counter()
    avg_new = (end_time_new - start_time_new) / iterations

    print(f"Old implementation: {avg_old:.4f}s avg per call")
    print(f"New implementation: {avg_new:.4f}s avg per call")
    print(f"Speedup: {avg_old / avg_new:.2f}x")

if __name__ == "__main__":
    benchmark()

import timeit
import sys
import os

# Ensure the src directory is in the python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../src')))

from flower_vending.app.services.inventory_service import InventoryService
from flower_vending.domain.entities import Product, Slot
from flower_vending.domain.value_objects.product_id import ProductId
from flower_vending.domain.value_objects.slot_id import SlotId
from flower_vending.domain.value_objects.amount import Amount

def generate_inventory(num_items):
    products = {}
    slots = {}
    for i in range(num_items):
        pid_val = f"prod_{i:06d}"
        sid_val = f"slot_{num_items - i:06d}" # Inverse order to ensure sorting has work to do

        pid = ProductId(pid_val)
        sid = SlotId(sid_val)

        p = Product(
            product_id=pid,
            name=f"Product {i}",
            display_name=f"Product {i}",
            category="category",
            price=Amount(1000)
        )
        s = Slot(slot_id=sid, product_id=pid, capacity=10, quantity=10)

        products[pid_val] = p
        slots[sid_val] = s

    return products, slots

def benchmark_list_catalog():
    num_items = 10000
    print(f"Generating inventory with {num_items} items...")
    products, slots = generate_inventory(num_items)
    service = InventoryService(products=products, slots=slots)

    print("Running benchmark...")

    # Warmup
    service.list_catalog()

    # Benchmark
    num_runs = 50
    timer = timeit.Timer(lambda: service.list_catalog())

    time_taken = timer.timeit(number=num_runs)
    avg_time = time_taken / num_runs

    print(f"Total time for {num_runs} runs: {time_taken:.4f} seconds")
    print(f"Average time per run: {avg_time:.6f} seconds")
    return avg_time

if __name__ == '__main__':
    benchmark_list_catalog()

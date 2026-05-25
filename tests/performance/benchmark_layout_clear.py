import sys
import time

import os
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QPushButton

def clear_with_reversed_range(layout):
    for i in reversed(range(layout.count())):
        item = layout.takeAt(i)
        if item is not None and item.widget() is not None:
            item.widget().deleteLater()

def clear_with_walrus(layout):
    while (item := layout.takeAt(0)) is not None:
        if w := item.widget():
            w.deleteLater()

def run_benchmark(clear_func, iterations=10, widgets_per_iteration=1000):
    app = QApplication.instance() or QApplication(sys.argv)

    total_time = 0


    for _ in range(iterations):
        # Setup
        widget = QWidget()
        layout = QVBoxLayout(widget)
        for _ in range(widgets_per_iteration):
            layout.addWidget(QPushButton("Test"))

        # Ensure layout is fully populated
        app.processEvents()

        # Measure clearing
        start_time = time.perf_counter()
        clear_func(layout)
        # Process events to actually run deleteLater
        app.processEvents()
        end_time = time.perf_counter()

        total_time += (end_time - start_time)

        # Cleanup
        widget.deleteLater()
        app.processEvents()

    return total_time / iterations

def main():
    print(f"Benchmarking UI Layout Clearing (10 iterations, 5000 widgets each)...")

    # Warmup
    app = QApplication.instance() or QApplication(sys.argv)

    old_time = run_benchmark(clear_with_reversed_range, iterations=10, widgets_per_iteration=5000)
    print(f"Old approach (reversed range): {old_time:.6f} seconds per iteration")

    new_time = run_benchmark(clear_with_walrus, iterations=10, widgets_per_iteration=5000)
    print(f"New approach (walrus): {new_time:.6f} seconds per iteration")

    if new_time < old_time:
        improvement = ((old_time - new_time) / old_time) * 100
        print(f"Improvement: {improvement:.2f}% faster")
    else:
        improvement = ((new_time - old_time) / new_time) * 100
        print(f"Regression: {improvement:.2f}% slower")

if __name__ == '__main__':
    main()

## 2026-05-25 - O(N^2) Layout Clearance in PySide6
**Learning:** Calling `layout.takeAt(0)` in a loop causes PySide6 to shift remaining elements every iteration, leading to O(N^2) complexity.
**Action:** Always use reverse iteration `for i in reversed(range(layout.count())): item = layout.takeAt(i)` when clearing layouts in PySide6.

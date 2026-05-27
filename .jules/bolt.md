## 2026-05-25 - O(N^2) Layout Clearance in PySide6
**Learning:** Calling `layout.takeAt(0)` in a loop causes PySide6 to shift remaining elements every iteration, leading to O(N^2) complexity.
**Action:** Always use reverse iteration `for i in reversed(range(layout.count())): item = layout.takeAt(i)` when clearing layouts in PySide6.
## 2026-05-25 - Avoid Recreating Widgets on Resize in PySide6
**Learning:** Calling relayout/recreation functions (like `self._relayout_grid()`) on every `resizeEvent()` triggers severe UI stuttering and CPU spikes because it destroys and reconstructs DOM/widget elements constantly during the resize. Additionally, repeatedly performing expensive `QPixmap` scaling and rounding operations without memoization worsens the performance.
**Action:** Let the layout manager handle widget resizing. If specific elements need adjusting, reposition them directly using a `QTimer.singleShot(0, ...)` callback in `resizeEvent` without destroying them. Always memoize expensive `QPixmap` manipulations by checking if dimensions have changed before recalculating.

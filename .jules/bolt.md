## 2024-05-25 - Unnecessary Widget Recreation and Image Scaling in PySide6
**Learning:** PySide6 layouts (like `QGridLayout`) automatically handle resizing. Recreating all widgets and re-running expensive software image manipulation (pixmap rounding) on every `resizeEvent` causes massive UI stuttering and high CPU usage.
**Action:** Avoid calling relayout/widget creation methods from `resizeEvent`. Instead, only reposition/resize child elements as needed via `QTimer.singleShot()` and memoize expensive operations like `QPixmap` scaling/rounding based on widget width/height dimensions.

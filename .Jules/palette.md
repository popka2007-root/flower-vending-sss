## 2024-05-25 - PySide6 ARIA Equivalents
**Learning:** In PySide6 UI applications, the equivalent to HTML ARIA labels for icon-only buttons (like `QPushButton` without text) is the `setAccessibleName()` method. This is critical for screen reader compatibility.
**Action:** Always verify that buttons containing only an `icon()` call also receive a `setAccessibleName()` call to ensure keyboard and screen reader accessibility.

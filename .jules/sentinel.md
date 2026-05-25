## 2024-05-30 - Default PIN in configuration model
**Vulnerability:** Default service PIN ("0000") is set directly in `ServiceModeConfig` (`src/flower_vending/infrastructure/config/models.py`). This may allow unauthorized access if not overridden in production environments, despite the presence of an assertion `_validate_pin_not_default_in_production`.
**Learning:** Default secrets should not be baked into configuration models directly if they can grant administrative/service access, or at least they should be strongly prevented in production. The current validation might not be robust enough.
**Prevention:** Avoid default passwords. Make the PIN a required field without a default.

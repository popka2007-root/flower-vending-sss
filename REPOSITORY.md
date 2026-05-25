# Flower Vending System v0.2.0

## Simulator-First Control Platform for Premium Flower Vending Machines

---

## 1. SYSTEM ARCHITECTURE AND LAYER ISOLATION

### 1.1 Layer Map

```
┌──────────────────────────────────────────────────────────────┐
│                     UI LAYER (PySide6)                       │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────┐  │
│  │ KioskWindow │  │  ScreenWidgets │  │ TouchButton/      │  │
│  │ (QMainWin)  │  │  (Catalog,     │  │ ProductTile/      │  │
│  │             │  │   Payment,     │  │ ProcessingWidget  │  │
│  │             │  │   Delivery...) │  │                    │  │
│  └──────┬──────┘  └──────┬───────┘  └─────────┬──────────┘  │
│         │                │                    │              │
│  ┌──────┴────────────────┴────────────────────┴──────────┐  │
│  │                 KioskPresenter                         │  │
│  │    (Session state, navigation, ScreenRender dispatch)  │  │
│  └───────────────────────┬───────────────────────────────┘  │
└──────────────────────────┼──────────────────────────────────┘
                           │ async calls via asyncio
┌──────────────────────────┼──────────────────────────────────┐
│                APPLICATION FACADE                            │
│  ┌───────────────────────┴───────────────────────────────┐  │
│  │              UiApplicationFacade                       │  │
│  │  (Catalog queries, purchase commands, diagnostics,     │  │
│  │   theme control, idle timeout touch)                   │  │
│  └───────────────────────┬───────────────────────────────┘  │
└──────────────────────────┼──────────────────────────────────┘
                           │
┌──────────────────────────┼──────────────────────────────────┐
│                 APPLICATION CORE                             │
│  ┌───────────────────────┴───────────────────────────────┐  │
│  │                  ApplicationCore                       │  │
│  │  ┌──────────┐  ┌───────────┐  ┌────────────────────┐  │  │
│  │  │ CommandBus│  │ EventBus  │  │ StateMachineEngine │  │  │
│  │  └─────┬─────┘  └─────┬─────┘  └─────────┬──────────┘  │  │
│  │        │              │                  │              │  │
│  │  ┌─────┴──────────────┴──────────────────┴──────────┐  │  │
│  │  │                 Orchestrators                     │  │  │
│  │  │  VendingController    PaymentCoordinator          │  │  │
│  │  │  TransactionCoordinator  RecoveryManager         │  │  │
│  │  │  PickupTimeoutCoord.  IdleTimeoutCoord.          │  │  │
│  │  │  ServiceModeCoord.    HealthMonitor              │  │  │
│  │  └───────────────────────┬──────────────────────────┘  │  │
│  └──────────────────────────┼─────────────────────────────┘  │
└──────────────────────────────┼───────────────────────────────┘
                               │
┌──────────────────────────────┼───────────────────────────────┐
│                      DOMAIN CORE                              │
│  ┌───────────────────────────┴─────────────────────────────┐  │
│  │  Entities         Value Objects       Aggregates         │  │
│  │  Transaction      TransactionId       MachineRuntime     │  │
│  │  Product          ProductId           PurchaseTrans...   │  │
│  │  Slot             SlotId                                 │  │
│  │  MoneyInventory   Amount / Currency                      │  │
│  │                   CorrelationId                          │  │
│  ├─────────────────────────────────────────────────────────┤  │
│  │  Domain Events         Domain Commands    Exceptions     │  │
│  │  payment_event()       StartPurchase      SaleBlocked    │  │
│  │  vending_event()       CancelPurchase     InvariantViol. │  │
│  │  machine_event()       ConfirmPickup      ChangeUnavail. │  │
│  │  device_event()        EnterServiceMode   ProductUnavail.│  │
│  └─────────────────────────────────────────────────────────┘  │
└──────────────────────────────┬───────────────────────────────┘
                               │
┌──────────────────────────────┼───────────────────────────────┐
│                    INFRASTRUCTURE                              │
│  ┌───────────────────────────┴─────────────────────────────┐  │
│  │  SQLiteDatabase   Repositories   SQLiteTransactionJournal│  │
│  │  (WAL, FULL sync) (Product,Slot, (intent/outcome/event) │  │
│  │                    Transaction,                           │  │
│  │                    MachineStatus,                         │  │
│  │                    MoneyInventory)                        │  │
│  ├─────────────────────────────────────────────────────────┤  │
│  │  Config (Pydantic)    Logging (QueueHandler + JSONL)     │  │
│  │  AppConfig            JsonLogFormatter                   │  │
│  │  DevicesConfig        StructuredLoggerAdapter            │  │
│  │  PersistenceConfig    contextvars (correlation_id)       │  │
│  └─────────────────────────────────────────────────────────┘  │
└──────────────────────────────┬───────────────────────────────┘
                               │
┌──────────────────────────────┼───────────────────────────────┐
│                   DEVICES & INTEGRATION                       │
│  ┌───────────────────────────┴─────────────────────────────┐  │
│  │  HW Interfaces          Drivers              Simulators  │  │
│  │  BillValidator          DBV300SDValidator    MockBillVal.│  │
│  │  MotorController        ArduinoMotor         MockMotor   │  │
│  │  WindowController       ArduinoWindow        MockWindow  │  │
│  │  TemperatureSensor      ArduinoTemp          MockTemp    │  │
│  │  DoorSensor             ArduinoDoor          MockDoor    │  │
│  │  ChangeDispenser        (requires HW)        MockChange  │  │
│  │  WatchdogAdapter        (requires HW)        MockWatchdog│  │
│  ├─────────────────────────────────────────────────────────┤  │
│  │  Integration                                        │  │
│  │  OneCClient (HTTP)    TelemetryPublisher (HTTP)       │  │
│  └─────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

### 1.2 Clean Architecture Compliance

Dependency direction: **UI → Application → Domain ← Infrastructure**

```
UI (PySide6)           Infrastructure (SQLite, serial, logging)
      │                          │
      ▼                          ▼
Application Facade ──▶ Application Core ◀── Repositories, Journal, Config
                              │
                              ▼
                         Domain Core
                    (zero external imports)
```

**Inversion of Control mechanisms:**

| Boundary | Mechanism | File |
|----------|-----------|------|
| Domain ↔ Infrastructure | `ApplicationJournal` Protocol | `app/journal.py` |
| Domain ↔ Infrastructure | `ApplicationLogger` Protocol | `app/logging.py` |
| Application ↔ Devices | `BillValidator`, `MotorController`, etc. ABCs | `devices/interfaces/__init__.py` |
| Application ↔ UI | `UiApplicationFacade` (no Qt imports) | `ui/facade.py` |
| Application ↔ 1C | `OneCClient` (pluggable `_HttpTransport` Protocol) | `integration/1c/__init__.py` |

**Domain Core isolation rules:**
- Zero imports from `PySide6`, `sqlite3`, `pyserial`, `yaml`, `pydantic`, `logging`
- All domain entities are `@dataclass(slots=True)` — no framework coupling
- Domain events are plain dataclasses, serializable to JSON
- Domain commands are plain dataclasses, dispatched through `CommandBus`
- Exceptions are a pure hierarchy with `user_message` for human-readable error display

---

## 2. FSM SPECIFICATION AND EVENT TOPOLOGY

### 2.1 State Matrix

The machine operates with a 21-state Finite State Machine enforced by `StateMachineEngine` (`app/fsm/machine_fsm.py`).

| State | Entry Condition | Valid Incoming Events | Target States |
|-------|----------------|----------------------|---------------|
| **BOOT** | System start | — | SELF_TEST, FAULT |
| **SELF_TEST** | After BOOT | — | IDLE, RECOVERY_PENDING, OUT_OF_SERVICE, FAULT |
| **IDLE** | Self-test complete | `purchase_started`, `service_mode_requested` | PRODUCT_SELECTED, SERVICE_MODE, OUT_OF_SERVICE, FAULT |
| **PRODUCT_SELECTED** | User taps product tile | `product_selected` | CHECKING_AVAILABILITY, CANCELLED, FAULT |
| **CHECKING_AVAILABILITY** | Inventory check | `availability_confirmed` | CHECKING_CHANGE, CANCELLED, OUT_OF_SERVICE, FAULT |
| **CHECKING_CHANGE** | Change assessment | `change_assessed` | WAITING_FOR_PAYMENT, CANCELLED, OUT_OF_SERVICE |
| **WAITING_FOR_PAYMENT** | Change OK, waiting for cash | `cash_session_started` | ACCEPTING_CASH, CANCELLED, FAULT, OUT_OF_SERVICE |
| **ACCEPTING_CASH** | Validator enabled | `bill_stacked`, `payment_complete` | PAYMENT_ACCEPTED, CANCELLED, FAULT, OUT_OF_SERVICE, RECOVERY_PENDING, REFUND |
| **PAYMENT_ACCEPTED** | Payment ≥ price | `vend_authorized` | DISPENSING_CHANGE, DISPENSING_PRODUCT, FAULT, RECOVERY_PENDING |
| **DISPENSING_CHANGE** | Change due > 0 | `change_dispensed` | DISPENSING_PRODUCT, FAULT, RECOVERY_PENDING |
| **DISPENSING_PRODUCT** | Motor vend authorized | `product_dispensed` | OPENING_DELIVERY_WINDOW, FAULT, RECOVERY_PENDING, REFUND |
| **OPENING_DELIVERY_WINDOW** | Product dispensed | `delivery_window_opened` | WAITING_FOR_CUSTOMER_PICKUP, FAULT, RECOVERY_PENDING |
| **WAITING_FOR_CUSTOMER_PICKUP** | Window open | `pickup_confirmed`, `pickup_timeout_elapsed` | CLOSING_DELIVERY_WINDOW, FAULT, RECOVERY_PENDING |
| **CLOSING_DELIVERY_WINDOW** | Pickup confirmed or timeout | `delivery_window_closed` | COMPLETED, FAULT, RECOVERY_PENDING |
| **COMPLETED** | Window closed, TX complete | `transaction_completed` | IDLE, OUT_OF_SERVICE |
| **CANCELLED** | User cancelled | `transaction_cancelled` | IDLE, OUT_OF_SERVICE, REFUND |
| **REFUND** | Refund in progress | `refund_dispensed` / `refund_failed` | CANCELLED, MANUAL_REVIEW, FAULT, RECOVERY_PENDING |
| **OUT_OF_SERVICE** | Critical device fault or temp | `health_restored` | SERVICE_MODE, IDLE, RECOVERY_PENDING |
| **FAULT** | Any hardware fault | `fault_cleared` | IDLE, OUT_OF_SERVICE, SERVICE_MODE, RECOVERY_PENDING |
| **SERVICE_MODE** | Operator PIN entered | `service_mode_exited` | OUT_OF_SERVICE, IDLE, FAULT, RECOVERY_PENDING |
| **MANUAL_REVIEW** | Operator review required | `recovery_completed` | IDLE, OUT_OF_SERVICE, FAULT, SERVICE_MODE, RECOVERY_PENDING |
| **RECOVERY_PENDING** | Unresolved intents on boot | `recovery_completed` / `unresolved_intent_detected` | IDLE, OUT_OF_SERVICE, FAULT, SERVICE_MODE |

### 2.2 EventBus Topology

**Critical subscriptions** (failure propagates to caller):

| Event | Handler | Effect |
|-------|---------|--------|
| `vend_authorized` | `VendingController.handle_vend_authorized` | Dispense product, open window |
| `transaction_completed` | `RuntimePersistenceProjector.handle_domain_event` | Persist TX + inventory + status |
| `transaction_cancelled` | `RuntimePersistenceProjector.handle_domain_event` | Persist cancelled TX |
| `payment_confirmed` | `RuntimePersistenceProjector.handle_domain_event` | Persist payment |
| `machine_faulted` | `RuntimePersistenceProjector.handle_domain_event` | Log fault |
| `product_dispensed` | `RuntimePersistenceProjector.handle_domain_event` | Persist dispense |
| *(plus 10 other persistence events)* | | |

**Best-effort subscriptions** (failure logged, chain continues):

| Event | Handler | Effect |
|-------|---------|--------|
| `*` (all events) | `KioskPresenter.handle_domain_event` | Update UI session state |
| `*` (all events) | `RecentEventStore.handle` | Buffer recent events |
| `delivery_window_opened` | `PickupTimeoutCoordinator` | Arm pickup deadline |
| `pickup_confirmed` | `PickupTimeoutCoordinator` | Cancel deadline |
| `transaction_completed` | `PickupTimeoutCoordinator` | Cancel deadline |
| `transaction_cancelled` | `PickupTimeoutCoordinator` | Cancel deadline |

### 2.3 Edge Case Handling

**Cancel during cash acceptance:**

```
ACCEPTING_CASH state:
  ┌─ User taps "Cancel" ──▶ PaymentCoordinator.cancel_purchase()
  │                           ├── validator.disable_acceptance()
  │                           ├── Transaction._cancelled = True
  │                           └── FSM → CANCELLED → IDLE (force_state)
  │
  ├─ Bill stacked event arrives:
  │   process_validator_event() checks Transaction._cancelled
  │   → if True: ignore event (InvariantViolationError suppressed)
  │
  └─ If payment completed before cancel processed:
      cancel_purchase() checks payment_status != CONFIRMED
      → if already confirmed: refund via change_dispenser
```

**Idle Timeout:**

```
IdleTimeoutCoordinator (120s default):
  Every ~12s: poll_once()
    if now - last_activity_at > 120s AND active TX in cancelable state:
      → PaymentCoordinator.cancel_purchase()
      → FSM force_state(IDLE, "idle_timeout_cancelled")

  UI touch points reset timer:
    KioskPresenter._touch() on every user action:
      select_product, start_checkout, cancel_purchase,
      confirm_pickup, show_pin_screen, back, handle_action
```

**Recovery on restart:**

```
Boot sequence:
  1. SQLite: load unresolved transactions from DB
  2. SQLiteTransactionJournal: detect unresolved intents
  3. RecoveryManager.detect_unresolved_intents()
     ├── classify_intent("motor_vend_requested") → manual_review_required
     ├── classify_intent("window_open_requested") → manual_review_required
     ├── classify_intent("change_dispense_requested") → manual_review_required
     ├── classify_intent("inventory_decrement") → manual_review_required
     └── classify_intent("acceptance_disable_requested") → cancel_safe
  4. FSM → RECOVERY_PENDING, block sales
  5. Operator must enter service mode → recover or clear
```

---

## 3. HARDWARE PROTOCOLS AND FAULT TOLERANCE

### 3.1 ESP32 Arduino Firmware Protocol

**Transport:** UART via USB (pyserial), 115200 baud, 8N1, `\n`-terminated ASCII

**Commands:**

| Command | Response | Description |
|---------|----------|-------------|
| `DOOR_OPEN` | `OK` | Pulse delivery door relay open |
| `DOOR_CLOSE` | `OK` | Pulse delivery door relay closed |
| `MOTOR_ON` | `OK` | Enable drum motor relay |
| `MOTOR_OFF` | `OK` | Disable drum motor relay |
| `VEND_SLOT N` | `OK` / `ERR` | Rotate to slot N (1-6), open/close door |
| `STATUS` | `OK DOOR=... MOTOR=... BUTTON=... DRUM=N HOME=N TEMP=C` | Full status |
| `HOME` | `OK` / `ERR HOMING_FAILED` | Rotate drum to home position |
| `TEMP` | `OK TEMP=<celsius>` | Read DS18B20 temperature |
| `COOL_ON` | `OK` | Enable cooling relay |
| `COOL_OFF` | `OK` | Disable cooling relay |
| `PINO N [ms]` | `OK` | Pulse relay N for ms milliseconds |
| `INFO` | `OK ESP32_VENDING FIRMWARE v2.0` | Identify firmware |
| `ALL_OFF` | `OK` | Disable all relays |
| `ENC_CALIBRATE` | `OK` | Set current drum position as home |

**Error codes:** `ERR UNKNOWN_CMD`, `ERR HOMING_FAILED`, `ERR RANGE`

**Python-side adapter:** `ArduinoSerialTransport` writes command string, reads response line.
All commands wrapped in `DeviceCommandRunner` for timeout/retry/idempotency.

### 3.2 DBV-300-SD Bill Validator Protocol (JCM Serial)

**Transport:** UART via USB (pyserial), 9600 baud, 8N1

**Frame format:**
```
STX(0x02) LEN CMD [DATA...] XOR_CKSUM ETX(0x03)
```

**Commands:**

| Command | Code | Description |
|---------|------|-------------|
| POLL | 0x01 | Poll device status |
| GET_DENOM_TABLE | 0x03 | Request denomination table |
| SET_ACCEPTANCE | 0x08 | Enable/disable bill acceptance (data: 0x01/0x00) |
| STACK_ESCROW | 0x0C | Accept escrowed bill into cashbox |
| RETURN_ESCROW | 0x0D | Return escrowed bill |

**Response codes:**

| Code | Name | Domain Event |
|------|------|-------------|
| 0x00 | ACK | (none) |
| 0x80 | BILL_INSERTED | `BILL_DETECTED` |
| 0x81 | BILL_VALIDATED | `BILL_VALIDATED` |
| 0x82 | BILL_REJECTED | `BILL_REJECTED` |
| 0x83 | BILL_STACKED | `BILL_STACKED` |
| 0x84 | ESCROW_POSITION | `ESCROW_AVAILABLE` |
| 0x85 | BILL_RETURNED | `BILL_RETURNED` |
| 0x86 | STACKER_FULL | `VALIDATOR_FAULT` |
| 0x87 | BILL_JAM | `VALIDATOR_FAULT` |
| 0x90 | POWER_UP | (none) |
| 0xF0 | COMMAND_TIMEOUT | `VALIDATOR_FAULT` |
| 0xF1 | COMMAND_ERROR | `VALIDATOR_FAULT` |

**Adapter:** `DBV300SDValidator` runs an async poll loop (`_poll_loop`) at `poll_interval_s` (default 0.2s).
Fault backoff: exponential 2^n up to 30s after consecutive faults.
Events are enqueued to `asyncio.Queue` and consumed by `ApplicationCore._validator_event_loop()`.
All protocol frames go through `ProtocolTraceRecorder` for bench analysis.

### 3.3 COM-Port Loss Recovery

```
Device command failure path:
  1. serial.SerialException on write/read
  2. DeviceCommandRunner catches and classifies:
     ├── TimeoutError → retry up to policy.retry_count
     ├── DeviceAdapterError → terminal fault
     └── DeviceCommandError with non-retryable code → terminal fault
  3. On terminal fault:
     ├── Adapter sets health = FAULT
     ├── ValidatorAdapter disables acceptance (fallback_disable_on_fault)
     ├── EventBus publishes VALIDATOR_FAULT event
     └── PaymentCoordinator.process_validator_event():
         transaction.mark_faulted()
         FSM → FAULT
         block_sales("validator_fault")

Recovery on port reconnect:
  1. HealthMonitor.poll_once() detects device state via get_health()
  2. If state transitions from FAULT → READY:
     ├── unblock_sales("validator_fault")
     └── FSM transitions FAULT → IDLE (via force_state)
  3. Adapter.start() re-opens serial port, re-sends init sequence
```

---

## 4. MULTITHREADING AND TOUCH ERGONOMICS

### 4.1 Thread Model

```
┌──────────────────────────────────────────────────┐
│              MAIN THREAD (Qt Event Loop)          │
│  QApplication.exec()                             │
│  - Widget rendering, event handling              │
│  - KioskPresenter method calls (via _run_async)  │
│  - QPropertyAnimation for crossfade transitions  │
│  - QTimer for theme auto-switching               │
└──────────────┬───────────────────────────────────┘
               │ asyncio.create_task()
┌──────────────┴───────────────────────────────────┐
│           ASYNCIO EVENT LOOP (same thread)        │
│  ApplicationCore background tasks:               │
│  - _validator_event_loop (50ms poll)             │
│  - _health_monitor_loop (500ms poll)             │
│  - _pickup_timeout_loop (250ms poll)             │
│  - _idle_timeout_loop (12s poll)                 │
│  - CommandBus.dispatch() → orchestrators         │
│  - EventBus.publish() → all subscribers          │
└──────────────┬───────────────────────────────────┘
               │ queue.Queue
┌──────────────┴───────────────────────────────────┐
│         LOGGING THREAD (QueueListener)            │
│  - JsonLogFormatter.format() + rotate            │
│  - RotatingFileHandler writes to .jsonl          │
│  - StreamHandler writes to stderr                │
│  - Isolated from main thread via QueueHandler    │
└──────────────────────────────────────────────────┘
```

**Key design decisions:**
- UI never blocked: all application calls are `async`, dispatched via `asyncio.create_task()` from Qt signals
- Logging never blocks: `QueueHandler` → `QueueListener` in dedicated thread
- SQLite: single-threaded access from asyncio event loop, verified by `_verify_thread_safety()`
- `QLock` (reentrant) on SQLite connection for intra-thread safety
- Context variables (`contextvars`) carry `correlation_id`/`transaction_id` through all async calls

### 4.2 Touch Debounce and Visual Feedback

**Double-tap prevention (`_TAP_DEBOUNCE_MS = 500`):**

```
TouchButton.mouseReleaseEvent():
  current_ms = time.monotonic() * 1000
  if current_ms - last_release_ms < 500ms:
    setDown(False)   # visually reset
    event.accept()   # suppress synthetic event
    return
  last_release_ms = current_ms
  super().mouseReleaseEvent(event)  # normal click
```

**QTouchEvent handling (prevents synthesized MouseEvent duplicates):**

```
TouchButton.event():
  TouchBegin → _touch_active = True
  TouchEnd   → if _touch_active:
                 emit click(), set down = False
                 return True (consume event)
  TouchCancel → _touch_active = False

TouchButton.mousePressEvent():
  if _touch_active: return  # suppress synthesized mouse event
```

**ProductTile pressed feedback:**

```
CSS: QFrame#ProductTile[pressed="true"] {
  background: #f0e8d8;       // 8-10% darkening (previously 2%)
  border: 2px solid #b8a080;
}
// margin-top: 2px REMOVED — caused layout recalc jank
```

**Screen transitions:**

```
KioskMainWindow._transition_to(widget):
  1. QStackedWidget.setCurrentWidget(new_widget)
  2. QGraphicsOpacityEffect on new widget, opacity = 0.0
  3. QPropertyAnimation opacity 0.0 → 1.0, 200ms, OutCubic
  4. On finish: widget.setGraphicsEffect(None)  // restore native rendering
```

---

## 5. PERSISTENCE, TELEMETRY, AND SECURITY

### 5.1 SQLite Schema and Transactionality

**Pragmas:** `journal_mode=WAL`, `synchronous=FULL`, `foreign_keys=ON`, `busy_timeout=5000`

**Tables:**

| Table | Purpose | Key columns |
|-------|---------|-------------|
| `products` | Catalog seed data | product_id, price_minor_units, enabled |
| `slots` | Slot inventory | slot_id, quantity, capacity, is_enabled |
| `transactions` | All sales | transaction_id, status, accepted_minor_units, payment/payout/dispense/delivery/recovery_status |
| `transaction_journal` | Intent/outcome/event log | transaction_id, entry_kind, entry_name, idempotency_key |
| `machine_status_projection` | Runtime status singleton | machine_id, machine_state, sale_blockers_json |
| `money_inventory` | Cash accounting | inventory_id, accounting_counts_json, reserved_counts_json, drift_detected |
| `device_fault_log` | Device faults | device_name, fault_code, acknowledged |
| `service_events` | Operator audit | event_type, operator_id |
| `temperature_events` | Chamber readings | sensor_name, celsius |
| `device_settings` | Runtime device config | logical_device_name, config_json |
| `applied_config` | Config snapshot | yaml_text, config_hash |

**Atomicity guarantees:**

```
VendingController.handle_vend_authorized():
  1. Journal: record_intent("motor_vend_requested")   ─┐
  2. motor_controller.vend_slot()                      │ atomic group
  3. Journal: record_outcome("motor_vend_requested")   ─┘
  4. Journal: record_intent("inventory_decrement")     ─┐
  5. inventory_service.mark_vended()                   │ atomic group
  6. Journal: record_outcome("inventory_decrement")    ─┘
  7. transaction.mark_product_dispensed()
  8. FSM → OPENING_DELIVERY_WINDOW

If power loss between step 3 and 4:
  RecoveryManager detects motor_vend_requested intent WITH outcome
  → motor vend SUCCEEDED, proceed to inventory check

If power loss between step 4 and 5:
  RecoveryManager detects inventory_decrement intent WITHOUT outcome
  → classify_intent("inventory_decrement") = manual_review_required
  → block sales, operator must verify slot physically
```

**Runtime snapshot persistence:**
```
_persist_runtime_snapshot():
  SQLiteDatabase.transaction() as connection:
    machine_status.save(status, _connection=connection)
    money_inventory.save(inventory, _connection=connection)
    for tx in unresolved_transactions:
      transactions.save(tx, _connection=connection)
  → single COMMIT or full ROLLBACK
```

### 5.2 Structured Logging

**Format:** JSON Lines (`.jsonl`), one JSON object per line

**Example log entry (production):**

```json
{
  "correlation_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "event_type": "payment_confirmed",
  "level": "INFO",
  "logger": "flower_vending",
  "machine_state": "PAYMENT_ACCEPTED",
  "message": "domain_event",
  "payload": {
    "accepted_minor_units": "***",
    "change_due_minor_units": "***"
  },
  "timestamp": "2026-05-21T20:23:38",
  "transaction_id": "b4c9d7d7-90c6-45b6-a8e9-9d932a92cefa"
}
```

**Sensitive field masking:** Configured in `logging.sensitive_fields`:
```yaml
sensitive_fields:
  - bill_minor_units
  - price_minor_units
  - accepted_minor_units
  - change_due_minor_units
  - refund_minor_units
```
Masked values replaced with `"***"` in `JsonLogFormatter.format()`.

**Context propagation:**
```python
# In RuntimePersistenceProjector.handle_domain_event():
set_log_context(correlation_id=event.correlation_id, transaction_id=event.transaction_id)
self._logger.info("domain_event", extra={...})
# correlation_id and transaction_id are read from contextvars in
# StructuredLoggerAdapter.process() — no new adapter objects created
```

### 5.3 Security

**Service PIN:**
- Stored as SHA-256 hash in `ServiceModeCoordinator._service_pin_hash`
- Compared: `hashlib.sha256(command.pin.encode()).hexdigest() != stored_hash`
- Rate limit: 5 failed attempts → 30-second lockout (`ServiceModeLockedError`)
- PIN sourced from config file: `machine.service_mode.pin`
- UI widgets do not store the correct PIN; they collect input and pass to coordinator

**1C credentials:**
- `FLOWER_VENDING_1C_PASSWORD` environment variable (not in YAML)
- `username`/`password` fields in `OneCConfig` default to empty strings
- Basic auth header via `base64` encoding

**Applied config storage:**
- `applied_config` table stores SHA-256 hash of YAML, not plaintext credentials
- Config snapshots kept for audit trail

---

## 6. DEPLOYMENT AND DEVELOPMENT TOOLS

### 6.1 Makefile Commands

| Command | Effect |
|---------|--------|
| `make install` | Install core dependencies from `requirements.txt` |
| `make install-dev` | Core + dev tools (pytest, mypy, ruff, pre-commit) |
| `make install-ui` | Core + PySide6 |
| `make install-serial` | Core + pyserial |
| `make install-all` | Everything: `pip install -e ".[dev,ui,serial]"` |
| `make check` | `lint` + `typecheck` + `test` — full pre-commit gate |
| `make lint` | `ruff check .` + `ruff format --check .` |
| `make lint-fix` | `ruff check --fix .` + `ruff format .` |
| `make typecheck` | `mypy src tests` — strict typing |
| `make test` | `pytest -v` — all tests (105 unit/integration/recovery) |
| `make test-e2e` | `pytest tests/e2e/ -v` — kiosk flow tests |
| `make test-coverage` | `pytest --cov=src --cov-report=term --cov-report=html` |
| `make verify` | `python scripts/verify_project.py` — config validation, smoke tests |
| `make clean` | Remove `build/`, `dist/`, `artifacts/`, `var/`, caches |
| `make pre-commit` | Run all pre-commit hooks on all files |
| `make setup` | Full dev setup: install + pre-commit + verify |
| `make build-windows-portable` | `python packaging/build_release.py windows-portable` → `.exe` |
| `make build-windows-installer` | Inno Setup installer |
| `make build-linux-appimage` | Linux AppImage |
| `make build-all` | All three build targets |

### 6.2 CLI Diagnostics

```
# Validate configuration
python -m flower_vending validate-config --config config/examples/machine.simulator.yaml

# Run simulator without UI
python -m flower_vending simulator-runtime --config config/examples/machine.simulator.yaml

# Launch kiosk UI
python -m flower_vending simulator-ui --config config/examples/machine.simulator.yaml

# Read persisted status from SQLite
python -m flower_vending status --config config/examples/machine.simulator.yaml

# Read recent events
python -m flower_vending events --config config/examples/machine.simulator.yaml

# Diagnose machine state (requires running runtime)
python -m flower_vending diagnostics --config config/examples/machine.simulator.yaml

# Enter service mode and get snapshot
python -m flower_vending service --config config/examples/machine.simulator.yaml --operator technician

# DBV-300-SD serial smoke test
python -m flower_vending dbv300sd-serial-smoke --port COM3

# DBV-300-SD protocol auto-detect
python -m flower_vending dbv300sd-analyze --port COM3

# Discover COM ports and connected hardware
python -m flower_vending discover

# Clear money inventory drift
python -m flower_vending clear-drift --config config/examples/machine.simulator.yaml

# Start production runtime with real hardware
python -m flower_vending run --config config/machine.production.yaml

# Print a test receipt
python -m flower_vending printer-test
```

### 6.3 Directory Structure

```
flower-vending-system/
├── config/                     # YAML configuration files
│   ├── examples/               # machine.simulator.yaml, machine.windows.yaml, machine.linux.yaml
│   ├── targets/                # machine.debian13-target.yaml
│   └── machine.production.yaml
├── firmware/                   # ESP32 Arduino firmware
│   └── esp32_vending/esp32_vending.ino
├── src/flower_vending/         # Python source
│   ├── app/                    # Application core (FSM, orchestrators, buses, services)
│   ├── domain/                 # Domain entities, value objects, aggregates, events, commands
│   ├── devices/                # Hardware interfaces, DBV-300-SD adapter, Arduino drivers
│   ├── simulators/             # Mock devices, fault injection, harness
│   ├── infrastructure/         # SQLite persistence, config (Pydantic), logging
│   ├── ui/                     # PySide6 kiosk UI (views, presenters, widgets, theme)
│   ├── integration/            # 1C client, telemetry publisher
│   ├── platform/               # OS abstraction (Windows/Linux extension points)
│   ├── payments/               # Change management
│   └── runtime/                # Bootstrap, CLI, production environment
├── tests/                      # 105 tests
│   ├── unit/                   # 9 files (change manager, config, DB migrations, DBV, policy, recovery, UI)
│   ├── integration/            # 6 files (cash flows, event bus, observability, pickup, runtime, scenarios)
│   ├── recovery/               # 2 files (persistence, crash windows)
│   ├── e2e/                    # 1 file (kiosk flows)
│   └── load_test.py            # Concurrent operation tests
├── scripts/                    # Build, verification, utility
├── packaging/                  # PyInstaller, Inno Setup, AppImage
├── docs/hardware/              # Bench validation checklists
├── Makefile
├── pyproject.toml
├── requirements.txt
├── requirements-dev.txt
├── requirements-ui.txt
└── .gitignore
```

### 6.4 Version History

| Version | Changes |
|---------|---------|
| 0.1.5 | Initial production-like baseline |
| 0.2.0 | Service PIN hashing, race condition fixes, FSM deadlock fixes, atomicity guarantees, EventBus unsubscribe, idle timeout, async logging, contextvars, 1C client, telemetry publisher, log sanitization, power-loss simulator fault, UX improvements (touch debounce, crossfade, flower processing widget, ThankYou buy-again, warm dark theme, price badges), dead code elimination, test consolidation (130→105) |

# Flower Vending System — Hardware Integration Guide

**Назначение:** Передать полный контекст для реализации реальных аппаратных драйверов.
**Для кого:** Инженер/ИИ, подключающий физическое оборудование к существующей software-only платформе.
**Принцип:** Simulator-first — каждый новый hardware adapter подтверждается на bench-стенде до включения в production.

---

## 1. Что уже готово (не трогать)

### Software-ядро (100% готово, не требует изменений)

- Доменная модель: Product, Slot, Transaction, MoneyInventory, MachineStatus, DeviceHealthSnapshot
- FSM: 22 состояния, 50+ разрешённых переходов
- Оркестраторы: VendingController, PaymentCoordinator, TransactionCoordinator, RecoveryManager, HealthMonitor, PickupTimeoutCoordinator, ServiceModeCoordinator
- Шины: CommandBus (асинхронная диспетчеризация), EventBus (critical + best_effort)
- Персистентность: SQLite, 13 таблиц, 9 репозиториев, WAL, миграции
- UI: 15 экранов, PySide6, MVP (Facade + Presenter + ViewModel)
- CLI: 9 команд (`validate-config`, `diagnostics`, `status`, `events`, `service`, `simulator-runtime`, `simulator-ui`, `dbv300sd-serial-smoke`, `clear-drift`)
- CI/CD: GitHub Actions matrix (Linux + Windows), ruff + mypy strict, Makefile, pre-commit

### Device Layer (интерфейсы и адаптер DBV-300-SD готов, протокол — заглушка)

- Все ABC в `devices/interfaces/__init__.py`
- DeviceCommandRunner в `devices/command_policy.py` — полноценный runner с таймаутом, retry, idempotency, fault classification
- DBV300SDValidator в `devices/dbv300sd/adapter.py` — полный lifecycle (start/stop/poll/fault/event-queue)
- SerialDBV300Transport в `devices/dbv300sd/transport/serial_transport.py` — pyserial-based
- Но: `DeferredSerialProtocol`, `DeferredMDBProtocol`, `DeferredPulseProtocol` — **заглушки**, все методы кидают `HardwareConfirmationRequiredError`

---

## 2. Device Interfaces (ABCs) — что нужно реализовать

### 2.1 BillValidator (`devices/interfaces/__init__.py`)

```python
class BillValidator(ManagedDevice):
    async def enable_acceptance(self, correlation_id: str | None = None) -> None
    async def disable_acceptance(self, correlation_id: str | None = None) -> None
    async def accept_escrow(self, correlation_id: str | None = None) -> None   # опционально
    async def return_escrow(self, correlation_id: str | None = None) -> None    # опционально
    async def read_event(self, timeout_s: float | None = None) -> BillValidatorEvent | None
    def supports_escrow(self) -> bool
```

**BillValidatorEventType** (нормализованные события):
`BILL_DETECTED`, `BILL_VALIDATED`, `BILL_REJECTED`, `ESCROW_AVAILABLE`, `BILL_STACKED`, `BILL_RETURNED`, `VALIDATOR_FAULT`, `VALIDATOR_DISABLED`

### 2.2 ChangeDispenser

```python
class ChangeDispenser(ManagedDevice):
    async def can_dispense(self, request: ChangeDispenseRequest) -> bool
    async def dispense(self, request: ChangeDispenseRequest) -> ChangeDispenseResult
    async def get_accounting_inventory(self) -> Mapping[int, int]
```

**ChangeDispenseResult.status:** `DISPENSED`, `PARTIAL`, `FAILED`, `AMBIGUOUS`

### 2.3 MotorController

```python
class MotorController(ManagedDevice):
    async def home(self, correlation_id: str | None = None) -> None
    async def vend_slot(self, slot_id: str, correlation_id: str | None = None) -> None
    async def stop_motion(self) -> None
```

### 2.4 WindowController

```python
class WindowController(ManagedDevice):
    async def open_window(self, correlation_id: str | None = None) -> None
    async def close_window(self, correlation_id: str | None = None) -> None
    async def get_window_status(self) -> WindowStatus
```

**WindowPosition:** `UNKNOWN`, `OPEN`, `CLOSED`, `OPENING`, `CLOSING`

### 2.5 Остальные сенсоры

```python
class TemperatureSensor(ManagedDevice):
    async def read_temperature(self) -> TemperatureReading     # sensor_name, celsius

class DoorSensor(ManagedDevice):
    async def read_service_door(self) -> DoorStatus            # sensor_name, is_open

class InventorySensor(ManagedDevice):
    async def read_slot(self, slot_id: str) -> InventoryPresence  # has_product, confidence

class PositionSensor(ManagedDevice):
    async def read_position(self) -> PositionReading           # position_id, in_position, is_home

class WatchdogAdapter(ManagedDevice):
    async def arm(self, timeout_s: float) -> None
    async def kick(self) -> None
    async def disarm(self) -> None
```

### 2.6 ManagedDevice (базовый)

```python
class ManagedDevice(ABC):
    @property
    def name(self) -> str
    async def start(self) -> None
    async def stop(self) -> None
    async def get_health(self) -> DeviceHealth   # name, state, faults[], details{}
```

---

## 3. DBV-300-SD — полный стек

### 3.1 Архитектура

```
┌────────────────────────────────────────────────────┐
│              DBV300SDValidator (adapter.py)         │
│  - asyncio.Lock, poll_task, event_queue             │
│  - start()/stop() lifecycle                         │
│  - _poll_loop() с exponential backoff               │
│  - DeviceCommandRunner для enable/disable/escrow    │
│  - _handle_fault() → VALIDATOR_FAULT event         │
├────────────────────────────────────────────────────┤
│              DBV300Protocol (protocol/base.py)      │
│  - initialize(), shutdown(), poll()                 │
│  - set_acceptance_enabled(), stack_escrow()         │
│  - return_escrow()                                  │
│  - СЕЙЧАС: DeferredSerialProtocol — ЗАГЛУШКА       │
├────────────────────────────────────────────────────┤
│           DBV300Transport (transport/base.py)        │
│  - open(), close(), write(), read(), flush_input()  │
│  - СЕЙЧАС: SerialDBV300Transport (pyserial)         │
└────────────────────────────────────────────────────┘
```

### 3.2 Transport (готов, можно использовать)

`SerialDBV300Transport` в `devices/dbv300sd/transport/serial_transport.py`
- pyserial-based, все I/O через `asyncio.to_thread()`
- Настройка: port, baudrate, bytesize, parity, stopbits, read/write timeout
- Методы: `open()`, `close()`, `write(data)`, `read(size)`, `flush_input()`

### 3.3 Protocol (нужно реализовать)

`devices/dbv300sd/protocol/base.py` — ABC с методами:

```python
class DBV300Protocol(ABC):
    @property
    def name(self) -> str                  # например "jcm-dbv300-serial-v1"
    @property
    def capabilities(self) -> ProtocolCapabilities  # escrow_supported, polling_required, push_events_supported

    async def initialize(self, transport: DBV300Transport) -> None
    async def shutdown(self, transport: DBV300Transport) -> None
    async def set_acceptance_enabled(self, transport: DBV300Transport, enabled: bool) -> None
    async def poll(self, transport: DBV300Transport) -> Sequence[ValidatorProtocolEvent]
    async def stack_escrow(self, transport: DBV300Transport) -> None
    async def return_escrow(self, transport: DBV300Transport) -> None
```

**Что нужно сделать:**
1. Получить официальную документацию JCM DBV-300-SD (command frames, handshake, denomination mapping, event codes)
2. Определить режим работы: **Serial** (JCM-proprietary), **MDB** (multi-drop bus), или **Pulse**
3. Реализовать конкретный класс протокола (например, `JCMSerialDBV300Protocol`)
4. Обновить фабрику `_build_protocol()` в adapter.py
5. Проверить на стенде через `python -m flower_vending dbv300sd-serial-smoke --port COM3`

### 3.4 ProtocolTraceRecorder (уже готов)

`devices/dbv300sd/protocol/trace.py` — буферизированная запись rx/tx в JSONL.
Используется bench-командой для снятия трейсов с реального COM-порта.

### 3.5 Bench CLI (уже готов)

```bash
python -m flower_vending dbv300sd-serial-smoke --port COM3 --baudrate 9600 \
  --tx-hex "02 03 01 FF" --read-size 8 --trace-log var/log/dbv-trace.jsonl
```
Открывает порт, шлёт байты, читает ответ, пишет JSONL-трейс.

---

## 4. Configuration Models

### 4.1 AppConfig (полный YAML → Pydantic)

Файлы конфигурации:
- `config/examples/machine.simulator.yaml` — симулятор (работает без железа)
- `config/examples/machine.windows.yaml` — пример для Windows с hardware_confirmation_required
- `config/examples/machine.linux.yaml` — пример для Linux
- `config/targets/machine.debian13-target.yaml` — целевая конфигурация Debian 13

### 4.2 BillValidatorConfig (Pydantic, из `config/models.py`)

```yaml
bill_validator:
  enabled: true
  driver: "dbv300sd"
  device_name: "jcm_dbv300sd"
  requires_hardware_confirmation: true    # !!! флаг extension point
  transport_kind: "serial"                # serial | mdb | pulse
  protocol_kind: "serial"                 # serial | mdb | pulse
  poll_interval_s: 0.2
  startup_disable_acceptance: true
  fallback_disable_on_fault: true
  accepted_denominations_minor: [100, 500, 1000]
  policy:
    timeout_s: 1.0
    retry_count: 0
    retryable_faults: ["command_timeout", "transient_command_failure", "communication_error"]
    non_retryable_faults: ["ambiguous_physical_result", "physical_state_mismatch", ...]
    require_manual_review_on_ambiguous_result: true
  serial:
    port: "COM3"              # или "/dev/ttyUSB0" на Linux
    baudrate: 9600
    bytesize: 8
    parity: "N"
    stopbits: 1
    read_timeout_s: 0.2
    write_timeout_s: 0.2
```

### 4.3 GenericDeviceConfig (для остальных устройств)

```yaml
motor_controller:
  enabled: true
  driver: "mock"                          # заменить на реальный драйвер
  device_name: "vend_motor"
  requires_hardware_confirmation: true    # extension point
  policy:
    timeout_s: 2.0
    retry_count: 1
  # mapping, timeouts_ms, settings — настраивается под железо
```

### 4.4 DeviceCommandPolicyConfig

```yaml
policy:
  timeout_s: 1.0                          # таймаут команды (None = нет таймаута)
  retry_count: 0                          # количество повторных попыток
  retryable_faults: [...]                 # какие коды ошибок можно повторять
  non_retryable_faults: [...]             # какие коды ошибок НЕ повторять
  require_manual_review_on_ambiguous_result: true  # ручная проверка при неоднозначном результате
```

---

## 5. Как устройства встраиваются в runtime

### 5.1 ApplicationCore (`app/bootstrap.py`)

Функция `build_application_core()` принимает устройства через параметры:

```python
def build_application_core(
    *,
    validator: BillValidator,
    change_dispenser: ChangeDispenser,
    motor_controller: MotorController,
    window_controller: WindowController,
    inventory_service: InventoryService,
    money_inventory: MoneyInventory,
    devices: Mapping[str, ManagedDevice],     # все устройства для HealthMonitor
    door_sensor: DoorSensor | None = None,
    temperature_sensor: TemperatureSensor | None = None,
    inventory_sensor: InventorySensor | None = None,
    ...
) -> ApplicationCore
```

### 5.2 SimulatorRuntimeEnvironment (`runtime/bootstrap.py`)

Функция `build_simulator_environment()` — полный пример как создать среду:
1. Загрузить YAML-конфиг
2. Создать SQLite + репозитории
3. Создать mock-устройства через `_build_simulator_devices()`
4. Вызвать `build_application_core()`
5. Запустить RuntimePersistenceProjector + SimulatorControlService

Для production-запуска: заменить `_build_simulator_devices()` на фабрику, читающую `requires_hardware_confirmation` из конфига, и создающую реальные адаптеры.

### 5.3 Фабрика устройств (сейчас в `runtime/bootstrap.py:804-860`)

```python
def _build_simulator_devices(config, money_inventory) -> SimulatorDevices:
    # Сейчас создаёт MockXXX для каждого устройства.
    # Для реального железа: читать config.devices.*.driver и создавать нужный адаптер
    return SimulatorDevices(
        validator=MockBillValidator(...),
        change_dispenser=MockChangeDispenser(...),
        motor_controller=MockMotorController(...),
        ...
    )
```

**Задача:** Создать `_build_production_devices()`, которая по драйверу из конфига создаёт:
- `"dbv300sd"` → `build_dbv300sd_validator(config.devices.bill_validator)`
- `"mock"` → `MockBillValidator(...)` (для отладки)
- Другие драйверы — по аналогии

---

## 6. DeviceCommandRunner — политика выполнения команд

`devices/command_policy.py` — универсальный исполнитель, который оборачивает любую аппаратную операцию:

```python
runner = DeviceCommandRunner(
    device_name="my_device",
    default_policy=DeviceCommandPolicy(timeout_s=1.0, retry_count=1),
    activate_fault=self._activate_command_fault,   # колбэк для ошибок
    heartbeat=self._heartbeat,                       # колбэк для heartbeat
)

result = await runner.run(
    "command_name",
    operation,               # async def operation() -> T
    correlation_id=...,
    idempotency_key=...,      # для идемпотентных повторов
    policy=...,               # override политики
    classify_result_fault=...,  # классификатор ошибок по результату
    is_result_ambiguous=...,    # проверка на неоднозначность
    reconcile=...,              # сверка физического состояния
    raise_on_ambiguous_result=False,
    success_state=DeviceOperationalState.READY,
)
```

**Что делает runner:**
- Таймаут через `asyncio.wait_for(operation(), timeout=policy.timeout_s)`
- Retry до `policy.retry_count + 1` раз
- Кэш идемпотентности (LRU, maxsize=10000)
- Классификация fault-кодов
- Определение ambiguous-результата → manual review
- Сверка физического состояния (reconciliation)
- Heartbeat и fault-notification через колбэки

---

## 7. DeviceFaultCode — нормализованная таксономия ошибок

Все аппаратные ошибки маппятся на эти коды:

| Код | Описание |
|-----|----------|
| `command_timeout` | Превышен таймаут команды |
| `command_retry_exhausted` | Исчерпаны все retry |
| `transient_command_failure` | Временная ошибка (можно повторить) |
| `communication_error` | Ошибка связи с устройством |
| `protocol_error` | Ошибка протокола (невалидный ответ) |
| `device_unavailable` | Устройство недоступно |
| `ambiguous_physical_result` | Результат нельзя подтвердить |
| `physical_state_mismatch` | Физическое состояние не совпадает с ожидаемым |
| `reconciliation_required` | Требуется ручная сверка |
| `unsupported_operation` | Операция не поддерживается |
| `configuration_error` | Ошибка конфигурации |

---

## 8. Platform Profiles

### 8.1 Расширение `platform/`

```python
# platform/common.py
PlatformProfile(target_os, common_components, extension_points)
PlatformExtensionPoint(name, mode, status=IMPLEMENTED|EXTENSION_POINT, description, config)

# platform/windows/__init__.py
build_windows_profile() → PlatformProfile
# Extension points: kiosk_mode, autostart, service_manager(windows_service), watchdog

# platform/linux/__init__.py
build_linux_profile() → PlatformProfile
# Extension points: kiosk_mode, autostart, service_manager(systemd), watchdog
```

### 8.2 Что нужно сделать для реального деплоя

**Kiosk lock/unlock:**
- Реализовать Windows-блокировку: `LockWorkStation()` через ctypes
- Реализовать Linux-блокировку: `loginctl lock-session` или GNOME Screensaver D-Bus
- Класс `KioskLock` уже есть в `platform/kiosk_lock.py`, нужно заменить `SimulatorKioskLock` на реальный

**Windows service:**
- `packaging/windows/register-service.ps1` — скрипт регистрации через NSSM/sc.exe
- Нужно протестировать на целевой Windows-машине

**Linux systemd:**
- `packaging/linux/flower-vending.service` — unit-файл с `Restart=on-failure`
- `packaging/linux/README.md` — инструкция по установке

**Watchdog:**
- Реальный HW watchdog или OS-уровня (IOCTL для /dev/watchdog на Linux)
- Сейчас: `MockWatchdogAdapter` — заменить на реальный

---

## 9. Bench Validation Checklist

### 9.1 Что проверить на стенде (в порядке приоритета)

1. **Serial loopback** — `dbv300sd-serial-smoke` открывает COM-порт, пишет байты, читает ответ
2. **DBV-300-SD команды** — реализовать protocol, проверить initialize/poll/set_acceptance_enabled
3. **Denomination mapping** — сопоставить номиналы купюр с кодами устройства
4. **Escrow** — если поддерживается: stack/return escrow
5. **Payout** — проверить выдачу монет: точная сумма, частичная выдача, пустая кассета
6. **Motor** — проверить vend_slot для каждой ячейки, homing, jam detection
7. **Window** — open/close, датчики открытия/закрытия, тайминги
8. **Temperature sensor** — калибровка, порог блокировки (8°C)
9. **Door sensor** — open/close события
10. **Inventory sensor** — presence per slot, confidence level
11. **Position sensor** — home position, slot position
12. **Watchdog** — arm/kick/disarm, timeout → reset

### 9.2 Измеряемые тайминги

- Время инициализации каждого устройства
- Время опроса (poll) для валидатора
- Время vend_slot для мотора
- Время open/close окна выдачи
- Время выдачи сдачи (denomination overhead)
- Максимальное число купюр в минуту (через quick-insert в симуляторе)

### 9.3 Критерии готовности к pilot

- Каждый hardware adapter в конфигурации имеет `bench evidence` (протокол испытаний)
- Отключённые устройства имеют simulator-only режимы
- DBV-300-SD, payout, motor, window, pickup и сенсоры имеют измеренные тайминги
- Service/autostart/watchdog/kiosk поведение подтверждено на целевом ОС-образе
- Operator runbooks покрывают restock, reconciliation, pickup timeout, payout ambiguity, fault recovery

---

## 10. Deployment Architecture

```
┌─────────────────────────────────────────────────────┐
│                 Kiosk Application                    │
│  ┌───────────────────────────────────────────────┐  │
│  │           ApplicationCore + FSM                │  │
│  │  VendingController, PaymentCoordinator, ...    │  │
│  └────────────────┬──────────────────────────────┘  │
│                   │                                  │
│  ┌────────────────┴──────────────────────────────┐  │
│  │             Device Adapters                     │  │
│  │  DBV300SD │ Payout │ Motor │ Sensors │ Watchdog │  │
│  └────────────────┬──────────────────────────────┘  │
│                   │                                  │
│  ┌────────────────┴──────────────────────────────┐  │
│  │         Serial / USB / GPIO / Network           │  │
│  └────────────────┬──────────────────────────────┘  │
│                   │                                  │
├─────────────────────────────────────────────────────┤
│  Platform: Windows 10/11 IoT or Debian 13 Bookworm   │
│  Python 3.11+, PySide6, pyserial, SQLite             │
└─────────────────────────────────────────────────────┘
```

**Windows target:** Windows 10/11 (x64), COM-порты через USB-Serial
**Linux target:** Debian 13 Bookworm, `/dev/ttyUSB0`, systemd-управление
**Форматы сборки:** PyInstaller portable exe / Inno Setup installer / AppImage

---

## 11. Что НЕ менять (защищённые компоненты)

| Компонент | Причина |
|-----------|---------|
| Domain Model (`domain/`) | Чистая бизнес-логика, не зависит от железа |
| FSM (`app/fsm/`) | Все 22 состояния и переходы |
| Оркестраторы (`app/orchestrators/`) | Управляют flow, не касаются железа напрямую |
| UI (`ui/`) | PySide6, работает через Facade |
| Persistence (`infrastructure/persistence/`) | SQLite схема и репозитории |
| ChangeManager (`payments/`) | Расчёт сдачи, резервы — чистая математика |
| Harness (`simulators/harness.py`) | Детерминированные тесты и сценарии |
| EventBus / CommandBus | Инфраструктура обмена сообщениями |

## 12. Что изменить (точки расширения)

| Компонент | Файл | Что сделать |
|-----------|------|-------------|
| DBV-300-SD protocol | `devices/dbv300sd/protocol/base.py` + новый класс | Реализовать JCM command frames |
| DBV-300-SD bench | `devices/dbv300sd/bench.py` | Уже готов, использовать для снятия трейсов |
| Payout driver | Новый файл, implements `ChangeDispenser` | Реальный драйвер выдачи сдачи |
| Motor driver | Новый файл, implements `MotorController` | Реальный драйвер мотора |
| Window driver | Новый файл, implements `WindowController` | Реальный драйвер окна |
| Sensor drivers | Новые файлы | TemperatureSensor, DoorSensor, InventorySensor, PositionSensor |
| Watchdog | Новый файл, implements `WatchdogAdapter` | HW watchdog через `/dev/watchdog` или IOCTL |
| Фабрика устройств | `runtime/bootstrap.py` → `_build_production_devices()` | Выбирать адаптер по полю `driver` из конфига |
| Platform profiles | `platform/windows/__init__.py` и `platform/linux/__init__.py` | Реализовать kiosk lock, заменить заглушки |
| YAML конфиг | `config/targets/machine.debian13-target.yaml` | Настроить порты/драйверы для целевого стенда |
| Packaging | `packaging/linux/flower-vending.service` | Протестировать systemd-сервис на Debian 13 |

---

## 13. Быстрый старт для hardware engineer

```bash
# 1. Клонировать
git clone https://github.com/popka2007-root/flower-vending-system
cd flower-vending-system

# 2. Установить
python -m pip install -r requirements-dev.txt
python -m pip install -r requirements-ui.txt
python -m pip install -e ".[dev,ui,serial]"

# 3. Проверить, что симулятор работает
python -m pytest tests/ -q

# 4. Снять трейс с реального DBV-300-SD
python -m flower_vending dbv300sd-serial-smoke --port COM3 --baudrate 9600 \
  --tx-hex "02 03 01 FF" --read-size 16 --trace-log dbv-trace.jsonl

# 5. Запустить UI симулятора
python -m flower_vending simulator-ui
```

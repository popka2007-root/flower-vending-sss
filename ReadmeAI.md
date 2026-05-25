# Flower Vending System — Полная карта репозитория для AI-агента

## 1. О проекте

**Flower Vending System** — полноценная платформа управления киоском по продаже премиальных букетов. Система работает в режиме киоска (kiosk mode) с сенсорным экраном и физическими устройствами: купюроприёмник JCM DBV-300-SD, моторы выдачи товара, ESP32 Arduino для управления дверцами/двигателями/температурой.

### Ключевые возможности
- Каталог цветов с корзиной и оформлением заказа
- Приём наличных (JCM DBV-300-SD) с проверкой возможности сдачи
- Выдача товара через моторные слоты с дверцами выдачи
- Контроль температуры в витрине
- Crash recovery (журнал intent/outcome для каждого аппаратного действия)
- Сервисный режим (PIN-доступ, дашборд оператора)
- Интеграция с 1С и телеметрией
- 105 тестов (unit, integration, recovery, e2e)

## 2. Стек технологий

| Слой | Технология |
|------|-----------|
| Язык | Python 3.11+ |
| UI | PySide6 (Qt6) |
| Асинхронность | asyncio |
| Конфигурация | Pydantic v2 + PyYAML |
| БД | SQLite (WAL + FULL sync) |
| Протоколы устройств | pyserial (UART) |
| Фирмваре | ESP32 Arduino (C++) |
| Сборка | Hatchling |
| Качество кода | Ruff (линтер + форматтер), mypy (strict), pre-commit |
| Тесты | pytest, pytest-asyncio |
| Упаковка | PyInstaller, Inno Setup, AppImage |
| CI/CD | GitHub Actions |

## 3. Архитектура: Clean Architecture (строго)

```
┌──────────────────────────────────────────────────────┐
│                   UI LAYER (PySide6)                  │
│  KioskWindow → ScreenWidgets → KioskPresenter        │
└──────────────────────┬───────────────────────────────┘
                       │ async вызовы через asyncio
┌──────────────────────┴───────────────────────────────┐
│              APPLICATION FACADE                       │
│  UiApplicationFacade (мост между UI и Core)           │
└──────────────────────┬───────────────────────────────┘
                       │
┌──────────────────────┴───────────────────────────────┐
│              APPLICATION CORE                         │
│  ApplicationCore → CommandBus + EventBus + FSM        │
│  Orchestrators: VendingController, PaymentCoordinator,│
│  TransactionCoordinator, RecoveryManager и др.        │
└──────────────────────┬───────────────────────────────┘
                       │
┌──────────────────────┴───────────────────────────────┐
│              DOMAIN CORE (zero external imports!)     │
│  Entities, Value Objects, Aggregates, Domain Events,  │
│  Domain Commands, Exceptions                          │
└──────────────────────┬───────────────────────────────┘
                       │
┌──────────────────────┴───────────────────────────────┐
│              INFRASTRUCTURE                           │
│  SQLite, Repositories, Journal, Config (Pydantic),    │
│  Logging (JSONL)                                      │
└──────────────────────┬───────────────────────────────┘
                       │
┌──────────────────────┴───────────────────────────────┐
│              DEVICES & INTEGRATION                    │
│  ABC interfaces → DBV300SD / Arduino / Simulators    │
│  1C Client, Telemetry Publisher                      │
└──────────────────────────────────────────────────────┘
```

### Правило зависимостей
- **Domain Core** — НИКАКИХ импортов из PySide6, sqlite3, pyserial, yaml, pydantic
- **Application Core** — зависит только от Domain Core
- **Infrastructure** — реализует интерфейсы Domain Core
- **UI Layer** — зависит от Application Facade
- Все зависимости направлены ВНУТРЬ, к Domain Core

## 4. Структура директорий

### `src/flower_vending/` — основной пакет

#### `runtime/` — Bootstrap, CLI, Production-окружение
| Файл | Назначение |
|------|-----------|
| `cli.py` | `python -m flower_vending` — 18 подкоманд (validate-config, run, simulator-ui, service, discover, dbv300sd-*, printer-test и др.) |
| `bootstrap.py` | Сборка приложения в режиме симулятора (все моки) |
| `production.py` | Сборка приложения для продакшена (реальные адаптеры) |
| `ui_runner.py` | Запуск Qt-приложения с asyncio pump |
| `paths.py` | Поиск корневых директорий (source/bundle/state) |
| `discover.py` | Поиск COM-портов и Arduino |

#### `app/` — Application Core
| Файл | Назначение |
|------|-----------|
| `command_bus.py` | Async CommandBus — диспетчеризация типизированных команд (StartPurchase, AcceptCash, CancelPurchase) |
| `event_bus.py` | Async EventBus — publish/subscribe (critical vs best-effort) |
| `journal.py` | Protocol ApplicationJournal — запись intent/outcome для crash recovery |
| `bootstrap.py` | `build_application_core()` — DI-сборка всех оркестраторов, шин, FSM |

#### `app/fsm/` — Finite State Machine
| Файл | Назначение |
|------|-----------|
| `states.py` | Enum MachineState: 21 состояний (BOOT → IDLE → WAITING_FOR_PAYMENT → ... → FAULT) |
| `transitions.py` | Карта разрешённых переходов: `state -> set[target_states]` |
| `machine_fsm.py` | StateMachineEngine — переходы с проверкой инвариантов |

#### `app/orchestrators/` — Оркестраторы бизнес-логики
| Файл | Назначение |
|------|-----------|
| `vending_controller.py` | Главный контроллер: start_purchase, accept_cash, cancel_purchase, confirm_pickup |
| `payment_coordinator.py` | Управление сессией оплаты: start_cash_session, process_validator_event, complete_payment |
| `transaction_coordinator.py` | Жизненный цикл транзакции: create, get, clear_active, recover |
| `recovery_manager.py` | Crash recovery: detect_unresolved_intents, classify_intent, recover_transaction |
| `pickup_timeout_coordinator.py` | Таймаут на выдачу (arm/cancel deadline) |
| `idle_timeout_coordinator.py` | Автоотмена покупки при бездействии (120s) |
| `service_mode_coordinator.py` | Вход/выход из сервисного режима (SHA-256 PIN, rate-limited) |
| `health_monitor.py` | Мониторинг здоровья устройств, критическая температура, блокировка продаж |
| `display_rotation_controller.py` | Вращение витрины для демонстрации |

#### `domain/` — Domain Core (без внешних импортов)
| Поддиректория | Содержимое |
|---------------|-----------|
| `events/` | DomainEvent + sub-packages: payment_events, vending_events, machine_events, device_events |
| `commands/` | Command base + purchase_commands, recovery_commands, service_commands |
| `exceptions/` | Иерархия: FlowerVendingError → SaleBlockedError, ChangeUnavailableError и т.д. |
| `value_objects/` | TransactionId, CorrelationId, ProductId, Amount, Denomination, Temperature, DeviceState |
| `entities/` | Transaction, Product, Slot, MachineStatus, MoneyInventory, PaymentSession |
| `aggregates/` | MachineRuntimeAggregate, PurchaseTransactionAggregate |

#### `devices/` — Адаптеры оборудования
| Файл/папка | Назначение |
|-----------|-----------|
| `contracts.py` | DTO: DeviceFault, DeviceHealth, BillValidatorEvent, MoneyValue, TemperatureReading |
| `interfaces/` | ABC интерфейсы: BillValidator, ChangeDispenser, MotorController, WindowController, TemperatureSensor, DoorSensor и др. |
| `command_policy.py` | DeviceCommandPolicy — timeout/retry/fault classification |
| `dbv300sd/` | Протокол JCM DBV-300-SD (serial transport, polling, frame parsing) |
| `arduino/` | Serial transport + адаптеры motor/window/temperature/door/position |
| `printer/` | Адаптер чекового принтера |
| `payment/` | Sberbank SPM terminal + mock |

#### `simulators/` — Моки и тестовые харнессы
| Файл/папка | Назначение |
|-----------|-----------|
| `devices/` | MockBillValidator, MockChangeDispenser, MockMotorController и т.д. |
| `faults.py` | SimulatorFaultCode |
| `control.py` | SimulatorControlService + RecentEventStore |
| `harness.py` | Сценарии для симуляции |
| `scenarios/` | normal_sale, insufficient_change, bill_rejected и др. |

#### `infrastructure/` — Персистентность и конфигурация
| Файл | Назначение |
|------|-----------|
| `persistence/sqlite/database.py` | SQLite wrapper (WAL, FULL sync, потокобезопасность) |
| `persistence/sqlite/schema.py` | Schema v2: 11 таблиц |
| `persistence/sqlite/repositories.py` | 10 репозиториев |
| `persistence/journal.py` | SQLiteTransactionJournal — intent/outcome |
| `config/models.py` | Все Pydantic модели: AppConfig, MachineConfig, RuntimeConfig, UiConfig, DevicesConfig |
| `config/loader.py` | Загрузка YAML + снапшот настроек устройств |

#### `ui/` — PySide6 Kiosk UI
| Файл | Назначение |
|------|-----------|
| `facade.py` | UiApplicationFacade — мост без Qt между Core и UI |
| `navigation.py` | ScreenId enum + NavigationState (stack) |
| `session.py` | KioskSessionState — состояние UI |
| `theme.py` | Light/Dark/Auto темы с переключением по времени |
| `presenters/` | KioskPresenter, CatalogPresenter, PaymentPresenter, StatusPresenter, ServicePresenter, AdminPresenter |
| `views/` | KioskWindow (QMainWindow), CatalogScreen, CheckoutFlow, PaymentScreen, DeliveryScreen, ThankYouScreen, StatusScreen, ServiceScreen, DiagnosticsScreen, PinScreen, AdminShell |
| `widgets/` | ModernButton, OutlineButton, BannerWidget, ChartWidget, ProcessingIndicator |
| `viewmodels/` | Все ViewModel'и: CatalogScreenVM, PaymentScreenVM, DeliveryScreenVM и т.д. |

### `tests/` — тесты
- `tests/unit/` — 9 файлов (change manager, config, dbv, recovery, UI)
- `tests/integration/` — 6 файлов (cash flows, event bus, pickup timeout, runtime)
- `tests/recovery/` — 2 файла (persistence, crash windows)
- `tests/e2e/` — 1 файл (full kiosk flow)
- `tests/load_test.py` — нагрузочное тестирование

## 5. Data Flow: нормальная продажа (шаг за шагом)

1. Пользователь выбирает товар → `catalog_screen` эмитирует `checkout_requested`
2. `KioskPresenter.checkout_cart()` → `UiApplicationFacade.start_cash_checkout()`
3. `CommandBus.dispatch(StartPurchase)` → `VendingController.start_purchase()`
   - InventoryService.ensure_selection()
   - TransactionCoordinator.create_transaction()
   - FSM: IDLE → PRODUCT_SELECTED → CHECKING_AVAILABILITY → CHECKING_CHANGE → WAITING_FOR_PAYMENT
4. `CommandBus.dispatch(AcceptCash)` → `VendingController.accept_cash()`
5. `PaymentCoordinator.start_cash_session()`:
   - ChangeManager.assess_sale() + reserve_for_transaction()
   - BillValidator.enable_acceptance()
   - FSM: → ACCEPTING_CASH
   - Journal.record_intent("acceptance_enable_requested")
6. Цикл asyncio: `BillValidator.read_event()` → BILL_STACKED
   - `PaymentCoordinator.process_validator_event()`
   - Transaction.record_stacked_cash()
   - EventBus: `cash_amount_updated`
   - Если сумма ≥ цена → `complete_payment()`
7. `PaymentCoordinator.complete_payment()`:
   - Transaction.confirm_payment()
   - BillValidator.disable_acceptance()
   - FSM: → PAYMENT_ACCEPTED
   - Если нужна сдача → FSM DISPENSING_CHANGE → ChangeManager.dispense()
   - EventBus: `payment_confirmed` + `vend_authorized`
8. `VendingController.handle_vend_authorized()`:
   - FSM: DISPENSING_PRODUCT → MotorController.vend_slot()
   - FSM: OPENING_DELIVERY_WINDOW → WindowController.open_window()
   - FSM: WAITING_FOR_CUSTOMER_PICKUP
   - EventBus: `delivery_window_opened`
9. `confirm_pickup()` → WindowController.close_window() → FSM COMPLETED → IDLE

## 6. FSM: 21 состояний машины

```
BOOT → IDLE → PRODUCT_SELECTED → CHECKING_AVAILABILITY → CHECKING_CHANGE
→ WAITING_FOR_PAYMENT → ACCEPTING_CASH → PAYMENT_ACCEPTED
→ DISPENSING_CHANGE → DISPENSING_PRODUCT → OPENING_DELIVERY_WINDOW
→ WAITING_FOR_CUSTOMER_PICKUP → COMPLETED

Любое состояние → FAULT → RECOVERY_PENDING → ...
IDLE → SERVICE_MODE_ACTIVE → ...
```

- Все переходы проверяются в `transitions.py`
- Невалидный переход → `InvariantViolationError`

## 7. Ключевые паттерны и соглашения

### Intent/Outcome Journal
Перед каждым аппаратным действием записывается **intent** (намерение) в БД. После выполнения — **outcome** (результат). При перезагрузке `RecoveryManager` находит незавершённые intent'ы и восстанавливает состояние.

### EventBus: critical vs best-effort
- **Critical**: подписчики выполняются последовательно; ошибка прерывает цепочку
- **Best-effort**: `fire-and-forget`; ошибки логируются, но не блокируют

### Async-only background loops
- Polling купюроприёмника
- Health monitor
- Pickup timeout
- Idle timeout

### QueueHandler для логов
- Отдельный поток для записи JSONL
- `contextvars`: `correlation_id`, `transaction_id` прозрачно пробрасываются

### Threading model
- Основной поток: asyncio event loop (все бизнес-операции)
- UI поток: Qt event loop (только рендеринг)
- `UiApplicationFacade` — мост: ставит корутины в asyncio loop через `ensure_future`

### Именование
- `snake_case` для модулей, функций, переменных
- `PascalCase` для классов
- `UPPER_CASE` для констант
- Файлы = один класс или логическая группа, назван по классу (snake_case)

### Тестирование
- `@pytest.mark.asyncio` для async-тестов
- SimulatorScenarios для детерминированных тестов
- Mock-устройства реализуют те же ABC, что и реальные

## 8. CLI (18 подкоманд)

```bash
# Валидация и диагностика
python -m flower_vending validate-config
python -m flower_vending diagnostics
python -m flower_vending status

# Симулятор
python -m flower_vending simulator-ui --config config/examples/machine.simulator.yaml
python -m flower_vending simulator-runtime

# Продакшен
python -m flower_vending run --config config/machine.production.yaml

# Сервис
python -m flower_vending service --operator tech --pin 1234
python -m flower_vending discover

# Оборудование
python -m flower_vending dbv300sd-analyze --port COM3
python -m flower_vending printer-test --port COM4
```

## 9. Как добавить новую фичу

1. Добавить Domain Event в `domain/events/`
2. Если нужна новая команда — добавить в `domain/commands/`
3. Реализовать оркестратор в `app/orchestrators/`
4. Зарегистрировать команду/обработчик в `app/bootstrap.py`
5. Подписаться на события в EventBus
6. Добавить ViewModel в `ui/viewmodels/`
7. Добавить экран в `ui/views/`
8. Зарегистрировать экран в `kiosk_window.py`
9. Написать тесты: unit → integration → e2e

## 10. Ссылки для AI-агента

- Полный architectural spec: `REPOSITORY.md` (672 строки)
- Главная точка входа: `src/flower_vending/__main__.py` → `runtime/cli.py`
- DI-сборка: `runtime/bootstrap.py` (симулятор), `runtime/production.py` (продакшен)
- Схема БД: `src/flower_vending/infrastructure/persistence/sqlite/schema.py`
- Конфигурация: `src/flower_vending/infrastructure/config/models.py`
- Интерфейсы устройств: `src/flower_vending/devices/interfaces/`
- Тесты: `tests/` (unit, integration, recovery, e2e)
- Фирмваре ESP32: `firmware/`

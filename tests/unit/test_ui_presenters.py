from __future__ import annotations

import unittest

from flower_vending.simulators.control import EventLogEntry
from flower_vending.ui.facade import (
    CatalogEntry,
    DeviceDiagnosticsRow,
    DiagnosticsSnapshot,
    MachineUiSnapshot,
)
from flower_vending.ui.presenters.catalog_presenter import CatalogPresenter
from flower_vending.ui.presenters.payment_presenter import PaymentPresenter
from flower_vending.ui.presenters.service_presenter import ServicePresenter
from flower_vending.ui.presenters.status_presenter import StatusPresenter
from flower_vending.ui.viewmodels.common import BannerTone


class PresenterTests(unittest.TestCase):
    def test_payment_presenter_exposes_simulator_quick_insert_buttons(self) -> None:
        presenter = PaymentPresenter()
        model = presenter.present_payment(
            transaction=type(
                "Tx",
                (),
                {
                    "product_name": "Розы Эквадор 7 шт.",
                    "price_minor_units": 249000,
                    "currency_code": "RUB",
                    "accepted_minor_units": 50000,
                    "change_due_minor_units": 0,
                },
            )(),
            machine=MachineUiSnapshot(
                machine_state="ACCEPTING_CASH",
                exact_change_only=False,
                sale_blockers=(),
                allow_cash_sales=True,
                allow_vending=True,
                service_mode=False,
                active_transaction_id="tx-1",
            ),
            quick_insert_denominations=(50000, 100000),
        )
        self.assertEqual(
            tuple(action.action_id for action in model.quick_insert_actions),
            ("insert_bill:50000", "insert_bill:100000"),
        )
        self.assertEqual(tuple(action.label for action in model.quick_insert_actions), ("500 ₽", "1 000 ₽"))

    def test_payment_presenter_humanizes_validator_warnings(self) -> None:
        presenter = PaymentPresenter()
        model = presenter.present_payment(
            transaction=type(
                "Tx",
                (),
                {
                    "product_name": "Розы Эквадор 7 шт.",
                    "price_minor_units": 249000,
                    "currency_code": "RUB",
                    "accepted_minor_units": 0,
                    "change_due_minor_units": 0,
                },
            )(),
            machine=MachineUiSnapshot(
                machine_state="ACCEPTING_CASH",
                exact_change_only=False,
                sale_blockers=(),
                allow_cash_sales=True,
                allow_vending=True,
                service_mode=False,
                active_transaction_id="tx-1",
            ),
            warning_message="simulator bill rejected",
        )
        assert model.banner is not None
        self.assertEqual(
            model.banner.message,
            "Купюра не принята. Проверьте купюру или попробуйте другую.",
        )

    def test_service_presenter_includes_simulator_actions_and_recent_events(self) -> None:
        presenter = ServicePresenter()
        diagnostics = DiagnosticsSnapshot(
            machine=MachineUiSnapshot(
                machine_state="IDLE",
                exact_change_only=False,
                sale_blockers=("service_door_open",),
                allow_cash_sales=False,
                allow_vending=False,
                service_mode=True,
                active_transaction_id=None,
            ),
            devices=(DeviceDiagnosticsRow("validator", "ready", ()),),
            unresolved_transaction_ids=("tx-1",),
            recent_events=(
                EventLogEntry(
                    timestamp="2026-04-15T00:00:00+00:00",
                    event_type="service_door_opened",
                    correlation_id="corr-1",
                    transaction_id=None,
                    summary="door opened",
                ),
            ),
        )
        model = presenter.present_service_dashboard(
            diagnostics,
            simulator_actions=("open_service_door", "inject_motor_fault"),
        )
        all_actions = []
        for tab in model.tabs:
            for grp in tab.groups:
                all_actions.extend(grp.actions)
        self.assertTrue(any("Диагностика" in (a.label if a else "") for a in all_actions if a))
        self.assertTrue(any("Открыть сервисную дверь" in (a.label if a else "") for a in all_actions if a))
        self.assertIsNotNone(model.kpi)
        self.assertEqual(model.kpi.blockers_count, 1)

    def test_status_presenter_restricted_mode_is_explicit(self) -> None:
        presenter = StatusPresenter()
        model = presenter.present_restricted_mode(details=("manual_review_required", "partial_payout"))
        self.assertEqual(model.title, "Нужна проверка оператора")
        assert model.banner is not None
        assert model.primary_action is not None
        self.assertEqual(model.banner.tone, BannerTone.ERROR)
        self.assertEqual(model.primary_action.action_id, "clear_restricted_state")

    def test_status_presenter_restricted_mode_shows_transaction_diagnostics(self) -> None:
        presenter = StatusPresenter()
        model = presenter.present_restricted_mode(
            details=("manual_review_required", "tx:tx-42", "unresolved:tx-42,tx-43"),
            transaction_id="tx-42",
            unresolved_transaction_ids=("tx-42", "tx-43"),
        )
        self.assertTrue(any("tx-42" in item for item in model.details))
        self.assertTrue(any("tx-43" in item for item in model.details))
        self.assertEqual(sum(1 for item in model.details if "Незавершенные транзакции:" in item), 1)

    # --- StatusPresenter: present_exact_change_only ---

    def test_status_presenter_exact_change_only(self) -> None:
        presenter = StatusPresenter()
        model = presenter.present_exact_change_only()
        self.assertEqual(model.title, "Только точная сумма")
        assert model.banner is not None
        self.assertEqual(model.banner.tone, BannerTone.WARNING)
        assert model.primary_action is not None
        self.assertEqual(model.primary_action.action_id, "show_catalog")
        assert model.secondary_action is not None
        self.assertEqual(model.secondary_action.action_id, "open_service")

    # --- StatusPresenter: present_no_change ---

    def test_status_presenter_no_change(self) -> None:
        presenter = StatusPresenter()
        model = presenter.present_no_change(message="device_fault")
        self.assertEqual(model.title, "Сдача недоступна")
        self.assertEqual(model.message, "Обнаружена неисправность устройства.")
        assert model.banner is not None
        self.assertEqual(model.banner.tone, BannerTone.WARNING)
        assert model.primary_action is not None
        self.assertEqual(model.primary_action.action_id, "show_catalog")
        assert model.secondary_action is not None
        self.assertEqual(model.secondary_action.action_id, "open_service")

    # --- StatusPresenter: present_sales_blocked ---

    def test_status_presenter_sales_blocked(self) -> None:
        presenter = StatusPresenter()
        machine = MachineUiSnapshot(
            machine_state="IDLE",
            exact_change_only=False,
            sale_blockers=("service_door_open", "critical_temperature"),
            allow_cash_sales=False,
            allow_vending=False,
            service_mode=False,
            active_transaction_id=None,
        )
        model = presenter.present_sales_blocked(machine)
        self.assertEqual(model.title, "Продажа временно недоступна")
        self.assertIn("Открыта сервисная дверь.", model.details)
        self.assertIn("Температура в охлаждаемой камере вышла за безопасный диапазон.", model.details)
        assert model.banner is not None
        self.assertEqual(model.banner.tone, BannerTone.ERROR)
        assert model.primary_action is not None
        self.assertEqual(model.primary_action.action_id, "clear_restricted_state")
        assert model.secondary_action is not None
        self.assertEqual(model.secondary_action.action_id, "open_service")

    # --- StatusPresenter: present_refund (3 states) ---

    def test_status_presenter_refund_in_progress(self) -> None:
        presenter = StatusPresenter()
        model = presenter.present_refund(refund_minor_units=50000, currency_code="RUB")
        self.assertEqual(model.title, "Возврат средств")
        self.assertIn("500", model.message)
        assert model.banner is not None
        self.assertEqual(model.banner.tone, BannerTone.INFO)
        self.assertIsNone(model.primary_action)
        assert model.secondary_action is not None
        self.assertEqual(model.secondary_action.action_id, "open_service")

    def test_status_presenter_refund_complete(self) -> None:
        presenter = StatusPresenter()
        model = presenter.present_refund(refund_complete=True)
        self.assertEqual(model.title, "Средства возвращены")
        assert model.banner is not None
        self.assertEqual(model.banner.tone, BannerTone.SUCCESS)
        assert model.primary_action is not None
        self.assertEqual(model.primary_action.action_id, "show_catalog")
        assert model.secondary_action is not None
        self.assertEqual(model.secondary_action.action_id, "open_service")

    def test_status_presenter_refund_error(self) -> None:
        presenter = StatusPresenter()
        model = presenter.present_refund(error_message="device_fault")
        self.assertEqual(model.title, "Ошибка возврата")
        self.assertEqual(model.message, "Обнаружена неисправность устройства.")
        assert model.banner is not None
        self.assertEqual(model.banner.tone, BannerTone.ERROR)
        assert model.primary_action is not None
        self.assertEqual(model.primary_action.action_id, "open_service")
        assert model.secondary_action is not None
        self.assertEqual(model.secondary_action.action_id, "show_home")

    # --- StatusPresenter: present_manual_review ---

    def test_status_presenter_manual_review(self) -> None:
        presenter = StatusPresenter()
        model = presenter.present_manual_review(reason="manual_review_required", transaction_id="tx-42")
        self.assertEqual(model.title, "Требуется проверка оператора")
        self.assertTrue(any("tx-42" in d for d in model.details))
        assert model.banner is not None
        self.assertEqual(model.banner.tone, BannerTone.ERROR)
        assert model.primary_action is not None
        self.assertEqual(model.primary_action.action_id, "open_service")
        assert model.secondary_action is not None
        self.assertEqual(model.secondary_action.action_id, "show_home")

    # --- StatusPresenter: present_error ---

    def test_status_presenter_error(self) -> None:
        presenter = StatusPresenter()
        model = presenter.present_error(
            title="Критическая ошибка",
            message="validator_fault",
            details=("Необходима проверка",),
        )
        self.assertEqual(model.title, "Критическая ошибка")
        self.assertEqual(model.message, "Купюроприемник временно недоступен.")
        self.assertIn("Необходима проверка", model.details)
        assert model.banner is not None
        self.assertEqual(model.banner.tone, BannerTone.ERROR)
        assert model.primary_action is not None
        self.assertEqual(model.primary_action.action_id, "clear_restricted_state")
        assert model.secondary_action is not None
        self.assertEqual(model.secondary_action.action_id, "open_service")

    # --- StatusPresenter: present_dispensing ---

    def test_status_presenter_dispensing(self) -> None:
        presenter = StatusPresenter()
        model = presenter.present_dispensing(product_name="Розы Эквадор")
        self.assertEqual(model.title, "Букет выдаётся")
        self.assertIn("Розы Эквадор", model.message)
        assert model.banner is not None
        self.assertEqual(model.banner.tone, BannerTone.INFO)
        self.assertIsNone(model.primary_action)

    # --- StatusPresenter: present_pickup ---

    def test_status_presenter_pickup(self) -> None:
        presenter = StatusPresenter()
        model = presenter.present_pickup(
            product_name="Розы Эквадор",
            pickup_timeout_active=True,
            pickup_timeout_remaining_s=30.0,
        )
        self.assertEqual(model.title, "Заберите букет")
        self.assertIn("Розы Эквадор", model.message)
        assert model.banner is not None
        self.assertEqual(model.banner.tone, BannerTone.SUCCESS)
        assert model.primary_action is not None
        self.assertEqual(model.primary_action.action_id, "confirm_pickup")

    def test_status_presenter_pickup_no_timeout(self) -> None:
        presenter = StatusPresenter()
        model = presenter.present_pickup(
            product_name="Розы Эквадор",
            pickup_timeout_active=False,
            pickup_timeout_remaining_s=None,
        )
        self.assertEqual(model.title, "Заберите букет")
        self.assertIn("закроется автоматически", model.details[1])

    # --- StatusPresenter: _humanize_blocker ---

    def test_status_presenter_humanize_blocker(self) -> None:
        presenter = StatusPresenter()
        known = {
            "critical_temperature": "Температура",
            "device_fault": "неисправность устройства",
            "service_door_open": "сервисная дверь",
            "recovery_pending": "безопасное восстановление",
            "validator_fault": "Купюроприемник",
            "manual_review_required": "ручная проверка",
            "partial_payout": "не полностью",
            "pickup_timeout": "Время получения истекло",
        }
        for key, expected_substring in known.items():
            with self.subTest(key=key):
                self.assertIn(expected_substring, presenter._humanize_blocker(key))
        self.assertEqual(
            presenter._humanize_blocker("some_unknown_blocker"),
            "Неизвестная причина: some unknown blocker",
        )
        self.assertEqual(
            presenter._humanize_blocker("sales are blocked: unknown_blocker"),
            "Продажа временно остановлена до выяснения причины.",
        )
        result = presenter._humanize_blocker("sales are blocked: critical_temperature, validator_fault")
        self.assertIn("Температура", result)
        self.assertIn("Купюроприемник", result)

    # --- CatalogPresenter: present_catalog ---

    def test_catalog_presenter_present_catalog(self) -> None:
        presenter = CatalogPresenter()
        entries = (
            CatalogEntry(
                product_id="rose_red",
                slot_id="A1",
                display_name="Красные розы",
                category="roses",
                price_minor_units=50000,
                currency_code="RUB",
                quantity=3,
                available=True,
                is_bouquet=True,
                metadata={"short_description": "Шикарный букет", "size_label": "Средний букет"},
            ),
            CatalogEntry(
                product_id="tulip_yellow",
                slot_id="B2",
                display_name="Жёлтые тюльпаны",
                category="tulips",
                price_minor_units=30000,
                currency_code="RUB",
                quantity=0,
                available=False,
                is_bouquet=False,
                metadata={},
            ),
        )
        machine = MachineUiSnapshot(
            machine_state="IDLE",
            exact_change_only=True,
            sale_blockers=(),
            allow_cash_sales=True,
            allow_vending=True,
            service_mode=False,
            active_transaction_id=None,
        )
        model = presenter.present_catalog(title="Цветочный автомат", subtitle="Выберите букет", entries=entries, machine=machine)
        self.assertEqual(model.title, "Цветочный автомат")
        self.assertEqual(len(model.items), 2)
        self.assertEqual(model.items[0].title, "Красные розы")
        self.assertEqual(model.items[0].price_text, "500 ₽")
        self.assertEqual(model.items[0].availability_text, "В наличии")
        self.assertEqual(model.items[0].badge_text, "Средний")
        self.assertFalse(model.items[1].enabled)
        self.assertEqual(model.items[1].availability_text, "Нет в наличии")
        self.assertEqual(model.items[1].badge_text, "")
        assert model.banner is not None
        self.assertEqual(model.banner.tone, BannerTone.WARNING)

    def test_catalog_presenter_present_catalog_no_banner_when_not_exact_change(self) -> None:
        presenter = CatalogPresenter()
        entry = CatalogEntry(
            product_id="rose_red",
            slot_id="A1",
            display_name="Красные розы",
            category="roses",
            price_minor_units=50000,
            currency_code="RUB",
            quantity=1,
            available=True,
            is_bouquet=True,
            metadata={},
        )
        machine = MachineUiSnapshot(
            machine_state="IDLE",
            exact_change_only=False,
            sale_blockers=(),
            allow_cash_sales=True,
            allow_vending=True,
            service_mode=False,
            active_transaction_id=None,
        )
        model = presenter.present_catalog(title="Каталог", subtitle="Выберите", entries=(entry,), machine=machine)
        self.assertIsNone(model.banner)

    # --- CatalogPresenter: present_product_details ---

    def test_catalog_presenter_present_product_details(self) -> None:
        presenter = CatalogPresenter()
        entry = CatalogEntry(
            product_id="rose_red",
            slot_id="A1",
            display_name="Красные розы",
            category="roses",
            price_minor_units=50000,
            currency_code="RUB",
            quantity=3,
            available=True,
            is_bouquet=True,
            metadata={
                "short_description": "Шикарный букет",
                "freshness_note": "Свежие",
                "size_label": "Премиум букет",
                "category_label": "Розы красные",
                "image_id": "rose_red_001",
            },
        )
        machine = MachineUiSnapshot(
            machine_state="IDLE",
            exact_change_only=False,
            sale_blockers=(),
            allow_cash_sales=True,
            allow_vending=True,
            service_mode=False,
            active_transaction_id=None,
        )
        model = presenter.present_product_details(entry=entry, machine=machine)
        self.assertEqual(model.title, "Красные розы")
        self.assertEqual(model.price_text, "500 ₽")
        self.assertEqual(model.availability_text, "В наличии")
        self.assertEqual(model.short_description, "Шикарный букет")
        self.assertEqual(model.freshness_note, "Свежие")
        self.assertEqual(model.size_label, "Премиум букет")
        self.assertEqual(model.category_label, "Розы красные")
        self.assertEqual(model.badge_text, "Премиум")
        self.assertIsNone(model.advisory_text)
        self.assertTrue(model.primary_action.enabled)
        self.assertEqual(model.primary_action.action_id, "start_cash_checkout")

    def test_catalog_presenter_present_product_details_not_available(self) -> None:
        presenter = CatalogPresenter()
        entry = CatalogEntry(
            product_id="tulip_yellow",
            slot_id="B2",
            display_name="Жёлтые тюльпаны",
            category="tulips",
            price_minor_units=30000,
            currency_code="RUB",
            quantity=0,
            available=False,
            is_bouquet=False,
            metadata={},
        )
        machine = MachineUiSnapshot(
            machine_state="IDLE",
            exact_change_only=False,
            sale_blockers=(),
            allow_cash_sales=True,
            allow_vending=True,
            service_mode=False,
            active_transaction_id=None,
        )
        model = presenter.present_product_details(entry=entry, machine=machine)
        self.assertFalse(model.primary_action.enabled)
        self.assertEqual(model.availability_text, "Нет в наличии")
        self.assertEqual(model.badge_text, "")


if __name__ == "__main__":
    unittest.main()

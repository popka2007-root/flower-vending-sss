"""Service and diagnostics presentation logic — redesigned with cards + KPI."""

from __future__ import annotations

from flower_vending.ui.facade import CatalogEntry, DiagnosticsSnapshot
from flower_vending.ui.viewmodels.common import ActionButtonViewModel
from flower_vending.ui.viewmodels.screens import (
    DiagnosticsDeviceViewModel,
    DiagnosticsScreenViewModel,
    ServiceActionGroupViewModel,
    ServiceKpiViewModel,
    ServiceScreenViewModel,
    ServiceTabViewModel,
)

_SIMULATOR_GROUPS: dict[str, dict[str, str]] = {
    "Дверь": {
        "open_service_door": "Открыть сервисную дверь",
        "close_service_door": "Закрыть сервисную дверь",
    },
    "Температура": {
        "raise_temperature_critical": "Поднять температуру (крит.)",
        "restore_temperature_nominal": "Восстановить температуру",
    },
    "Платежи и купюры": {
        "inject_validator_unavailable": "Отключить купюроприёмник",
        "inject_bill_rejected": "След. купюра — отказ",
        "inject_bill_jam": "След. купюра — замятие",
        "inject_payout_unavailable": "Отключить выдачу сдачи",
        "inject_partial_payout": "Частичная сдача",
    },
    "Выдача и окно": {
        "inject_motor_fault": "Ошибка мотора",
        "inject_window_fault": "Ошибка окна выдачи",
        "force_pickup_timeout_now": "Таймаут получения",
    },
    "Инвентарь": {
        "inject_inventory_mismatch": "Ошибка наличия",
        "restore_inventory_match": "Восстановить датчик",
    },
}

_SCENARIOS: dict[str, tuple[str, ...]] = {
    "Тест оплаты": ("inject_validator_unavailable", "inject_bill_jam"),
    "Тест выдачи": ("inject_motor_fault", "inject_window_fault"),
    "Полный recovery": (
        "close_service_door", "restore_temperature_nominal",
        "restore_inventory_match", "clear_simulator_faults",
    ),
}


def product_toggle_action_id(product_id: str, *, enabled: bool) -> str:
    return f"toggle_product:{product_id}:{'enable' if not enabled else 'disable'}"


def is_product_toggle_action(action_id: str) -> bool:
    return action_id.startswith("toggle_product:")


def parse_product_toggle_action(action_id: str) -> tuple[str, bool] | None:
    parts = action_id.split(":")
    if len(parts) == 3 and parts[0] == "toggle_product":
        return parts[1], parts[2] == "enable"
    return None


def _action(label: str, action_id: str, variant: str = "default", enabled: bool = True) -> ActionButtonViewModel:
    return ActionButtonViewModel(action_id, label, enabled)


class ServicePresenter:

    def present_service_dashboard(
        self,
        diagnostics: DiagnosticsSnapshot,
        *,
        simulator_actions: tuple[str, ...] = (),
        catalog_entries: tuple[CatalogEntry, ...] = (),
        payment_methods: dict[str, bool] | None = None,
        purchase_locked: bool = False,
    ) -> ServiceScreenViewModel:
        ms = diagnostics.machine
        total_devices = len(diagnostics.devices)
        ok_devices = sum(1 for d in diagnostics.devices if d.state in ("ok", "ready", "normal"))
        state_color = "green" if ms.machine_state == "IDLE" else (
            "red" if ms.machine_state in ("ERROR", "RECOVERY_PENDING") else "yellow")

        kpi = ServiceKpiViewModel(
            machine_state=ms.machine_state,
            state_color=state_color,
            blockers_count=len(ms.sale_blockers),
            unresolved_count=len(diagnostics.unresolved_transaction_ids),
            devices_ok=ok_devices,
            devices_total=total_devices,
        )

        lock_label = "Разблокировать продажи" if purchase_locked else "Заблокировать продажи"
        lock_action = "unlock_purchase" if purchase_locked else "lock_purchase"

        product_toggles = tuple(
            ActionButtonViewModel(
                product_toggle_action_id(e.product_id, enabled=e.available),
                e.display_name,
                e.available,
            )
            for e in catalog_entries
        )

        sim_available = {a for a in simulator_actions}

        service_groups: list[ServiceActionGroupViewModel] = []
        service_groups.append(ServiceActionGroupViewModel("Управление", (
            _action("Диагностика", "show_diagnostics", "primary"),
            _action(lock_label, lock_action, "warning"),
        )))
        service_groups.append(ServiceActionGroupViewModel("Способы оплаты", (
            _action("Наличные", "set_payment_methods:cash,sbp,card" if payment_methods else "set_payment_methods:cash"),
            _action("Карта", "set_payment_methods:cash,card"),
            _action("СБП", "set_payment_methods:cash,sbp"),
        ), "compact"))
        if product_toggles:
            service_groups.append(ServiceActionGroupViewModel("Товары (вкл/выкл)", product_toggles, "toggles"))
        service_groups.append(ServiceActionGroupViewModel("Сброс и восстановление", (
            _action("Сбросить блокировки", "clear_restricted_state", "danger"),
            _action("Сбросить незаверш. транзакции", "clear_pending_transactions", "danger"),
            _action("Тест печати", "print_test"),
        )))
        service_groups.append(ServiceActionGroupViewModel("Навигация", (
            _action("Админ-панель", "show_admin", "primary"),
            _action("Выйти из сервиса", "exit_service", "danger"),
        )))

        sim_groups: list[ServiceActionGroupViewModel] = []
        for group_name, actions in _SIMULATOR_GROUPS.items():
            group_actions = tuple(
                _action(label, aid)
                for aid, label in actions.items()
                if aid in sim_available
            )
            if group_actions:
                sim_groups.append(ServiceActionGroupViewModel(group_name, group_actions))

        if "clear_simulator_faults" in sim_available:
            sim_groups.append(ServiceActionGroupViewModel("Сброс симулятора", (
                _action("Сбросить все ошибки симулятора", "clear_simulator_faults", "warning"),
            )))

        scenarios = tuple(
            _action(name, f"scenario:{name}", "primary")
            for name in _SCENARIOS if any(a in sim_available for a in _SCENARIOS[name])
        )
        if scenarios:
            sim_groups.append(ServiceActionGroupViewModel("Сценарии", scenarios))

        tabs = (
            ServiceTabViewModel("service", "Сервис", tuple(service_groups)),
            ServiceTabViewModel("simulation", "Симуляция", tuple(sim_groups)),
        )

        pm = payment_methods or {}
        return ServiceScreenViewModel(
            title="Сервисный режим",
            subtitle="Панель оператора",
            kpi=kpi,
            tabs=tabs,
            product_toggles=product_toggles,
            payment_cash=pm.get("cash", True),
            payment_card=pm.get("card", False),
            payment_sbp=pm.get("sbp", False),
            purchase_locked=purchase_locked,
        )

    def _state_color(self, state: str) -> str:
        st = state.lower()
        if st in ("ready", "normal", "ok"):
            return "green"
        if st in ("degraded", "disabled"):
            return "yellow"
        return "red"

    def present_diagnostics(self, diagnostics: DiagnosticsSnapshot) -> DiagnosticsScreenViewModel:
        devices = tuple(
            DiagnosticsDeviceViewModel(
                device_name=device.device_name,
                state=device.state,
                fault_codes=device.fault_codes,
                state_color=self._state_color(device.state),
            )
            for device in diagnostics.devices
        )
        recent_events = tuple(
            f"{event.event_type} [{event.correlation_id}] {event.summary}"
            for event in diagnostics.recent_events[-8:]
        )
        return DiagnosticsScreenViewModel(
            title="Диагностика устройств",
            subtitle="Текущее состояние runtime и симулятора",
            machine_state=diagnostics.machine.machine_state,
            sale_blockers=diagnostics.machine.sale_blockers,
            unresolved_transactions=diagnostics.unresolved_transaction_ids,
            devices=devices,
            recent_events=recent_events,
            primary_action=ActionButtonViewModel("back_to_service", "Назад"),
        )

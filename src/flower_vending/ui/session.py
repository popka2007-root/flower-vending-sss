"""Mutable UI session state for the kiosk presentation layer."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class KioskSessionState:
    selected_product_id: str | None = None
    selected_slot_id: str | None = None
    active_transaction_id: str | None = None
    selected_product_name: str | None = None
    selected_price_minor_units: int = 0
    selected_currency_code: str = "RUB"
    payment_method: str = "cash"
    accepted_minor_units: int = 0
    change_due_minor_units: int = 0
    refund_minor_units: int = 0
    last_error_title: str | None = None
    last_error_message: str | None = None
    last_warning_message: str | None = None
    restricted_details: tuple[str, ...] = ()
    customer_message: str = "Выберите букет или цветок"
    sale_blockers: set[str] = field(default_factory=set)
    _1c_enabled: bool = False
    _admin_filter: str = "all"

    def select_product(
        self,
        *,
        product_id: str,
        slot_id: str,
        product_name: str,
        price_minor_units: int,
        currency_code: str,
    ) -> None:
        self.selected_product_id = product_id
        self.selected_slot_id = slot_id
        self.selected_product_name = product_name
        self.selected_price_minor_units = price_minor_units
        self.selected_currency_code = currency_code
        self.accepted_minor_units = 0
        self.change_due_minor_units = 0
        self.last_error_title = None
        self.last_error_message = None

    def start_transaction(self, transaction_id: str) -> None:
        self.active_transaction_id = transaction_id
        self.accepted_minor_units = 0
        self.change_due_minor_units = 0
        self.last_error_title = None
        self.last_error_message = None

    def record_error(self, *, title: str, message: str) -> None:
        self.last_error_title = title
        self.last_error_message = message

    def record_restricted(self, *details: str) -> None:
        self.restricted_details = tuple(details)

    def clear_messages(self) -> None:
        self.last_error_title = None
        self.last_error_message = None
        self.last_warning_message = None
        self.restricted_details = ()

    def reset_purchase(self) -> None:
        self.active_transaction_id = None
        self.accepted_minor_units = 0
        self.change_due_minor_units = 0
        self.customer_message = "Выберите букет или цветок"
        self.clear_messages()

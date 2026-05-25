"""Payment screen presentation logic."""

from __future__ import annotations

from flower_vending.ui.facade import MachineUiSnapshot, TransactionUiSnapshot
from flower_vending.ui.presenters.formatting import format_money
from flower_vending.ui.viewmodels.common import ActionButtonViewModel, BannerTone, BannerViewModel
from flower_vending.ui.viewmodels.screens import PaymentScreenViewModel


class PaymentPresenter:
    def present_payment(
        self,
        *,
        transaction: TransactionUiSnapshot,
        machine: MachineUiSnapshot,
        quick_insert_denominations: tuple[int, ...] = (),
        warning_message: str | None = None,
        payment_method: str = "cash",
    ) -> PaymentScreenViewModel:
        remaining_minor = max(0, transaction.price_minor_units - transaction.accepted_minor_units)
        banner = None
        if warning_message:
            banner = BannerViewModel(
                title="Проверьте оплату",
                message=self._humanize_warning(warning_message),
                tone=BannerTone.WARNING,
            )
        elif machine.exact_change_only:
            banner = BannerViewModel(
                title="Нужна точная сумма",
                message="Сдача сейчас не гарантируется. Внесите ровно стоимость выбранного товара.",
                tone=BannerTone.WARNING,
            )
        is_non_cash = payment_method in ("card", "qr", "sbp")

        return PaymentScreenViewModel(
            title=self._payment_title(payment_method),
            subtitle=self._payment_subtitle(payment_method),
            product_name=transaction.product_name,
            price_text=format_money(transaction.price_minor_units, transaction.currency_code),
            accepted_text=format_money(transaction.accepted_minor_units, transaction.currency_code) if not is_non_cash else "",
            remaining_text=format_money(remaining_minor, transaction.currency_code) if not is_non_cash else "",
            change_text=format_money(transaction.change_due_minor_units, transaction.currency_code) if not is_non_cash else "",
            help_text=self._payment_help(payment_method),
            banner=banner,
            cancel_action=ActionButtonViewModel("cancel_purchase", "Отменить покупку"),
            payment_method=payment_method,
            quick_insert_actions=tuple(
                ActionButtonViewModel(
                    action_id=f"insert_bill:{denomination}",
                    label=format_money(denomination, transaction.currency_code),
                )
                for denomination in quick_insert_denominations
            ) if not is_non_cash else (),
        )

    @staticmethod
    def _payment_title(method: str) -> str:
        titles = {
            "cash": "Оплата наличными",
            "card": "Оплата картой",
            "qr": "Оплата по QR-коду",
            "sbp": "Оплата через СБП",
        }
        return titles.get(method, "Оплата")

    @staticmethod
    def _payment_subtitle(method: str) -> str:
        subtitles = {
            "cash": "Внесите купюры в купюроприемник",
            "card": "Приложите карту к терминалу",
            "qr": "Отсканируйте QR-код на экране",
            "sbp": "Подтвердите перевод в приложении банка",
        }
        return subtitles.get(method, "")

    @staticmethod
    def _payment_help(method: str) -> str:
        helps = {
            "cash": "После полной оплаты автомат выдаст букет и откроет окно получения.",
            "card": "Дождитесь подтверждения оплаты на терминале.",
            "qr": "Отсканируйте код и подтвердите оплату на телефоне.",
            "sbp": "Вы будете перенаправлены в приложение вашего банка.",
        }
        return helps.get(method, "")

    def _humanize_warning(self, message: str) -> str:
        normalized = message.lower()
        if "bill rejected" in normalized or "rejected" in normalized:
            return "Купюра не принята. Проверьте купюру или попробуйте другую."
        if "bill jam" in normalized or "jam" in normalized:
            return "Купюра застряла. Покупка остановлена до проверки автомата."
        if "validator unavailable" in normalized or "validator" in normalized:
            return "Автомат временно не принимает оплату."
        if "change" in normalized or "payout" in normalized:
            return "Автомат не может безопасно выдать сдачу для этой оплаты."
        return message

"""Catalog and product-card presentation logic."""

from __future__ import annotations

from typing import Any

from flower_vending.ui.asset_paths import resolve_ui_asset_path
from flower_vending.ui.facade import CatalogEntry, MachineUiSnapshot
from flower_vending.ui.presenters.formatting import format_money
from flower_vending.ui.viewmodels.common import ActionButtonViewModel, BannerTone, BannerViewModel
from flower_vending.ui.viewmodels.screens import (
    CatalogCategoryViewModel,
    CatalogItemViewModel,
    CatalogScreenViewModel,
    ProductDetailsScreenViewModel,
)


class CatalogPresenter:
    def present_catalog(
        self,
        *,
        title: str,
        subtitle: str,
        entries: tuple[CatalogEntry, ...],
        machine: MachineUiSnapshot,
    ) -> CatalogScreenViewModel:
        banner = None
        if machine.exact_change_only:
            banner = BannerViewModel(
                title="Только точная сумма",
                message="Автомат принимает оплату, но сдача сейчас не гарантируется.",
                tone=BannerTone.WARNING,
            )
        items = tuple(self._item_view_model(entry) for entry in entries)
        return CatalogScreenViewModel(
            title=title,
            subtitle=subtitle,
            banner=banner,
            items=items,
            categories=self._category_view_models(items),
            secondary_action=None,
        )

    def present_product_details(
        self,
        *,
        entry: CatalogEntry,
        machine: MachineUiSnapshot,
    ) -> ProductDetailsScreenViewModel:
        advisory = None
        if machine.exact_change_only:
            advisory = "Нужна точная сумма: автомат не сможет безопасно выдать сдачу."
        elif not entry.available:
            advisory = "Этот букет временно недоступен. Выберите другую позицию в каталоге."
        pm = machine.payment_methods or {}
        return ProductDetailsScreenViewModel(
            title=entry.display_name,
            subtitle="",
            price_text=format_money(entry.price_minor_units, entry.currency_code),
            availability_text=self._availability_text(entry),
            short_description=self._metadata_text(entry.metadata, "short_description"),
            image_path=self._image_path(entry.metadata),
            category_label=self._category_label(entry.category, entry.metadata),
            freshness_note=self._metadata_text(entry.metadata, "freshness_note"),
            size_label=self._metadata_text(entry.metadata, "size_label"),
            badge_text=self._badge_text(entry),
            advisory_text=advisory,
            primary_action=ActionButtonViewModel(
                "start_cash_checkout",
                "Оплатить",
                entry.available,
            ),
            secondary_action=ActionButtonViewModel("", "Назад"),
            payment_methods=self._payment_method_actions(pm),
        )

    def _item_view_model(self, entry: CatalogEntry) -> CatalogItemViewModel:
        return CatalogItemViewModel(
            product_id=entry.product_id,
            slot_id=entry.slot_id,
            title=entry.display_name,
            category=entry.category,
            category_label=self._category_label(entry.category, entry.metadata),
            price_text=format_money(entry.price_minor_units, entry.currency_code),
            price_minor_units=entry.price_minor_units,
            currency_code=entry.currency_code,
            availability_text=self._availability_text(entry),
            enabled=entry.available,
            available_quantity=entry.quantity,
            short_description=self._metadata_text(entry.metadata, "short_description")
            or (self._metadata_text(entry.metadata, "description")),
            image_path=self._image_path(entry.metadata),
            freshness_note=self._metadata_text(entry.metadata, "freshness_note"),
            size_label=self._metadata_text(entry.metadata, "size_label"),
            accent=None,
            badge_text=self._badge_text(entry),
        )

    def _category_view_models(
        self,
        items: tuple[CatalogItemViewModel, ...],
    ) -> tuple[CatalogCategoryViewModel, ...]:
        seen: dict[str, str] = {}
        for item in items:
            seen.setdefault(item.category, item.category_label)
        all_label = "Все"
        return (CatalogCategoryViewModel("all", all_label),) + tuple(
            CatalogCategoryViewModel(
                category_id,
                label,
            )
            for category_id, label in seen.items()
        )

    def _availability_text(self, entry: CatalogEntry) -> str:
        if not entry.available:
            return "Нет в наличии"
        return "В наличии"

    def _badge_text(self, entry: CatalogEntry) -> str:
        size_label = self._metadata_text(entry.metadata, "size_label")
        if size_label:
            compact = {
                "7 стеблей": "7 шт",
                "9 стеблей": "9 шт",
                "Средний букет": "Средний",
                "Подарочный формат": "Подарочный",
                "Премиум букет": "Премиум",
            }
            return compact.get(size_label, size_label)
        return ""

    def _category_label(self, category: str, metadata: dict[str, Any] | None = None) -> str:
        if metadata:
            category_label = self._metadata_text(metadata, "category_label")
            if category_label:
                return category_label
        mapping = {
            "roses": "Розы",
            "tulips": "Тюльпаны",
            "bouquets": "Букеты",
            "seasonal": "Сезонные",
            "gift": "Подарочные",
            "flowers": "Цветы",
        }
        return mapping.get(category, category.replace("_", " ").title())

    def _image_path(self, metadata: dict[str, Any]) -> str | None:
        raw_path = self._metadata_text(metadata, "image_path")
        resolved = resolve_ui_asset_path(raw_path)
        if resolved is not None:
            return resolved

        image_id = self._metadata_text(metadata, "image_id")
        if image_id:
            return resolve_ui_asset_path(f"products/{image_id}.jpg")
        return None

    def _metadata_text(self, metadata: dict[str, Any], key: str) -> str | None:
        value = metadata.get(key)
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _payment_method_actions(pm: dict[str, bool]) -> tuple[ActionButtonViewModel, ...]:
        labels = {
            "cash": "Наличные",
            "card": "Карта",
            "qr": "QR-код",
            "sbp": "СБП",
        }
        actions: list[ActionButtonViewModel] = []
        for method_id, enabled in pm.items():
            if enabled and method_id in labels:
                actions.append(
                    ActionButtonViewModel(
                        action_id=f"pay_{method_id}",
                        label=labels[method_id],
                    )
                )
        return tuple(actions)

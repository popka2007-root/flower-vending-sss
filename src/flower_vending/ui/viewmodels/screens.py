"""Screen-specific view models for the kiosk UI."""

from __future__ import annotations

from dataclasses import dataclass, field

from flower_vending.ui.viewmodels.common import ActionButtonViewModel, BannerViewModel


@dataclass(frozen=True, slots=True)
class CatalogCategoryViewModel:
    category_id: str
    label: str


@dataclass(frozen=True, slots=True)
class CatalogItemViewModel:
    product_id: str
    slot_id: str
    title: str
    category: str
    category_label: str
    price_text: str
    price_minor_units: int = 0
    currency_code: str = "RUB"
    availability_text: str = ""
    enabled: bool = True
    short_description: str | None = None
    image_path: str | None = None
    freshness_note: str | None = None
    size_label: str | None = None
    accent: str | None = None
    badge_text: str | None = None


@dataclass(frozen=True, slots=True)
class CatalogScreenViewModel:
    title: str
    subtitle: str
    banner: BannerViewModel | None
    items: tuple[CatalogItemViewModel, ...]
    categories: tuple[CatalogCategoryViewModel, ...] = ()
    primary_action: ActionButtonViewModel | None = None
    secondary_action: ActionButtonViewModel | None = None


@dataclass(frozen=True, slots=True)
class ProductDetailsScreenViewModel:
    title: str
    subtitle: str
    price_text: str
    availability_text: str
    short_description: str | None
    image_path: str | None
    category_label: str | None
    freshness_note: str | None
    size_label: str | None
    badge_text: str | None
    advisory_text: str | None
    primary_action: ActionButtonViewModel
    secondary_action: ActionButtonViewModel
    payment_methods: tuple[ActionButtonViewModel, ...] = ()


@dataclass(frozen=True, slots=True)
class PaymentScreenViewModel:
    title: str
    subtitle: str
    product_name: str
    price_text: str
    accepted_text: str
    remaining_text: str
    change_text: str
    help_text: str
    banner: BannerViewModel | None
    cancel_action: ActionButtonViewModel
    payment_method: str = "cash"
    quick_insert_actions: tuple[ActionButtonViewModel, ...] = ()
    is_processing: bool = False


@dataclass(frozen=True, slots=True)
class StatusScreenViewModel:
    title: str
    message: str
    details: tuple[str, ...] = ()
    banner: BannerViewModel | None = None
    primary_action: ActionButtonViewModel | None = None
    secondary_action: ActionButtonViewModel | None = None


@dataclass(frozen=True, slots=True)
class DeliveryScreenViewModel:
    title: str
    message: str
    details: tuple[str, ...] = ()
    banner: BannerViewModel | None = None
    primary_action: ActionButtonViewModel | None = None
    remaining_seconds: float | None = None


@dataclass(frozen=True, slots=True)
class DiagnosticsDeviceViewModel:
    device_name: str
    state: str
    fault_codes: tuple[str, ...] = ()
    state_color: str = "green"


@dataclass(frozen=True, slots=True)
class DiagnosticsScreenViewModel:
    title: str
    subtitle: str
    machine_state: str
    sale_blockers: tuple[str, ...]
    unresolved_transactions: tuple[str, ...]
    devices: tuple[DiagnosticsDeviceViewModel, ...] = ()
    recent_events: tuple[str, ...] = ()
    primary_action: ActionButtonViewModel | None = None


@dataclass(frozen=True, slots=True)
class ServiceKpiViewModel:
    machine_state: str = ""
    state_color: str = "green"
    blockers_count: int = 0
    unresolved_count: int = 0
    devices_ok: int = 0
    devices_total: int = 0


@dataclass(frozen=True, slots=True)
class ServiceActionGroupViewModel:
    label: str
    actions: tuple[ActionButtonViewModel, ...] = ()
    variant: str = "default"


@dataclass(frozen=True, slots=True)
class ServiceTabViewModel:
    tab_id: str
    label: str
    groups: tuple[ServiceActionGroupViewModel, ...] = ()


@dataclass(frozen=True, slots=True)
class ServiceScreenViewModel:
    title: str
    subtitle: str
    kpi: ServiceKpiViewModel | None = None
    tabs: tuple[ServiceTabViewModel, ...] = ()
    product_toggles: tuple[ActionButtonViewModel, ...] = ()
    payment_cash: bool = True
    payment_card: bool = False
    payment_sbp: bool = False
    purchase_locked: bool = False


@dataclass(frozen=True, slots=True)
class AdminOrderViewModel:
    order_id: str
    items_summary: str
    total_text: str
    status: str
    status_text: str
    date: str
    window_id: str | None = None
    payment_method: str = "—"


@dataclass(frozen=True, slots=True)
class AdminOrdersTabViewModel:
    orders: tuple[AdminOrderViewModel, ...] = ()
    revenue_total: str = ""
    pending_count: int = 0
    completed_count: int = 0
    cancelled_count: int = 0
    active_filter: str = "all"


@dataclass(frozen=True, slots=True)
class AdminAnalyticsTabViewModel:
    revenue_total: str = ""
    revenue_delta: str = ""
    pending_count: int = 0
    completed_count: int = 0
    cancelled_count: int = 0
    chart_days: dict[str, float] = field(default_factory=dict)
    payment_methods: dict[str, float] = field(default_factory=dict)
    top_products: tuple[tuple[str, str, float], ...] = ()


@dataclass(frozen=True, slots=True)
class AdminCatalogItemViewModel:
    product_id: str
    title: str
    price_text: str
    category: str
    stock: int
    active: bool
    image_path: str | None = None


@dataclass(frozen=True, slots=True)
class AdminCatalogTabViewModel:
    products: tuple[AdminCatalogItemViewModel, ...] = ()
    can_add: bool = True


@dataclass(frozen=True, slots=True)
class AdminWindowViewModel:
    window_id: str
    status: str
    status_text: str
    detail_text: str
    current_order_id: str | None = None


@dataclass(frozen=True, slots=True)
class AdminWindowsTabViewModel:
    windows: tuple[AdminWindowViewModel, ...] = ()
    activity_log: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AdminSettingsTabViewModel:
    vending_name: str = ""
    working_hours: str = ""
    contact_phone: str = ""
    support_email: str = ""
    min_order_amount: int = 1000
    delivery_time: str = "2-3"
    accept_card: bool = False
    accept_cash: bool = True
    accept_sbp: bool = False
    auto_restock: bool = False
    restock_threshold: int = 5
    notify_on_order: bool = False
    notify_on_low_stock: bool = False
    receipt_printer: bool = False
    discounts_enabled: bool = False
    discount_percent: int = 0
    price_markup: int = 0
    current_pin: str = ""
    new_pin: str = ""

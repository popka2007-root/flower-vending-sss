"""Payment terminal adapters."""

from flower_vending.devices.payment.interfaces import (
    PaymentMethod,
    PaymentRequest,
    PaymentResult,
    PaymentStatus,
    PaymentTerminal,
    TerminalState,
)
from flower_vending.devices.payment.config import PaymentTerminalConfig
from flower_vending.devices.payment.mock_terminal import MockPaymentTerminal
from flower_vending.devices.payment.sberbank_spm import SberbankSPMTerminal

__all__ = [
    "PaymentMethod",
    "PaymentRequest",
    "PaymentResult",
    "PaymentStatus",
    "PaymentTerminal",
    "TerminalState",
    "PaymentTerminalConfig",
    "MockPaymentTerminal",
    "SberbankSPMTerminal",
]

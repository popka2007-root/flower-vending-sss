"""Mock payment terminal for testing without hardware."""

from __future__ import annotations

import asyncio
from typing import Any

from flower_vending.devices.payment.interfaces import (
    PaymentMethod,
    PaymentRequest,
    PaymentResult,
    PaymentStatus,
    PaymentTerminal,
    TerminalState,
)


class MockPaymentTerminal(PaymentTerminal):
    def __init__(self, name: str = "mock_terminal") -> None:
        self._name = name
        self._connected = False
        self._state = TerminalState.IDLE

    @property
    def name(self) -> str:
        return self._name

    async def connect(self) -> None:
        self._connected = True
        self._state = TerminalState.IDLE

    async def disconnect(self) -> None:
        self._connected = False
        self._state = TerminalState.OUT_OF_ORDER

    async def get_state(self) -> TerminalState:
        return self._state

    async def start_payment(self, request: PaymentRequest) -> PaymentResult:
        self._state = TerminalState.PROCESSING
        await asyncio.sleep(0.5)
        self._state = TerminalState.COMPLETED
        return PaymentResult(
            transaction_id=request.transaction_id,
            status=PaymentStatus.APPROVED,
            payment_method=PaymentMethod.CARD,
            authorization_code="MOCK123456",
            card_last_digits="1234",
            provider="mock",
            details={"request": str(request)},
        )

    async def cancel_payment(self, transaction_id: str) -> bool:
        self._state = TerminalState.IDLE
        return True

    async def get_health(self) -> dict[str, Any]:
        return {
            "name": self._name,
            "connected": self._connected,
            "state": self._state.value,
        }

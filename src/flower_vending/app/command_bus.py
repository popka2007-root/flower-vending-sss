"""Asynchronous command bus."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeVar, cast, overload

from flower_vending.domain.commands import Command
from flower_vending.domain.commands.purchase_commands import (
    AcceptCash,
    CancelPurchase,
    ConfirmPickup,
    StartPurchase,
)
from flower_vending.domain.commands.recovery_commands import RecoverInterruptedTransaction
from flower_vending.domain.commands.service_commands import (
    EnterServiceMode,
    LockPurchaseButton,
    ToggleProductCommand,
)


CommandT = TypeVar("CommandT", bound=Command)
ResultT = TypeVar("ResultT")
CommandHandler = Callable[[CommandT], Awaitable[ResultT]]
ErasedCommandHandler = Callable[[Command], Awaitable[object]]


class CommandBus:
    def __init__(self) -> None:
        self._handlers: dict[type[Command], ErasedCommandHandler] = {}

    def register_handler(
        self,
        command_type: type[CommandT],
        handler: CommandHandler[CommandT, ResultT],
    ) -> None:
        self._handlers[command_type] = cast(ErasedCommandHandler, handler)

    @overload
    async def dispatch(self, command: StartPurchase) -> str: ...

    @overload
    async def dispatch(self, command: AcceptCash) -> str: ...

    @overload
    async def dispatch(self, command: CancelPurchase) -> str: ...

    @overload
    async def dispatch(self, command: ConfirmPickup) -> str: ...

    @overload
    async def dispatch(self, command: EnterServiceMode) -> str: ...

    @overload
    async def dispatch(self, command: ToggleProductCommand) -> tuple[str, bool]: ...

    @overload
    async def dispatch(self, command: LockPurchaseButton) -> bool: ...

    @overload
    async def dispatch(self, command: RecoverInterruptedTransaction) -> str: ...

    @overload
    async def dispatch(self, command: Command) -> object: ...

    async def dispatch(self, command: Command) -> object:
        command_type = type(command)
        if command_type not in self._handlers:
            raise LookupError(f"no handler registered for command type {command_type.__name__}")
        return await self._handlers[command_type](command)

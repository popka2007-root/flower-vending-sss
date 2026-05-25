"""Asynchronous event bus."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from flower_vending.domain.events import DomainEvent


EventHandler = Callable[[DomainEvent], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class EventSubscription:
    handler: EventHandler
    critical: bool


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[EventSubscription]] = defaultdict(list)
        self._logger = logging.getLogger("flower_vending.event_bus")

    def subscribe(self, event_type: str, handler: EventHandler, *, critical: bool = True) -> None:
        self._subscribers[event_type].append(EventSubscription(handler=handler, critical=critical))

    def subscribe_critical(self, event_type: str, handler: EventHandler) -> None:
        self.subscribe(event_type, handler, critical=True)

    def subscribe_best_effort(self, event_type: str, handler: EventHandler) -> None:
        self.subscribe(event_type, handler, critical=False)

    def unsubscribe(self, event_type: str, handler: EventHandler) -> bool:
        subscriptions = self._subscribers.get(event_type)
        if not subscriptions:
            return False
        for i, subscription in enumerate(subscriptions):
            if subscription.handler is handler:
                subscriptions.pop(i)
                if not subscriptions:
                    self._subscribers.pop(event_type, None)
                return True
        return False

    async def publish(self, event: DomainEvent) -> None:
        subscriptions = [
            *self._subscribers.get(event.event_type, []),
            *self._subscribers.get("*", []),
        ]
        if not subscriptions:
            return

        critical_subscriptions = [s for s in subscriptions if s.critical]
        best_effort_subscriptions = [s for s in subscriptions if not s.critical]

        first_error: BaseException | None = None
        if critical_subscriptions:
            critical_results = await asyncio.gather(
                *(s.handler(event) for s in critical_subscriptions),
                return_exceptions=True,
            )
            for i, (subscription, result) in enumerate(
                zip(critical_subscriptions, critical_results), start=1
            ):
                if not isinstance(result, BaseException):
                    continue
                if isinstance(result, asyncio.CancelledError):
                    raise result
                self._logger.error(
                    "event_bus_critical_handler_failed",
                    extra={
                        "event_type": event.event_type,
                        "correlation_id": event.correlation_id,
                        "transaction_id": event.transaction_id,
                        "handler": self._handler_name(subscription.handler),
                        "order": i,
                        "critical": True,
                    },
                    exc_info=(type(result), result, result.__traceback__),
                )
                if first_error is None:
                    first_error = result

        if first_error is not None and isinstance(first_error, Exception):
            raise first_error

        if not best_effort_subscriptions:
            return

        results = await asyncio.gather(
            *(s.handler(event) for s in best_effort_subscriptions),
            return_exceptions=True,
        )
        for subscription, result in zip(best_effort_subscriptions, results, strict=True):
            if not isinstance(result, BaseException):
                continue
            if isinstance(result, asyncio.CancelledError):
                raise result
            if not isinstance(result, Exception):
                raise result
            self._log_best_effort_failure(subscription, event, result)

    def _log_best_effort_failure(
        self,
        subscription: EventSubscription,
        event: DomainEvent,
        error: Exception,
    ) -> None:
        self._logger.error(
            "event_bus_best_effort_handler_failed",
            extra={
                "event_type": event.event_type,
                "correlation_id": event.correlation_id,
                "transaction_id": event.transaction_id,
                "handler": self._handler_name(subscription.handler),
                "critical": subscription.critical,
            },
            exc_info=(type(error), error, error.__traceback__),
        )

    def _handler_name(self, handler: EventHandler) -> str:
        module = getattr(handler, "__module__", type(handler).__module__)
        qualified_name = getattr(handler, "__qualname__", type(handler).__qualname__)
        return f"{module}.{qualified_name}"

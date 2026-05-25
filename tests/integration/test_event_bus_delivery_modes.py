from __future__ import annotations

from flower_vending.domain.events import DomainEvent
from tests._support import AsyncHarnessTestCase


class EventBusDeliveryModeTests(AsyncHarnessTestCase):
    async def test_best_effort_handler_failure_does_not_abort_command(self) -> None:
        harness = await self.create_harness()
        delivered: list[str] = []

        async def failing_ui_listener(event: DomainEvent) -> None:
            if event.event_type == "purchase_started":
                raise RuntimeError("ui refresh failed")

        async def observer(event: DomainEvent) -> None:
            if event.event_type == "purchase_started":
                delivered.append(event.event_type)

        harness.core.event_bus.subscribe_best_effort("*", failing_ui_listener)
        harness.core.event_bus.subscribe_best_effort("*", observer)

        with self.assertLogs("flower_vending.event_bus", level="ERROR") as logs:
            transaction_id = await harness.start_purchase(correlation_id="best-effort-listener")

        self.assertTrue(transaction_id)
        self.assertEqual(delivered, ["purchase_started"])
        self.assertIn("purchase_started", harness.recorder.event_types)
        self.assertIn("event_bus_best_effort_handler_failed", "\n".join(logs.output))

    async def test_critical_handler_failure_is_returned_to_command(self) -> None:
        harness = await self.create_harness()
        delivered: list[str] = []

        async def failing_journal_listener(event: DomainEvent) -> None:
            if event.event_type == "purchase_started":
                raise RuntimeError("journal write failed")

        async def observer(event: DomainEvent) -> None:
            if event.event_type == "purchase_started":
                delivered.append(event.event_type)

        harness.core.event_bus.subscribe_critical("*", failing_journal_listener)
        harness.core.event_bus.subscribe_best_effort("*", observer)

        with self.assertLogs("flower_vending.event_bus", level="ERROR") as logs:
            with self.assertRaisesRegex(RuntimeError, "journal write failed"):
                await harness.start_purchase(correlation_id="critical-listener")

        self.assertEqual(delivered, [])
        self.assertIn("event_bus_critical_handler_failed", "\n".join(logs.output))

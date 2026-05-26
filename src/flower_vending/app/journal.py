"""Application-layer durable intent journal port."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Iterator, Protocol, cast


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


class JournalOutcome(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True, slots=True)
class ApplicationJournalRecord:
    entry_kind: str
    entry_name: str
    correlation_id: str
    transaction_id: str | None = None
    machine_state: str | None = None
    transaction_status: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    idempotency_key: str | None = None
    created_at: datetime = field(default_factory=_utc_now)


def journal_idempotency_key(
    *,
    transaction_id: str,
    action_name: str,
    logical_step: str,
    record_kind: str,
) -> str:
    return f"{transaction_id}:{action_name}:{logical_step}:{record_kind}"


def intent_idempotency_key(
    *,
    transaction_id: str,
    action_name: str,
    logical_step: str,
) -> str:
    return journal_idempotency_key(
        transaction_id=transaction_id,
        action_name=action_name,
        logical_step=logical_step,
        record_kind="intent",
    )


def outcome_idempotency_key(
    *,
    transaction_id: str,
    action_name: str,
    logical_step: str,
) -> str:
    return journal_idempotency_key(
        transaction_id=transaction_id,
        action_name=action_name,
        logical_step=logical_step,
        record_kind="outcome",
    )


class ApplicationJournal(Protocol):
    @contextmanager
    def atomic_transaction(self) -> Iterator[sqlite3.Connection]:
        """Provide an atomic transaction context for multi-step persistence."""
        ...

    def record_intent(
        self,
        *,
        action_name: str,
        correlation_id: str,
        transaction_id: str,
        logical_step: str,
        machine_state: str | None = None,
        transaction_status: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> int | None:
        """Persist the intent before a hardware-facing action starts."""

    def record_outcome(
        self,
        *,
        action_name: str,
        outcome: JournalOutcome,
        correlation_id: str,
        transaction_id: str,
        logical_step: str,
        machine_state: str | None = None,
        transaction_status: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> int | None:
        """Persist the hardware-facing action result."""

    def unresolved_intents(self) -> tuple[ApplicationJournalRecord, ...]:
        """Return intent records that do not have a matching outcome."""

    def orphaned_outcomes(self) -> tuple[ApplicationJournalRecord, ...]:
        """Return outcome records that do not have a matching intent."""


class NoopApplicationJournal:
    @contextmanager
    def atomic_transaction(self) -> Iterator[sqlite3.Connection]:
        # Minimal dummy connection for no-op case
        yield cast(sqlite3.Connection, None)

    def record_intent(
        self,
        *,
        action_name: str,
        correlation_id: str,
        transaction_id: str,
        logical_step: str,
        machine_state: str | None = None,
        transaction_status: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> int | None:
        return None

    def record_outcome(
        self,
        *,
        action_name: str,
        outcome: JournalOutcome,
        correlation_id: str,
        transaction_id: str,
        logical_step: str,
        machine_state: str | None = None,
        transaction_status: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> int | None:
        return None

    def unresolved_intents(self) -> tuple[ApplicationJournalRecord, ...]:
        return ()

    def orphaned_outcomes(self) -> tuple[ApplicationJournalRecord, ...]:
        return ()

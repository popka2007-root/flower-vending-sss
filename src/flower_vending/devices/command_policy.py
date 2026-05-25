"""Policy runner for normalized device commands."""

from __future__ import annotations

import asyncio
import inspect
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from typing import Any, Protocol, TypeVar, cast

from flower_vending.devices.contracts import (
    DeviceCommandPolicy,
    DeviceFaultCode,
    DeviceOperationalState,
    PhysicalReconciliationStatus,
    PhysicalStateReconciliation,
)
from flower_vending.devices.exceptions import (
    AmbiguousDeviceResultError,
    DeviceAdapterError,
    DeviceCommandError,
    DeviceCommandRetryExhaustedError,
    DeviceCommandTimeoutError,
)

T = TypeVar("T")


class ActivateFault(Protocol):
    def __call__(
        self,
        code: str,
        message: str,
        *,
        critical: bool = True,
        **details: Any,
    ) -> None:
        """Record a normalized device fault."""


class Heartbeat(Protocol):
    def __call__(self, *, state: DeviceOperationalState | None = None, **details: Any) -> None:
        """Record a normalized device heartbeat."""


CommandOperation = Callable[[], Awaitable[T]]
ResultFaultClassifier = Callable[[T], str | None]
ResultAmbiguityClassifier = Callable[[T], bool]
StateReconciler = Callable[[T], PhysicalStateReconciliation | Awaitable[PhysicalStateReconciliation]]


class DeviceCommandRunner:
    """Apply timeout, retry, idempotency, and reconciliation policy around commands."""

    def __init__(
        self,
        *,
        device_name: str,
        default_policy: DeviceCommandPolicy | None = None,
        activate_fault: ActivateFault,
        heartbeat: Heartbeat,
    ) -> None:
        self._device_name = device_name
        self._default_policy = default_policy or DeviceCommandPolicy()
        self._activate_fault = activate_fault
        self._heartbeat = heartbeat
        self._idempotency_cache: OrderedDict[str, Any] = OrderedDict()
        self._idempotency_cache_maxsize = 10000

    async def run(
        self,
        command_name: str,
        operation: CommandOperation[T],
        *,
        correlation_id: str | None = None,
        idempotency_key: str | None = None,
        policy: DeviceCommandPolicy | None = None,
        classify_result_fault: ResultFaultClassifier[T] | None = None,
        is_result_ambiguous: ResultAmbiguityClassifier[T] | None = None,
        reconcile: StateReconciler[T] | None = None,
        raise_on_ambiguous_result: bool = False,
        success_state: DeviceOperationalState = DeviceOperationalState.READY,
    ) -> T:
        active_policy = policy or self._default_policy
        cache_key = self._cache_key(command_name, idempotency_key)
        if cache_key is not None and cache_key in self._idempotency_cache:
            self._idempotency_cache.move_to_end(cache_key)
            self._heartbeat(
                state=DeviceOperationalState.READY,
                command_name=command_name,
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
                idempotent_replay=True,
            )
            return cast(T, self._copy_cached_value(self._idempotency_cache[cache_key]))

        max_attempts = active_policy.retry_count + 1
        last_error: DeviceCommandError | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                result = await self._run_once(operation, active_policy)
                result_fault = classify_result_fault(result) if classify_result_fault else None
                ambiguous = (is_result_ambiguous(result) if is_result_ambiguous else False)
                reconciliation = await self._reconcile(result, reconcile)
                ambiguous = ambiguous or reconciliation.manual_review_required

                if result_fault and active_policy.is_retryable(result_fault) and attempt < max_attempts:
                    self._heartbeat(
                        state=DeviceOperationalState.DEGRADED,
                        command_name=command_name,
                        correlation_id=correlation_id,
                        idempotency_key=idempotency_key,
                        fault_code=result_fault,
                        attempt=attempt,
                        retrying=True,
                    )
                    continue

                if ambiguous and active_policy.require_manual_review_on_ambiguous_result:
                    self._activate_ambiguous_fault(
                        command_name,
                        correlation_id=correlation_id,
                        idempotency_key=idempotency_key,
                        attempt=attempt,
                        reconciliation=reconciliation,
                        result_fault=result_fault,
                    )
                    if cache_key is not None:
                        self._cache_set(cache_key, result)
                    if raise_on_ambiguous_result:
                        raise AmbiguousDeviceResultError(
                            f"{self._device_name}.{command_name} produced an ambiguous physical result",
                            correlation_id=correlation_id,
                            idempotency_key=idempotency_key,
                        )
                    return result

                if result_fault:
                    self._activate_fault(
                        result_fault,
                        f"{self._device_name}.{command_name} failed",
                        critical=True,
                        command_name=command_name,
                        correlation_id=correlation_id,
                        idempotency_key=idempotency_key,
                        attempt=attempt,
                    )
                    if cache_key is not None:
                        self._cache_set(cache_key, result)
                    return result

                self._heartbeat(
                    state=success_state,
                    command_name=command_name,
                    correlation_id=correlation_id,
                    idempotency_key=idempotency_key,
                    attempts=attempt,
                    recovered=attempt > 1,
                    reconciliation_status=reconciliation.status.value,
                )
                if cache_key is not None:
                    self._cache_set(cache_key, result)
                return result
            except DeviceCommandError as exc:
                last_error = exc
                if self._should_retry(exc, active_policy) and attempt < max_attempts:
                    self._heartbeat(
                        state=DeviceOperationalState.DEGRADED,
                        command_name=command_name,
                        correlation_id=correlation_id,
                        idempotency_key=idempotency_key,
                        fault_code=exc.fault_code,
                        attempt=attempt,
                        retrying=True,
                    )
                    continue
                self._activate_terminal_exception(
                    command_name,
                    exc,
                    correlation_id=correlation_id,
                    idempotency_key=idempotency_key,
                    attempt=attempt,
                    retry_attempted=max_attempts > 1,
                )
                raise
            except asyncio.TimeoutError:
                last_error = DeviceCommandTimeoutError(
                    f"{self._device_name}.{command_name} timed out after {active_policy.timeout_s}s",
                    correlation_id=correlation_id,
                    idempotency_key=idempotency_key,
                )
                if active_policy.is_retryable(last_error.fault_code) and attempt < max_attempts:
                    self._heartbeat(
                        state=DeviceOperationalState.DEGRADED,
                        command_name=command_name,
                        correlation_id=correlation_id,
                        idempotency_key=idempotency_key,
                        fault_code=last_error.fault_code,
                        attempt=attempt,
                        retrying=True,
                    )
                    continue
                self._activate_terminal_exception(
                    command_name,
                    last_error,
                    correlation_id=correlation_id,
                    idempotency_key=idempotency_key,
                    attempt=attempt,
                    retry_attempted=max_attempts > 1,
                )
                raise last_error
            except DeviceAdapterError as exc:
                last_error = DeviceCommandError(
                    str(exc),
                    fault_code=DeviceFaultCode.DEVICE_UNAVAILABLE.value,
                    correlation_id=correlation_id,
                    idempotency_key=idempotency_key,
                )
                self._activate_terminal_exception(
                    command_name,
                    last_error,
                    correlation_id=correlation_id,
                    idempotency_key=idempotency_key,
                    attempt=attempt,
                    retry_attempted=False,
                )
                raise

        if last_error is None:
            raise DeviceCommandError(
                f"{self._device_name}.{command_name} failed without a concrete fault",
                fault_code=DeviceFaultCode.DEVICE_UNAVAILABLE.value,
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
            )
        raise last_error

    async def _run_once(
        self,
        operation: CommandOperation[T],
        policy: DeviceCommandPolicy,
    ) -> T:
        if policy.timeout_s is None:
            return await operation()
        return await asyncio.wait_for(operation(), timeout=policy.timeout_s)

    async def _reconcile(
        self,
        result: T,
        reconcile: StateReconciler[T] | None,
    ) -> PhysicalStateReconciliation:
        if reconcile is None:
            return PhysicalStateReconciliation()
        reconciliation = reconcile(result)
        if inspect.isawaitable(reconciliation):
            return await reconciliation
        return reconciliation

    def _should_retry(self, exc: DeviceCommandError, policy: DeviceCommandPolicy) -> bool:
        if exc.retryable is not None:
            return exc.retryable and exc.fault_code not in policy.non_retryable_faults
        return policy.is_retryable(exc.fault_code)

    def _activate_terminal_exception(
        self,
        command_name: str,
        exc: DeviceCommandError,
        *,
        correlation_id: str | None,
        idempotency_key: str | None,
        attempt: int,
        retry_attempted: bool,
    ) -> None:
        if retry_attempted:
            exhausted = DeviceCommandRetryExhaustedError(
                f"{self._device_name}.{command_name} exhausted retry policy",
                cause_fault_code=exc.fault_code,
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
            )
            self._activate_fault(
                exhausted.fault_code,
                str(exhausted),
                critical=True,
                command_name=command_name,
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
                attempt=attempt,
                cause_fault_code=exhausted.cause_fault_code,
                manual_review_required=exc.manual_review_required,
            )
            return
        self._activate_fault(
            exc.fault_code,
            str(exc),
            critical=True,
            command_name=command_name,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            attempt=attempt,
            ambiguous=exc.ambiguous,
            manual_review_required=exc.manual_review_required,
        )

    def _activate_ambiguous_fault(
        self,
        command_name: str,
        *,
        correlation_id: str | None,
        idempotency_key: str | None,
        attempt: int,
        reconciliation: PhysicalStateReconciliation,
        result_fault: str | None,
    ) -> None:
        code = result_fault or DeviceFaultCode.AMBIGUOUS_PHYSICAL_RESULT.value
        if reconciliation.status is PhysicalReconciliationStatus.MISMATCH:
            code = DeviceFaultCode.PHYSICAL_STATE_MISMATCH.value
        self._activate_fault(
            code,
            reconciliation.message or f"{self._device_name}.{command_name} requires manual review",
            critical=True,
            command_name=command_name,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            attempt=attempt,
            reconciliation_status=reconciliation.status.value,
            observed_state=dict(reconciliation.observed_state),
            expected_state=dict(reconciliation.expected_state),
            ambiguous=True,
            manual_review_required=True,
        )

    def _cache_set(self, key: str, value: Any) -> None:
        self._idempotency_cache[key] = value
        self._idempotency_cache.move_to_end(key)
        if len(self._idempotency_cache) > self._idempotency_cache_maxsize:
            self._idempotency_cache.popitem(last=False)

    def _copy_cached_value(self, value: T) -> T:
        if isinstance(value, dict):
            return cast(T, value.copy())
        return value

    def _cache_key(self, command_name: str, idempotency_key: str | None) -> str | None:
        if idempotency_key is None:
            return None
        return f"{self._device_name}:{command_name}:{idempotency_key}"

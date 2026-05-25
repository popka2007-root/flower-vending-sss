"""Device-layer exceptions."""

from __future__ import annotations

from flower_vending.devices.contracts import DeviceFaultCode


class DeviceAdapterError(RuntimeError):
    """Base exception for device adapter failures."""


class DeviceNotStartedError(DeviceAdapterError):
    """Raised when an operation requires a running adapter."""


class UnsupportedDeviceOperationError(DeviceAdapterError):
    """Raised when the configured device or protocol cannot perform an operation."""


class HardwareConfirmationRequiredError(DeviceAdapterError):
    """Raised when a real hardware or protocol detail must be confirmed first."""


class TransportIOError(DeviceAdapterError):
    """Raised on low-level transport read or write failures."""


class DeviceProtocolError(DeviceAdapterError):
    """Raised on protocol-level communication failures."""


class ProtocolDecodeError(DeviceAdapterError):
    """Raised when a wire-level message cannot be decoded safely."""


class ConfigurationError(DeviceAdapterError):
    """Raised when an adapter configuration is incomplete or inconsistent."""


class DeviceCommandError(DeviceAdapterError):
    """Raised when a normalized device command fails."""

    def __init__(
        self,
        message: str,
        *,
        fault_code: str = DeviceFaultCode.DEVICE_UNAVAILABLE.value,
        correlation_id: str | None = None,
        idempotency_key: str | None = None,
        retryable: bool | None = None,
        ambiguous: bool = False,
        manual_review_required: bool = False,
    ) -> None:
        super().__init__(message)
        self.fault_code = fault_code
        self.correlation_id = correlation_id
        self.idempotency_key = idempotency_key
        self.retryable = retryable
        self.ambiguous = ambiguous
        self.manual_review_required = manual_review_required


class DeviceCommandTimeoutError(DeviceCommandError):
    """Raised when a command exceeds its policy timeout."""

    def __init__(
        self,
        message: str,
        *,
        correlation_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> None:
        super().__init__(
            message,
            fault_code=DeviceFaultCode.COMMAND_TIMEOUT.value,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            retryable=True,
        )


class DeviceCommandRetryExhaustedError(DeviceCommandError):
    """Raised after all retry attempts are exhausted."""

    def __init__(
        self,
        message: str,
        *,
        cause_fault_code: str,
        correlation_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> None:
        super().__init__(
            message,
            fault_code=DeviceFaultCode.COMMAND_RETRY_EXHAUSTED.value,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            retryable=False,
        )
        self.cause_fault_code = cause_fault_code


class AmbiguousDeviceResultError(DeviceCommandError):
    """Raised when command side effects cannot be reconciled automatically."""

    def __init__(
        self,
        message: str,
        *,
        correlation_id: str | None = None,
        idempotency_key: str | None = None,
        fault_code: str = DeviceFaultCode.AMBIGUOUS_PHYSICAL_RESULT.value,
    ) -> None:
        super().__init__(
            message,
            fault_code=fault_code,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            retryable=False,
            ambiguous=True,
            manual_review_required=True,
        )

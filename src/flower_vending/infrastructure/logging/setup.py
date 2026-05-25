"""Structured logging configuration for the vending machine runtime."""

from __future__ import annotations

import atexit
import contextvars
import json
import logging
import logging.handlers
import queue
from collections.abc import Mapping, MutableMapping
from pathlib import Path
from typing import Any

from flower_vending.infrastructure.config.models import LoggingConfig


_correlation_ctx: contextvars.ContextVar[str] = contextvars.ContextVar(
    "flower_vending_correlation_id", default=""
)
_transaction_ctx: contextvars.ContextVar[str] = contextvars.ContextVar(
    "flower_vending_transaction_id", default=""
)


def set_log_context(
    *, correlation_id: str | None = None, transaction_id: str | None = None
) -> None:
    if correlation_id is not None:
        _correlation_ctx.set(correlation_id)
    if transaction_id is not None:
        _transaction_ctx.set(transaction_id)


_ACTIVE_LISTENERS: list[logging.handlers.QueueListener] = []
_HANDLERS: list[logging.Handler] = []

_STANDARD_FIELDS = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
    "message",
    "asctime",
}


class JsonLogFormatter(logging.Formatter):
    def __init__(self, *, sensitive_fields: tuple[str, ...] = ()) -> None:
        super().__init__()
        self._sensitive_fields = set(sensitive_fields)

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key.startswith("_") or key in _STANDARD_FIELDS:
                continue
            payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        for field in self._sensitive_fields:
            if field in payload:
                payload[field] = "***"
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)


class StructuredLoggerAdapter(logging.LoggerAdapter[logging.Logger]):
    def bind(self, **extra: Any) -> "StructuredLoggerAdapter":
        merged = dict(self._base_extra())
        merged.update(extra)
        return StructuredLoggerAdapter(self.logger, merged)

    def process(
        self, msg: object, kwargs: MutableMapping[str, Any]
    ) -> tuple[object, MutableMapping[str, Any]]:
        extra = dict(self._base_extra())
        ctx_correlation = _correlation_ctx.get()
        if ctx_correlation:
            extra.setdefault("correlation_id", ctx_correlation)
        ctx_transaction = _transaction_ctx.get()
        if ctx_transaction:
            extra.setdefault("transaction_id", ctx_transaction)
        supplied_extra = kwargs.pop("extra", {})
        if isinstance(supplied_extra, Mapping):
            extra.update(supplied_extra)
        kwargs["extra"] = extra
        return msg, kwargs

    def _base_extra(self) -> Mapping[str, object]:
        return {} if self.extra is None else self.extra


def close_logging(logger: StructuredLoggerAdapter | logging.Logger) -> None:
    target = logger.logger if isinstance(logger, StructuredLoggerAdapter) else logger
    for handler in list(target.handlers):
        _safe_flush_close(handler)
        target.removeHandler(handler)
    for listener in reversed(_ACTIVE_LISTENERS):
        listener.stop()
    _ACTIVE_LISTENERS.clear()
    for handler in _HANDLERS:
        _safe_flush_close(handler)
    _HANDLERS.clear()


def _safe_flush_close(handler: logging.Handler) -> None:
    try:
        handler.flush()
    except OSError:
        pass
    try:
        handler.close()
    except OSError:
        pass


def configure_logging(
    config: LoggingConfig, *, logger_name: str = "flower_vending"
) -> StructuredLoggerAdapter:
    log_directory = Path(config.directory)
    log_directory.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(logger_name)
    logger.setLevel(getattr(logging, config.level.upper(), logging.INFO))
    close_logging(logger)
    logger.propagate = False

    formatter: logging.Formatter
    formatter = (
        JsonLogFormatter(sensitive_fields=config.sensitive_fields)
        if config.json_logs
        else logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )

    file_handler: logging.Handler = logging.handlers.RotatingFileHandler(
        log_directory / config.filename,
        maxBytes=config.rotation.max_bytes,
        backupCount=config.rotation.backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    handlers: list[logging.Handler] = [file_handler]

    if config.stderr:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        handlers.append(stream_handler)

    if config.async_log:
        log_queue: queue.Queue[logging.LogRecord] = queue.Queue(-1)
        queue_handler = logging.handlers.QueueHandler(log_queue)
        logger.addHandler(queue_handler)
        _HANDLERS.extend(handlers)
        listener = logging.handlers.QueueListener(log_queue, *handlers, respect_handler_level=True)
        listener.start()
        _ACTIVE_LISTENERS.append(listener)
        atexit.register(listener.stop)
    else:
        for handler in handlers:
            logger.addHandler(handler)
            _HANDLERS.append(handler)

    return StructuredLoggerAdapter(logger, {})

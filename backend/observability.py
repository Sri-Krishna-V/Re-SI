"""Observability helpers for request correlation, logging, and optional tracing."""

from __future__ import annotations

import contextlib
import contextvars
import logging
import os
import uuid
from typing import Any, Dict, Iterator, Optional

_request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-"
)

_otel_trace_api = None
_otel_initialized = False
_fastapi_instrumented = False
OBS_LOGGER_NAME = "observability"


def _is_truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


class RequestContextFilter(logging.Filter):
    """Inject request context fields into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = _request_id_var.get()
        if not hasattr(record, "session_id"):
            record.session_id = "-"
        if not hasattr(record, "event_type"):
            record.event_type = "-"
        if not hasattr(record, "duration_ms"):
            record.duration_ms = "-"
        return True


def configure_logging() -> None:
    """Apply structured logging format with context fields."""
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    log_format = (
        "%(asctime)s %(levelname)s "
        "[request_id=%(request_id)s session_id=%(session_id)s "
        "event=%(event_type)s duration_ms=%(duration_ms)s] "
        "%(name)s: %(message)s"
    )

    root_logger = logging.getLogger()
    if not root_logger.handlers:
        logging.basicConfig(level=level, format=log_format)
        root_logger = logging.getLogger()
    else:
        root_logger.setLevel(level)
        formatter = logging.Formatter(log_format)
        for handler in root_logger.handlers:
            handler.setFormatter(formatter)

    for handler in root_logger.handlers:
        has_filter = any(
            isinstance(existing_filter, RequestContextFilter)
            for existing_filter in handler.filters
        )
        if not has_filter:
            handler.addFilter(RequestContextFilter())


def set_request_id(request_id: Optional[str] = None) -> contextvars.Token:
    """Set the request context ID for current task context."""
    resolved = request_id or str(uuid.uuid4())
    return _request_id_var.set(resolved)


def get_request_id() -> str:
    return _request_id_var.get()


def reset_request_id(token: contextvars.Token) -> None:
    _request_id_var.reset(token)


def event_extra(
    *,
    session_id: Optional[str] = None,
    event_type: Optional[str] = None,
    duration_ms: Optional[float] = None,
    **fields: Any,
) -> Dict[str, Any]:
    """Build a standard extra payload for structured logs."""
    extra: Dict[str, Any] = {
        "session_id": session_id or "-",
        "event_type": event_type or "-",
        "duration_ms": duration_ms if duration_ms is not None else "-",
    }
    extra.update(fields)
    return extra


def init_tracing(service_name: str = "re-si-backend") -> bool:
    """Initialize OpenTelemetry when enabled via environment variables."""
    global _otel_trace_api, _otel_initialized

    logger = logging.getLogger(OBS_LOGGER_NAME)

    if _otel_initialized:
        return _otel_trace_api is not None
    _otel_initialized = True

    if not _is_truthy(os.getenv("OBSERVABILITY_OTEL_ENABLED", "false")):
        logger.info(
            "OpenTelemetry is disabled",
            extra=event_extra(event_type="otel_init"),
        )
        return False

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import (
            BatchSpanProcessor,
            ConsoleSpanExporter,
            SimpleSpanProcessor,
        )
    except Exception as exc:
        logger.warning(
            "OpenTelemetry packages are unavailable; tracing disabled: %s",
            exc,
            extra=event_extra(event_type="otel_init"),
        )
        return False

    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.name": os.getenv("OTEL_SERVICE_NAME", service_name),
            }
        )
    )

    exporter_added = False
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    if endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )

            insecure = _is_truthy(
                os.getenv("OTEL_EXPORTER_OTLP_INSECURE", "true"))
            exporter = OTLPSpanExporter(endpoint=endpoint, insecure=insecure)
            provider.add_span_processor(BatchSpanProcessor(exporter))
            exporter_added = True
        except Exception as exc:
            logger.warning(
                "Failed to configure OTLP exporter: %s",
                exc,
                extra=event_extra(event_type="otel_exporter"),
            )

    if _is_truthy(os.getenv("OBSERVABILITY_OTEL_CONSOLE", "false")):
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
        exporter_added = True

    if not exporter_added:
        logger.warning(
            "Tracing enabled but no exporter configured; spans will not be exported",
            extra=event_extra(event_type="otel_exporter"),
        )

    trace.set_tracer_provider(provider)
    _otel_trace_api = trace
    logger.info(
        "OpenTelemetry initialized",
        extra=event_extra(event_type="otel_init"),
    )
    return True


def instrument_fastapi(app: Any) -> bool:
    """Instrument FastAPI app when OpenTelemetry is active."""
    global _fastapi_instrumented

    logger = logging.getLogger(OBS_LOGGER_NAME)

    if _fastapi_instrumented or _otel_trace_api is None:
        return _fastapi_instrumented

    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
        _fastapi_instrumented = True
        logger.info(
            "FastAPI instrumentation enabled",
            extra=event_extra(event_type="otel_fastapi"),
        )
        return True
    except Exception as exc:
        logger.warning(
            "Failed to instrument FastAPI app: %s",
            exc,
            extra=event_extra(event_type="otel_fastapi"),
        )
        return False


@contextlib.contextmanager
def traced_span(
    name: str,
    attributes: Optional[Dict[str, Any]] = None,
) -> Iterator[Any]:
    """Create a span if tracing is enabled, otherwise no-op."""
    if _otel_trace_api is None:
        yield None
        return

    tracer = _otel_trace_api.get_tracer("re-si")
    with tracer.start_as_current_span(name) as span:
        if attributes:
            for key, value in attributes.items():
                if value is not None:
                    span.set_attribute(key, value)
        yield span


"""Observability helpers for logging, request correlation, and optional tracing.

This module is designed to fail open: missing telemetry dependencies or exporter
configuration should never break request handling.
"""


_request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-")
_tracing_initialized = False
_trace_api = None
_fastapi_instrumented = False


class RequestContextFilter(logging.Filter):
    """Inject request and event context into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = _request_id_var.get()
        if not hasattr(record, "session_id"):
            record.session_id = "-"
        if not hasattr(record, "event_type"):
            record.event_type = "-"
        if not hasattr(record, "duration_ms"):
            record.duration_ms = "-"
        return True


def _is_truthy(value: Optional[str], default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_flag(name: str, default: bool = False) -> bool:
    return _is_truthy(os.getenv(name), default)


def configure_logging() -> None:
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_format = (
        "%(asctime)s %(levelname)s "
        "[request_id=%(request_id)s session_id=%(session_id)s "
        "event=%(event_type)s duration_ms=%(duration_ms)s] "
        "%(name)s: %(message)s"
    )

    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(level=level, format=log_format)
    else:
        root.setLevel(level)
        formatter = logging.Formatter(log_format)
        for handler in root.handlers:
            handler.setFormatter(formatter)

    for handler in root.handlers:
        has_filter = any(isinstance(f, RequestContextFilter)
                         for f in handler.filters)
        if not has_filter:
            handler.addFilter(RequestContextFilter())


def set_request_id(request_id: Optional[str] = None) -> contextvars.Token[str]:
    value = request_id or str(uuid.uuid4())
    return _request_id_var.set(value)


def get_request_id() -> str:
    return _request_id_var.get()


def reset_request_id(token: contextvars.Token[str]) -> None:
    _request_id_var.reset(token)


def event_extra(
    session_id: Optional[str] = None,
    event_type: Optional[str] = None,
    duration_ms: Optional[float] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    extra: Dict[str, Any] = {
        "session_id": session_id or "-",
        "event_type": event_type or "-",
        "duration_ms": duration_ms if duration_ms is not None else "-",
    }
    extra.update(kwargs)
    return extra


def init_tracing(service_name: str = "re-si-backend") -> bool:
    """Initialize OpenTelemetry if enabled via env.

    Requires OBSERVABILITY_OTEL_ENABLED=true. If optional dependencies are missing,
    tracing is disabled and the app keeps running.
    """
    global _tracing_initialized, _trace_api

    if _tracing_initialized:
        return _trace_api is not None

    _tracing_initialized = True
    logger = logging.getLogger(__name__)

    if not env_flag("OBSERVABILITY_OTEL_ENABLED", default=False):
        logger.info(
            "OpenTelemetry is disabled (OBSERVABILITY_OTEL_ENABLED=false)",
            extra=event_extra(event_type="otel_init"),
        )
        return False

    try:
        from opentelemetry import trace  # type: ignore
        from opentelemetry.sdk.resources import Resource  # type: ignore
        from opentelemetry.sdk.trace import TracerProvider  # type: ignore
        from opentelemetry.sdk.trace.export import BatchSpanProcessor  # type: ignore
    except Exception as exc:
        logger.warning(
            "OpenTelemetry packages are not installed; tracing disabled: %s",
            exc,
            extra=event_extra(event_type="otel_init"),
        )
        return False

    provider = TracerProvider(
        resource=Resource.create(
            {"service.name": os.getenv("OTEL_SERVICE_NAME", service_name)})
    )

    exporter_configured = False
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    if endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (  # type: ignore
                OTLPSpanExporter,
            )

            insecure = env_flag("OTEL_EXPORTER_OTLP_INSECURE", default=True)
            otlp_exporter = OTLPSpanExporter(
                endpoint=endpoint, insecure=insecure)
            provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
            exporter_configured = True
        except Exception as exc:
            logger.warning(
                "OTLP exporter setup failed; tracing will not export remotely: %s",
                exc,
                extra=event_extra(event_type="otel_init"),
            )

    if env_flag("OBSERVABILITY_OTEL_CONSOLE", default=False):
        try:
            from opentelemetry.sdk.trace.export import (  # type: ignore
                ConsoleSpanExporter,
                SimpleSpanProcessor,
            )

            provider.add_span_processor(
                SimpleSpanProcessor(ConsoleSpanExporter()))
            exporter_configured = True
        except Exception as exc:
            logger.warning(
                "Console span exporter setup failed: %s",
                exc,
                extra=event_extra(event_type="otel_init"),
            )

    try:
        trace.set_tracer_provider(provider)
    except Exception as exc:
        logger.warning(
            "Tracer provider setup failed; tracing disabled: %s",
            exc,
            extra=event_extra(event_type="otel_init"),
        )
        return False

    _trace_api = trace

    if exporter_configured:
        logger.info(
            "OpenTelemetry initialized with exporter",
            extra=event_extra(event_type="otel_init"),
        )
    else:
        logger.info(
            "OpenTelemetry initialized without exporter (spans not exported)",
            extra=event_extra(event_type="otel_init"),
        )

    return True


def instrument_fastapi(app: Any) -> bool:
    global _fastapi_instrumented

    if _fastapi_instrumented or _trace_api is None:
        return False

    logger = logging.getLogger(__name__)
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor  # type: ignore

        FastAPIInstrumentor.instrument_app(app)
        _fastapi_instrumented = True
        logger.info(
            "FastAPI OpenTelemetry instrumentation enabled",
            extra=event_extra(event_type="otel_init"),
        )
        return True
    except Exception as exc:
        logger.warning(
            "FastAPI OpenTelemetry instrumentation not available: %s",
            exc,
            extra=event_extra(event_type="otel_init"),
        )
        return False


def is_tracing_enabled() -> bool:
    return _trace_api is not None


@contextlib.contextmanager
def traced_span(name: str, attributes: Optional[Dict[str, Any]] = None) -> Iterator[Any]:
    """Create a span if tracing is initialized, else behave as a no-op context."""
    if _trace_api is None:
        yield None
        return

    tracer = _trace_api.get_tracer("re-si")
    with tracer.start_as_current_span(name) as span:
        if attributes:
            for key, value in attributes.items():
                if value is not None:
                    span.set_attribute(key, value)
        yield span

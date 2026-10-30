import json
import logging
import os
from datetime import datetime, timezone

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# Custom business metric (a no-op until setup_telemetry() installs a provider)
meter = metrics.get_meter("incident-hub")
incidents_created = meter.create_counter(
    "incidents_created", description="Number of incidents created"
)
incidents_resolved = meter.create_counter(
    "incidents_resolved", description="Number of incidents resolved"
)


class JsonFormatter(logging.Formatter):
    """Structured JSON logs that carry the current trace id."""

    def format(self, record):
        payload = {
            "time": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        ctx = trace.get_current_span().get_span_context()
        if ctx.is_valid:
            payload["trace_id"] = format(ctx.trace_id, "032x")
            payload["span_id"] = format(ctx.span_id, "016x")
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def _setup_logging():
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    app_logger = logging.getLogger("incident-hub")
    app_logger.setLevel(logging.INFO)
    app_logger.handlers = [handler]
    app_logger.propagate = False
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        for h in logging.getLogger(name).handlers:
            h.setFormatter(JsonFormatter())


def setup_telemetry(app, engine):
    _setup_logging()

    # Lets tests and local runs without a collector skip OTel entirely
    if os.getenv("OTEL_ENABLED", "true").lower() == "false":
        return

    resource = Resource.create(
        {"service.name": os.getenv("OTEL_SERVICE_NAME", "incident-hub-backend")}
    )

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(tracer_provider)

    reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(), export_interval_millis=10000
    )
    metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[reader]))

    FastAPIInstrumentor.instrument_app(app, excluded_urls="health")
    SQLAlchemyInstrumentor().instrument(engine=engine)
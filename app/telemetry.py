"""Timing and tracing.

`step(name, timings)` always records how long a step took (shown in the UI), and also
creates an OpenTelemetry span. Spans are only exported when OTEL_EXPORTER_OTLP_ENDPOINT
is set, for example by `./start.sh tracing`, which also starts Jaeger at http://localhost:16686.
"""
import logging
import os
import time
from contextlib import contextmanager

log = logging.getLogger(__name__)

try:
    from opentelemetry import trace

    _tracer = trace.get_tracer("confpilot")
except ImportError:  # tracing packages are optional
    trace = None
    _tracer = None


def setup(app):
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint or trace is None:
        return False
    try:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.elasticsearch import ElasticsearchInstrumentor
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider = TracerProvider(resource=Resource.create(
            {"service.name": os.getenv("OTEL_SERVICE_NAME", "confpilot")}))
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True)))
        trace.set_tracer_provider(provider)
        ElasticsearchInstrumentor().instrument()
        FastAPIInstrumentor.instrument_app(app, excluded_urls="healthz,static")
        log.info("OpenTelemetry tracing on, exporting to %s", endpoint)
        return True
    except Exception as exc:
        log.warning("Tracing disabled: %s", exc)
        return False


@contextmanager
def step(name, timings=None, **attrs):
    start = time.perf_counter()
    if _tracer is None:
        try:
            yield
        finally:
            if timings is not None:
                timings[name] = round((time.perf_counter() - start) * 1000)
        return
    with _tracer.start_as_current_span(name) as span:
        for k, v in attrs.items():
            span.set_attribute(k, v)
        try:
            yield
        finally:
            if timings is not None:
                timings[name] = round((time.perf_counter() - start) * 1000)

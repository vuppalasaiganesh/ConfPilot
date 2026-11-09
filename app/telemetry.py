"""OpenTelemetry: traces, metrics and logs.

Where telemetry goes (first match wins):
  1. Dash0:  set DASH0_AUTH_TOKEN and DASH0_OTLP_ENDPOINT (optional DASH0_DATASET) in .env.
  2. Any OTLP endpoint: OTEL_EXPORTER_OTLP_ENDPOINT, e.g. Jaeger via `./start.sh tracing`.
  3. Nowhere: spans and metrics are no-ops, but step timings still show in the UI.

`step(name, timings)` times a step for the UI and wraps it in a span.
`record_*` helpers emit the app's own metrics (search latency, LLM calls, fallbacks).
"""
import logging
import os
import time
from contextlib import contextmanager

log = logging.getLogger(__name__)
SERVICE = os.getenv("OTEL_SERVICE_NAME", "confpilot")
VERSION = "2026.11.09-9"

try:
    from opentelemetry import metrics, trace

    _tracer = trace.get_tracer("confpilot")
    _meter = metrics.get_meter("confpilot")
except ImportError:  # telemetry packages are optional
    trace = metrics = _tracer = _meter = None

_instruments = {}
DESTINATION = None  # "dash0", "otlp" or None


def _target():
    """(endpoint, headers, label) or None."""
    token = os.getenv("DASH0_AUTH_TOKEN", "").strip()
    endpoint = os.getenv("DASH0_OTLP_ENDPOINT", "").strip()
    if token and endpoint:
        headers = {"authorization": f"Bearer {token.removeprefix('Bearer ').strip()}"}
        if os.getenv("DASH0_DATASET", "").strip():
            headers["dash0-dataset"] = os.getenv("DASH0_DATASET").strip()
        return endpoint, headers, "dash0"
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    if endpoint:
        return endpoint, {}, "otlp"
    return None


def setup(app):
    global DESTINATION
    target = _target()
    if not target or trace is None:
        return False
    endpoint, headers, label = target
    insecure = endpoint.startswith("http://")
    try:
        from opentelemetry._logs import set_logger_provider
        from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.elasticsearch import ElasticsearchInstrumentor
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
        from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource.create({
            "service.name": SERVICE,
            "service.version": VERSION,
            "deployment.environment": os.getenv("DEPLOY_ENV", "local"),
            # Set in Kubernetes via the downward API, so Dash0/Radar can link telemetry to the pod.
            **{k: v for k, v in {"k8s.pod.name": os.getenv("POD_NAME"),
                                  "k8s.namespace.name": os.getenv("POD_NAMESPACE"),
                                  "k8s.node.name": os.getenv("NODE_NAME")}.items() if v},
        })
        kw = {"endpoint": endpoint, "headers": headers, "insecure": insecure}

        tp = TracerProvider(resource=resource)
        tp.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(**kw)))
        trace.set_tracer_provider(tp)

        if label == "dash0":  # Jaeger only accepts traces
            reader = PeriodicExportingMetricReader(OTLPMetricExporter(**kw), export_interval_millis=15000)
            metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[reader]))
            lp = LoggerProvider(resource=resource)
            lp.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter(**kw)))
            set_logger_provider(lp)
            logging.getLogger().addHandler(LoggingHandler(level=logging.INFO, logger_provider=lp))

        ElasticsearchInstrumentor().instrument()
        FastAPIInstrumentor.instrument_app(app, excluded_urls="healthz,static")
        DESTINATION = label
        log.info("OpenTelemetry on: sending %s to %s", "traces, metrics and logs" if label == "dash0" else "traces",
                 endpoint)
        return True
    except Exception as exc:
        log.warning("Telemetry disabled: %s", exc)
        return False


def _instrument(kind, name, **kw):
    if _meter is None:
        return None
    if name not in _instruments:
        _instruments[name] = getattr(_meter, kind)(name, **kw)
    return _instruments[name]


def record_llm_call(model, outcome, seconds):
    """outcome: ok | busy | retired | rejected | error"""
    c = _instrument("create_counter", "confpilot.llm.calls", description="LLM calls by model and outcome")
    h = _instrument("create_histogram", "confpilot.llm.duration", unit="s", description="LLM call latency")
    if c:
        c.add(1, {"llm.model": model, "outcome": outcome})
        h.record(seconds, {"llm.model": model, "outcome": outcome})


def record_fallback(reason):
    c = _instrument("create_counter", "confpilot.ai.fallbacks",
                    description="Requests answered with rule-based fallback because the AI failed")
    if c:
        c.add(1, {"reason": reason})


def record_search(seconds, results):
    h = _instrument("create_histogram", "confpilot.search.duration", unit="s", description="Hybrid search latency")
    c = _instrument("create_histogram", "confpilot.search.results", description="Talks returned per search")
    if h:
        h.record(seconds)
        c.record(results)


def record_summary(seconds):
    h = _instrument("create_histogram", "confpilot.summary.duration", unit="s", description="Talk summary latency")
    if h:
        h.record(seconds)


def current_span():
    return trace.get_current_span() if trace else None


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

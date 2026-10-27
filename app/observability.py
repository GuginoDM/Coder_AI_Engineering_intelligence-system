import os
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from openinference.instrumentation.langchain import LangChainInstrumentor

def setup_observability():
    """Configura OpenTelemetry para enviar trazas al contenedor de Phoenix en Docker."""
    endpoint = os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "http://phoenix:6006/v1/traces")
    
    provider = TracerProvider()

    # Configuración optimizada para producción
    processor = BatchSpanProcessor(
        span_exporter=OTLPSpanExporter(endpoint=endpoint),
        schedule_delay_millis=5000,     # Envía lotes cada 5 segundos
        max_export_batch_size=512       # Envía hasta 512 trazas por lote
    )

    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)

    LangChainInstrumentor().instrument(tracer_provider=provider)
    print(f" OpenTelemetry exportando trazas hacia Phoenix en: {endpoint}")
"""Reading the spans that the `exported_spans` fixture keeps, for the guardrail tests."""

from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter


def spans_as_text(exporter: InMemorySpanExporter) -> str:
    """Write the names, attributes, and event names of the exported spans as one text.

    Args:
        exporter: The exporter of `exported_spans`.

    Returns:
        The text that a guardrail test searches.
    """
    return repr(
        [
            (span.name, dict(span.attributes or {}), [event.name for event in span.events])
            for span in exporter.get_finished_spans()
        ]
    )

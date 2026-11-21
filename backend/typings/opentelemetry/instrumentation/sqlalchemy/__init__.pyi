"""Type stub for the part of `opentelemetry-instrumentation-sqlalchemy` that backend uses.

The package ships no type information (no `py.typed`), so pyright in strict mode needs this
stub (CODE-27). It declares only the calls of `platform/adapters/telemetry.py`, with the
keyword arguments that the package reads in `SQLAlchemyInstrumentor._instrument`.
"""

from opentelemetry.sdk.trace import TracerProvider
from sqlalchemy.engine import Engine

__all__ = ["SQLAlchemyInstrumentor"]

class SQLAlchemyInstrumentor:
    """Add a span for every statement of an engine."""

    def instrument(
        self, *, engine: Engine, tracer_provider: TracerProvider, enable_commenter: bool
    ) -> None:
        """Instrument one engine."""

    def uninstrument(self) -> None:
        """Remove the instrumentation of every engine."""

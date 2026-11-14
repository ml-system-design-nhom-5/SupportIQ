"""The port for the trace of the current work (LOG-04, LOG-05)."""

from typing import NewType, Protocol

# A W3C trace ID as 32 lowercase hexadecimal characters. Internal data.
TraceId = NewType("TraceId", str)
TRACE_ID_FORMAT = "032x"


class TraceContext(Protocol):
    """Tell the trace of the work in progress: the request, continued or started."""

    def current_trace_id(self) -> TraceId:
        """Return the trace ID of the current work.

        Returns:
            The trace ID, as 32 lowercase hexadecimal characters.
        """
        ...

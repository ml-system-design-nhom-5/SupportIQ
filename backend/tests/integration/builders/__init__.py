"""Builders of integration test data, inserted as the owner with sensible defaults (TEST-05).

`supportiq_app` cannot insert admin accounts, customer accounts, or commerce data, so the
builders connect as the owner.
IDs and times come from a counter, so a test run is deterministic (TEST-14). A test overrides
only the fields that matter to it. Every value is synthetic (TEST-18).

Each area has its own module: `accounts`, `commerce`, `tickets`, and `suggestions` hold the
specs of their rows and the class that inserts them, and `DatabaseBuilder` is the one entry
point that every test uses.
"""

from tests.integration.builders.accounts import UNUSABLE_PASSWORD_HASH, AccountSpec
from tests.integration.builders.commerce import (
    CURRENCY,
    LineSpec,
    OrderSpec,
    RefundSpec,
    ShipmentSpec,
)
from tests.integration.builders.database_builder import DatabaseBuilder
from tests.integration.builders.suggestions import (
    FAILED_SUGGESTION,
    SUGGESTION_TRACE_ID,
    SuggestionPartSpec,
    SuggestionSpec,
)
from tests.integration.builders.tickets import TicketSpec

__all__ = [
    "CURRENCY",
    "FAILED_SUGGESTION",
    "SUGGESTION_TRACE_ID",
    "UNUSABLE_PASSWORD_HASH",
    "AccountSpec",
    "DatabaseBuilder",
    "LineSpec",
    "OrderSpec",
    "RefundSpec",
    "ShipmentSpec",
    "SuggestionPartSpec",
    "SuggestionSpec",
    "TicketSpec",
]

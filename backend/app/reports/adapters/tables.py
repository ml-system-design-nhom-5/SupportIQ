"""The columns that reports reads, as SQLAlchemy Core tables of its own (ARCH-17, PY-39).

reports owns no table. It declares only the columns it reads, so no query of reports can name
a message body, a reply body, a note, or the pseudonym map: those columns and that table do not
exist here (SEC-37). The two Confidential columns that it declares, `suggestions.request` and
`suggestion_parts.result`, hold pseudonymized text, and only the decision-record export reads
them (SEC-33).
"""

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Integer,
    MetaData,
    Numeric,
    Table,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB

_METADATA = MetaData()

TICKETS = Table(
    "tickets",
    _METADATA,
    Column("ticket_number", BigInteger, primary_key=True),
    Column("ticket_id", Text),
    Column("handling_mode", Text),
    Column("created_at", DateTime(timezone=True)),
    Column("handling_started_at", DateTime(timezone=True)),
    Column("closed_at", DateTime(timezone=True)),
    Column("current_suggestion_id", Uuid()),
    Column("study_pair_id", Text),
    Column("study_batch", Text),
)
STAFF_DECISIONS = Table(
    "staff_decisions",
    _METADATA,
    Column("decision_id", Uuid(), primary_key=True),
    Column("ticket_id", Text),
    Column("decision_type", Text),
    Column("staff_reason_codes", JSONB()),
    Column("change_ratio", Numeric(4, 3, asdecimal=False)),
    Column("final_intent", Text),
    Column("is_proposal_changed", Boolean),
    Column("decided_at", DateTime(timezone=True)),
)
ESCALATIONS = Table(
    "escalations",
    _METADATA,
    Column("escalation_id", Uuid(), primary_key=True),
    Column("ticket_id", Text),
    Column("staff_reason_codes", JSONB()),
    Column("escalated_at", DateTime(timezone=True)),
)
SUGGESTIONS = Table(
    "suggestions",
    _METADATA,
    Column("suggestion_id", Uuid(), primary_key=True),
    Column("ticket_id", Text),
    Column("trigger", Text),
    Column("intent_override", Text),
    Column("created_at", DateTime(timezone=True)),
    # The exact `SuggestionRequest` sent to ai-service, absent until pseudonymization succeeded.
    Column("request", JSONB(none_as_null=True)),
)
SUGGESTION_PARTS = Table(
    "suggestion_parts",
    _METADATA,
    Column("suggestion_id", Uuid(), primary_key=True),
    Column("part", Text, primary_key=True),
    Column("status", Text),
    Column("reason_codes", JSONB()),
    Column("llm_cost_micro_usd", Integer),
    Column("completed_at", DateTime(timezone=True)),
    # The ai-service response as received, with placeholders in its text.
    Column("result", JSONB(none_as_null=True)),
)

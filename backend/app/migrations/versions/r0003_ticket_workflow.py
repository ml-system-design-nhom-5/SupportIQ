"""Add the tables of the ticket workflow: suggestions, jobs, the pseudonym map, and replies.

Revision ID: 0003
Revises: 0002

Every change comes from the backend ticket workflow design (Tables): the tables of
`suggestions`, `pseudonymization`, and `tickets`, three columns of `tickets`, the privileges of
`supportiq_app`, and the triggers that no privilege can express. `r0001` and `r0002` are never
changed (PY-40).
"""

from alembic import op

revision = "0003"
down_revision: str | None = "0002"
branch_labels: str | None = None
depends_on: str | None = None

_CREATE_TABLES = (
    # suggestions: `request` stays absent until pseudonymization succeeded (Confidential).
    """
    CREATE TABLE suggestions (
        suggestion_id uuid PRIMARY KEY,
        ticket_id text NOT NULL REFERENCES tickets (ticket_id),
        trigger text NOT NULL
            CHECK (trigger IN ('ticket_created', 'intent_override', 'kb_version_changed', 'retry')),
        intent_override text,
        requested_by_account_id uuid REFERENCES accounts (account_id),
        created_at timestamptz NOT NULL,
        trace_id text NOT NULL CHECK (trace_id ~ '^[0-9a-f]{32}$'),
        request jsonb,
        CONSTRAINT suggestions_a_request_by_staff_names_the_account
            CHECK ((trigger = 'ticket_created') = (requested_by_account_id IS NULL))
    )
    """,
    "CREATE INDEX suggestions_by_ticket ON suggestions (ticket_id, created_at)",
    """
    CREATE TABLE suggestion_parts (
        suggestion_id uuid NOT NULL REFERENCES suggestions (suggestion_id),
        part text NOT NULL CHECK (part IN ('analysis', 'draft')),
        status text NOT NULL,
        reason_codes jsonb NOT NULL CHECK (jsonb_typeof(reason_codes) = 'array'),
        release_id text,
        versions jsonb,
        latency_ms integer CHECK (latency_ms >= 0),
        llm_input_token_count integer CHECK (llm_input_token_count >= 0),
        llm_output_token_count integer CHECK (llm_output_token_count >= 0),
        llm_cost_micro_usd integer CHECK (llm_cost_micro_usd >= 0),
        mask_count_by_type jsonb,
        completed_at timestamptz,
        result jsonb,
        PRIMARY KEY (suggestion_id, part),
        CONSTRAINT suggestion_parts_status_of_the_part CHECK (
            (part = 'analysis' AND status IN ('pending', 'ready', 'unavailable', 'cancelled'))
            OR (part = 'draft' AND status IN (
                'pending', 'draft_ready', 'abstained', 'escalation_recommended',
                'llm_unavailable', 'unavailable', 'cancelled'
            ))
        ),
        CONSTRAINT suggestion_parts_final_parts_are_dated
            CHECK ((status = 'pending') = (completed_at IS NULL))
    )
    """,
    # The partial index serves the claim: the oldest job that is not done (ADR-0011, item 2).
    """
    CREATE TABLE suggestion_jobs (
        suggestion_id uuid PRIMARY KEY REFERENCES suggestions (suggestion_id),
        state text NOT NULL CHECK (state IN ('queued', 'running', 'done')),
        attempt_number integer NOT NULL CHECK (attempt_number >= 0),
        lease_expires_at timestamptz,
        created_at timestamptz NOT NULL,
        updated_at timestamptz NOT NULL,
        CONSTRAINT suggestion_jobs_running_jobs_have_a_lease
            CHECK (state <> 'running' OR lease_expires_at IS NOT NULL)
    )
    """,
    """
    CREATE INDEX suggestion_jobs_claimable
        ON suggestion_jobs (created_at, suggestion_id) WHERE state <> 'done'
    """,
    # pseudonymization (ADR-0010, Storage and lifecycle, item 3): `original_value` is
    # Confidential, and only the pseudonymization module reads the table (SEC-37).
    """
    CREATE TABLE pseudonym_map_entries (
        ticket_id text NOT NULL REFERENCES tickets (ticket_id),
        pseudonym text NOT NULL,
        pseudonym_type text NOT NULL CHECK (pseudonym_type IN (
            'NAME', 'EMAIL', 'PHONE', 'CARD', 'ADDRESS', 'ORDER_ID', 'TRACKING_ID',
            'TRANSACTION_ID', 'LITERAL'
        )),
        original_value text NOT NULL,
        created_at timestamptz NOT NULL,
        PRIMARY KEY (ticket_id, pseudonym)
    )
    """,
    """
    CREATE TABLE reply_proposals (
        proposal_id uuid PRIMARY KEY,
        ticket_id text NOT NULL REFERENCES tickets (ticket_id),
        basis text NOT NULL CHECK (basis IN ('ai_draft', 'rejected_ai_draft', 'no_ai_draft')),
        suggestion_id uuid REFERENCES suggestions (suggestion_id),
        acknowledged_warning_ids jsonb NOT NULL,
        staff_reason_codes jsonb NOT NULL,
        proposed_by_account_id uuid NOT NULL REFERENCES accounts (account_id),
        created_at timestamptz NOT NULL,
        body text NOT NULL CHECK (char_length(body) BETWEEN 1 AND 2000),
        note text
    )
    """,
    "CREATE INDEX reply_proposals_by_ticket ON reply_proposals (ticket_id, created_at)",
    # The unique `ticket_id` makes a second reply impossible (ERR-16).
    """
    CREATE TABLE replies (
        reply_id uuid PRIMARY KEY,
        ticket_id text NOT NULL UNIQUE REFERENCES tickets (ticket_id),
        basis text NOT NULL CHECK (
            basis IN ('ai_draft', 'rejected_ai_draft', 'no_ai_draft', 'reply_proposal')
        ),
        suggestion_id uuid REFERENCES suggestions (suggestion_id),
        proposal_id uuid REFERENCES reply_proposals (proposal_id),
        acknowledged_warning_ids jsonb NOT NULL,
        staff_reason_codes jsonb NOT NULL,
        sent_by_account_id uuid NOT NULL REFERENCES accounts (account_id),
        sent_at timestamptz NOT NULL,
        body text NOT NULL CHECK (char_length(body) BETWEEN 1 AND 2000),
        note text,
        CONSTRAINT replies_a_proposal_reply_names_its_proposal
            CHECK ((basis = 'reply_proposal') = (proposal_id IS NOT NULL))
    )
    """,
    """
    CREATE TABLE escalations (
        escalation_id uuid PRIMARY KEY,
        ticket_id text NOT NULL UNIQUE REFERENCES tickets (ticket_id),
        suggestion_id uuid REFERENCES suggestions (suggestion_id),
        staff_reason_codes jsonb NOT NULL,
        escalated_by_account_id uuid NOT NULL REFERENCES accounts (account_id),
        escalated_at timestamptz NOT NULL,
        note text
    )
    """,
    "CREATE INDEX escalations_by_time ON escalations (escalated_at)",
    # A decision holds no text (ADR-0006).
    """
    CREATE TABLE staff_decisions (
        decision_id uuid PRIMARY KEY,
        ticket_id text NOT NULL REFERENCES tickets (ticket_id),
        suggestion_id uuid REFERENCES suggestions (suggestion_id),
        decision_type text NOT NULL
            CHECK (decision_type IN ('approve', 'edit', 'reject', 'escalate')),
        staff_reason_codes jsonb NOT NULL,
        change_ratio numeric(4, 3) CHECK (change_ratio BETWEEN 0 AND 1),
        final_intent text,
        decided_by_account_id uuid NOT NULL REFERENCES accounts (account_id),
        proposed_by_account_id uuid REFERENCES accounts (account_id),
        is_proposal_changed boolean,
        decided_at timestamptz NOT NULL
    )
    """,
    "CREATE INDEX staff_decisions_by_time ON staff_decisions (decided_at)",
    # tickets: the current suggestion, and the study pair and batch of imported tickets.
    """
    ALTER TABLE tickets
        ADD COLUMN current_suggestion_id uuid REFERENCES suggestions (suggestion_id),
        ADD COLUMN study_pair_id text,
        ADD COLUMN study_batch text
    """,
    # The console queues: open tickets oldest first, closed tickets newest first.
    """
    CREATE INDEX tickets_by_status
        ON tickets (status, created_at, ticket_id COLLATE "C")
    """,
    """
    CREATE INDEX tickets_closed_by_time
        ON tickets (closed_at DESC, ticket_id COLLATE "C") WHERE status = 'closed'
    """,
)

_CREATE_TRIGGERS = (
    # `suggestions.request` goes from absent to a value once (design, Tables).
    """
    CREATE FUNCTION reject_suggestion_request_rewrite() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF OLD.request IS NOT NULL THEN
            RAISE EXCEPTION 'the request of a suggestion is written once'
                USING ERRCODE = 'check_violation';
        END IF;
        RETURN NEW;
    END
    $$
    """,
    """
    CREATE TRIGGER suggestions_request_written_once
        BEFORE UPDATE OF request ON suggestions
        FOR EACH ROW EXECUTE FUNCTION reject_suggestion_request_rewrite()
    """,
    # Every column of a final part is written once.
    """
    CREATE FUNCTION reject_final_part_change() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF OLD.status <> 'pending' THEN
            RAISE EXCEPTION 'a final suggestion part is never changed'
                USING ERRCODE = 'check_violation';
        END IF;
        RETURN NEW;
    END
    $$
    """,
    """
    CREATE TRIGGER suggestion_parts_final_parts_stay_final
        BEFORE UPDATE ON suggestion_parts
        FOR EACH ROW EXECUTE FUNCTION reject_final_part_change()
    """,
    # `tickets.status` changes only along the state machine of the design.
    """
    CREATE FUNCTION reject_disallowed_ticket_transition() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF NEW.status IS DISTINCT FROM OLD.status AND NOT (
            (OLD.status = 'open' AND NEW.status IN ('awaiting_approval', 'escalated', 'closed'))
            OR (OLD.status IN ('awaiting_approval', 'escalated') AND NEW.status = 'closed')
        ) THEN
            RAISE EXCEPTION 'the ticket status cannot change this way'
                USING ERRCODE = 'check_violation';
        END IF;
        RETURN NEW;
    END
    $$
    """,
    """
    CREATE TRIGGER tickets_status_follows_the_state_machine
        BEFORE UPDATE OF status ON tickets
        FOR EACH ROW EXECUTE FUNCTION reject_disallowed_ticket_transition()
    """,
)

_GRANT_PRIVILEGES = (
    "GRANT SELECT, INSERT ON suggestions TO supportiq_app",
    "GRANT UPDATE (request) ON suggestions TO supportiq_app",
    "GRANT SELECT, INSERT ON suggestion_parts TO supportiq_app",
    """
    GRANT UPDATE (status, reason_codes, release_id, versions, latency_ms,
        llm_input_token_count, llm_output_token_count, llm_cost_micro_usd, mask_count_by_type,
        completed_at, result) ON suggestion_parts TO supportiq_app
    """,
    "GRANT SELECT, INSERT, UPDATE ON suggestion_jobs TO supportiq_app",
    """
    GRANT SELECT, INSERT
        ON pseudonym_map_entries, reply_proposals, replies, escalations, staff_decisions
        TO supportiq_app
    """,
    "GRANT UPDATE (current_suggestion_id) ON tickets TO supportiq_app",
)

_DOWNGRADE = (
    "REVOKE UPDATE (current_suggestion_id) ON tickets FROM supportiq_app",
    "DROP TRIGGER tickets_status_follows_the_state_machine ON tickets",
    "DROP FUNCTION reject_disallowed_ticket_transition()",
    "DROP INDEX tickets_closed_by_time",
    "DROP INDEX tickets_by_status",
    """
    ALTER TABLE tickets
        DROP COLUMN study_batch,
        DROP COLUMN study_pair_id,
        DROP COLUMN current_suggestion_id
    """,
    "DROP TABLE staff_decisions",
    "DROP TABLE escalations",
    "DROP TABLE replies",
    "DROP TABLE reply_proposals",
    "DROP TABLE pseudonym_map_entries",
    "DROP TABLE suggestion_jobs",
    "DROP TABLE suggestion_parts",
    "DROP TABLE suggestions",
    "DROP FUNCTION reject_final_part_change()",
    "DROP FUNCTION reject_suggestion_request_rewrite()",
)


def upgrade() -> None:
    """Create the tables, the triggers, and the privileges of the ticket workflow."""
    for statement in (*_CREATE_TABLES, *_CREATE_TRIGGERS, *_GRANT_PRIVILEGES):
        op.execute(statement)


def downgrade() -> None:
    """Drop everything that `upgrade` created; the foundation tables stay as `r0002` left them."""
    for statement in _DOWNGRADE:
        op.execute(statement)

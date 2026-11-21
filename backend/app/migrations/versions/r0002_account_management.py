"""Let `supportiq_app` create staff and manager accounts and replace password hashes.

Revision ID: 0002
Revises: 0001

Every change comes from the account management design (Migration `r0002`), which implements
ADR-0015: the privileges to insert an account without `customer_id` and to update
`password_hash`, a trigger that keeps admin accounts to the owner, and the check of
`audit_log_entries.event_type` with the three new event types. `supportiq_app` still cannot
delete an account. `r0001` is never changed (PY-40).
"""

from alembic import op

revision = "0002"
down_revision: str | None = "0001"
branch_labels: str | None = None
depends_on: str | None = None

_UPGRADE = (
    # `customer_id` is not granted, so the check of `r0001` refuses every customer row that
    # supportiq_app inserts.
    """
    GRANT INSERT (account_id, login_name, display_name, role, is_active, password_hash,
        created_at) ON accounts TO supportiq_app
    """,
    "GRANT UPDATE (password_hash) ON accounts TO supportiq_app",
    # Admin accounts exist only through the seed, which runs as the owner (ADR-0012, admin
    # limit 3). Having the privileges of the owning role is what owning a table means in
    # PostgreSQL, so the owner passes and supportiq_app does not.
    """
    CREATE FUNCTION reject_admin_account_insert() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF NEW.role = 'admin' AND NOT pg_catalog.pg_has_role(
            (SELECT relowner FROM pg_catalog.pg_class WHERE oid = TG_RELID), 'USAGE'
        ) THEN
            RAISE EXCEPTION 'admin accounts are inserted only by the owner of the table'
                USING ERRCODE = 'insufficient_privilege';
        END IF;
        RETURN NEW;
    END
    $$
    """,
    """
    CREATE TRIGGER accounts_admin_accounts_only_from_the_owner
        BEFORE INSERT ON accounts
        FOR EACH ROW EXECUTE FUNCTION reject_admin_account_insert()
    """,
    # The audit log accepts only the event types it lists, so without the three new ones every
    # creation, reset, and own change would fail. The check of `r0001` has the name that
    # PostgreSQL gives a column check.
    "ALTER TABLE audit_log_entries DROP CONSTRAINT audit_log_entries_event_type_check",
    """
    ALTER TABLE audit_log_entries ADD CONSTRAINT audit_log_entries_event_type_check
        CHECK (event_type IN (
            'message.pseudonymized', 'suggestion.part_completed', 'intent.overridden',
            'reply_proposal.submitted', 'reply.sent', 'decision.recorded', 'ticket.escalated',
            'account.role_changed', 'account.status_changed', 'account.created',
            'account.password_changed', 'account.password_reset'
        ))
    """,
)

_DOWNGRADE = (
    # No role can delete an audit log entry (SEC-39), so entries of the new types stay. The
    # earlier check comes back as NOT VALID: it skips them, and no new one can be written.
    # Accounts created before the downgrade stay.
    "ALTER TABLE audit_log_entries DROP CONSTRAINT audit_log_entries_event_type_check",
    """
    ALTER TABLE audit_log_entries ADD CONSTRAINT audit_log_entries_event_type_check
        CHECK (event_type IN (
            'message.pseudonymized', 'suggestion.part_completed', 'intent.overridden',
            'reply_proposal.submitted', 'reply.sent', 'decision.recorded', 'ticket.escalated',
            'account.role_changed', 'account.status_changed'
        )) NOT VALID
    """,
    "DROP TRIGGER accounts_admin_accounts_only_from_the_owner ON accounts",
    "DROP FUNCTION reject_admin_account_insert()",
    "REVOKE UPDATE (password_hash) ON accounts FROM supportiq_app",
    """
    REVOKE INSERT (account_id, login_name, display_name, role, is_active, password_hash,
        created_at) ON accounts FROM supportiq_app
    """,
)


def upgrade() -> None:
    """Grant the account privileges, add the trigger, and allow the new event types."""
    for statement in _UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    """Remove the trigger and the privileges, and restore the earlier check as NOT VALID."""
    for statement in _DOWNGRADE:
        op.execute(statement)

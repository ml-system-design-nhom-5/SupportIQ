"""Create the foundation schema: tables, privileges of `supportiq_app`, and triggers.

Revision ID: 0001
Revises: none

Every table, column, constraint, privilege, and trigger comes from the backend foundation
design (Tables; Database roles and privileges). Data classes are in the comments of the
design and in the ORM models of each feature. Times are `timestamptz` in UTC (PY-26), money
is an amount in minor units with its currency (CON-16), and closed sets are text with a
CHECK constraint, so that adding a value is a plain migration.
"""

from alembic import op

revision = "0001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None

_CREATE_TABLES = (
    # commerce: seeded only (ADR-0013).
    """
    CREATE TABLE customers (
        customer_id uuid PRIMARY KEY,
        display_name text NOT NULL CHECK (display_name <> ''),
        email text NOT NULL CHECK (email <> ''),
        phone text NOT NULL CHECK (phone <> '')
    )
    """,
    # accounts: seeded only; supportiq_app may change role and is_active (ADR-0012).
    """
    CREATE TABLE accounts (
        account_id uuid PRIMARY KEY,
        login_name text NOT NULL UNIQUE CHECK (login_name <> ''),
        display_name text NOT NULL CHECK (display_name <> ''),
        role text NOT NULL CHECK (role IN ('customer', 'staff', 'manager', 'admin')),
        is_active boolean NOT NULL,
        customer_id uuid UNIQUE REFERENCES customers (customer_id),
        password_hash text NOT NULL CHECK (password_hash <> ''),
        created_at timestamptz NOT NULL,
        CONSTRAINT accounts_customer_id_exactly_for_customers
            CHECK ((role = 'customer') = (customer_id IS NOT NULL))
    )
    """,
    """
    CREATE TABLE sessions (
        session_id_hash bytea PRIMARY KEY CHECK (octet_length(session_id_hash) = 32),
        account_id uuid NOT NULL REFERENCES accounts (account_id),
        role text NOT NULL CHECK (role IN ('customer', 'staff', 'manager', 'admin')),
        created_at timestamptz NOT NULL,
        last_seen_at timestamptz NOT NULL,
        expires_at timestamptz NOT NULL
    )
    """,
    "CREATE INDEX sessions_account_id ON sessions (account_id)",
    "CREATE INDEX sessions_expires_at ON sessions (expires_at)",
    "CREATE INDEX sessions_last_seen_at ON sessions (last_seen_at)",
    """
    CREATE TABLE sign_in_failures (
        login_name_hash bytea NOT NULL CHECK (octet_length(login_name_hash) = 32),
        failed_at timestamptz NOT NULL
    )
    """,
    "CREATE INDEX sign_in_failures_by_name ON sign_in_failures (login_name_hash, failed_at)",
    "CREATE INDEX sign_in_failures_failed_at ON sign_in_failures (failed_at)",
    # idempotency (ERR-15): no response yet means that the request is in progress.
    """
    CREATE TABLE idempotency_records (
        account_id uuid NOT NULL REFERENCES accounts (account_id),
        operation_id text NOT NULL CHECK (operation_id <> ''),
        idempotency_key uuid NOT NULL,
        request_hash bytea NOT NULL CHECK (octet_length(request_hash) = 32),
        response_status smallint CHECK (response_status BETWEEN 200 AND 299),
        response_body json,
        created_at timestamptz NOT NULL,
        PRIMARY KEY (account_id, operation_id, idempotency_key),
        CONSTRAINT idempotency_records_response_complete
            CHECK ((response_status IS NULL) = (response_body IS NULL))
    )
    """,
    "CREATE INDEX idempotency_records_created_at ON idempotency_records (created_at)",
    """
    CREATE TABLE products (
        product_id text PRIMARY KEY CHECK (product_id <> ''),
        name text NOT NULL CHECK (name <> ''),
        description text NOT NULL CHECK (description <> ''),
        category text NOT NULL CHECK (category <> ''),
        price_amount_minor bigint NOT NULL CHECK (price_amount_minor >= 0),
        price_currency text NOT NULL CHECK (price_currency ~ '^[A-Z]{3}$')
    )
    """,
    # The catalog is listed by name, then product ID, by code point (contract listShopProducts).
    """
    CREATE INDEX products_catalog_order
        ON products (name COLLATE "C", product_id COLLATE "C")
    """,
    """
    CREATE TABLE orders (
        order_id text PRIMARY KEY CHECK (order_id <> ''),
        customer_id uuid NOT NULL REFERENCES customers (customer_id),
        order_status text NOT NULL
            CHECK (order_status IN ('placed', 'processing', 'shipped', 'delivered', 'cancelled')),
        placed_at timestamptz NOT NULL,
        order_total_amount_minor bigint NOT NULL CHECK (order_total_amount_minor >= 0),
        order_total_currency text NOT NULL CHECK (order_total_currency ~ '^[A-Z]{3}$'),
        shipping_cost_amount_minor bigint NOT NULL CHECK (shipping_cost_amount_minor >= 0),
        shipping_cost_currency text NOT NULL CHECK (shipping_cost_currency ~ '^[A-Z]{3}$'),
        shipping_address text NOT NULL CHECK (shipping_address <> ''),
        transaction_id text NOT NULL UNIQUE CHECK (transaction_id <> ''),
        CONSTRAINT orders_one_currency CHECK (order_total_currency = shipping_cost_currency)
    )
    """,
    # A customer's orders are listed newest first, then by order ID (contract listShopOrders).
    """
    CREATE INDEX orders_by_customer
        ON orders (customer_id, placed_at DESC, order_id COLLATE "C")
    """,
    """
    CREATE TABLE order_lines (
        order_id text NOT NULL REFERENCES orders (order_id),
        line_number integer NOT NULL CHECK (line_number >= 1),
        product_id text NOT NULL REFERENCES products (product_id),
        quantity integer NOT NULL CHECK (quantity >= 1),
        PRIMARY KEY (order_id, line_number),
        UNIQUE (order_id, product_id)
    )
    """,
    """
    CREATE TABLE shipments (
        shipment_id uuid PRIMARY KEY,
        order_id text NOT NULL UNIQUE REFERENCES orders (order_id),
        shipment_status text NOT NULL CHECK (
            shipment_status IN ('not_shipped', 'in_transit', 'delivered', 'delayed', 'lost')
        ),
        tracking_code text NOT NULL CHECK (tracking_code <> ''),
        estimated_delivery_at timestamptz,
        delivered_at timestamptz,
        CONSTRAINT shipments_delivered_at_exactly_when_delivered
            CHECK ((shipment_status = 'delivered') = (delivered_at IS NOT NULL))
    )
    """,
    """
    CREATE TABLE refunds (
        refund_id uuid PRIMARY KEY,
        order_id text NOT NULL UNIQUE REFERENCES orders (order_id),
        refund_status text NOT NULL
            CHECK (refund_status IN ('requested', 'under_review', 'approved', 'rejected', 'paid')),
        refund_amount_minor bigint NOT NULL CHECK (refund_amount_minor >= 0),
        refund_currency text NOT NULL CHECK (refund_currency ~ '^[A-Z]{3}$'),
        refund_requested_at timestamptz NOT NULL,
        updated_at timestamptz NOT NULL
    )
    """,
    # tickets: the ticket workflow design adds its own tables that point here. The numbers
    # start at 1001, so that ticket IDs read like `TCK-1001` (contracts v1 examples).
    "CREATE SEQUENCE ticket_number_seq START WITH 1001",
    """
    CREATE TABLE tickets (
        ticket_number bigint PRIMARY KEY DEFAULT nextval('ticket_number_seq'),
        ticket_id text NOT NULL UNIQUE
            GENERATED ALWAYS AS ('TCK-' || ticket_number::text) STORED,
        customer_id uuid NOT NULL REFERENCES customers (customer_id),
        order_id text REFERENCES orders (order_id),
        status text NOT NULL
            CHECK (status IN ('open', 'awaiting_approval', 'escalated', 'closed')),
        handling_mode text NOT NULL CHECK (handling_mode IN ('assisted', 'manual')),
        is_authority_required boolean NOT NULL DEFAULT false,
        source text NOT NULL CHECK (source IN ('shop', 'import')),
        created_at timestamptz NOT NULL,
        handling_started_at timestamptz,
        closed_at timestamptz,
        CONSTRAINT tickets_shop_tickets_have_an_order
            CHECK (source = 'import' OR order_id IS NOT NULL)
    )
    """,
    "ALTER SEQUENCE ticket_number_seq OWNED BY tickets.ticket_number",
    # A customer's tickets are listed newest first, then by ticket ID (contract listShopTickets).
    """
    CREATE INDEX tickets_by_customer
        ON tickets (customer_id, created_at DESC, ticket_id COLLATE "C")
    """,
    "CREATE INDEX tickets_order_id ON tickets (order_id)",
    """
    CREATE TABLE customer_messages (
        message_id uuid PRIMARY KEY,
        ticket_id text NOT NULL UNIQUE REFERENCES tickets (ticket_id),
        body text NOT NULL CHECK (char_length(body) BETWEEN 1 AND 2000),
        created_at timestamptz NOT NULL
    )
    """,
    # audit (SEC-39): data holds identifiers, statuses, reason codes, versions, and numbers.
    """
    CREATE TABLE audit_log_entries (
        entry_id uuid PRIMARY KEY,
        occurred_at timestamptz NOT NULL,
        event_type text NOT NULL CHECK (event_type IN (
            'message.pseudonymized', 'suggestion.part_completed', 'intent.overridden',
            'reply_proposal.submitted', 'reply.sent', 'decision.recorded', 'ticket.escalated',
            'account.role_changed', 'account.status_changed'
        )),
        actor_account_id uuid REFERENCES accounts (account_id),
        ticket_id text REFERENCES tickets (ticket_id),
        trace_id text NOT NULL CHECK (trace_id ~ '^[0-9a-f]{32}$'),
        data jsonb NOT NULL CHECK (jsonb_typeof(data) = 'object')
    )
    """,
)

_CREATE_TRIGGERS = (
    # The audit log is insert-only for every role, the owner included; reset uses TRUNCATE,
    # which supportiq_app may not run (SEC-39).
    """
    CREATE FUNCTION reject_audit_log_change() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        RAISE EXCEPTION 'audit log entries are never updated or deleted'
            USING ERRCODE = 'insufficient_privilege';
    END
    $$
    """,
    """
    CREATE TRIGGER audit_log_entries_insert_only
        BEFORE UPDATE OR DELETE ON audit_log_entries
        FOR EACH STATEMENT EXECUTE FUNCTION reject_audit_log_change()
    """,
    # A role changes only from staff to manager or back (ADR-0012, admin limit 3).
    """
    CREATE FUNCTION reject_disallowed_role_change() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF (OLD.role, NEW.role) NOT IN (('staff', 'manager'), ('manager', 'staff')) THEN
            RAISE EXCEPTION 'a role changes only between staff and manager'
                USING ERRCODE = 'check_violation';
        END IF;
        RETURN NEW;
    END
    $$
    """,
    """
    CREATE TRIGGER accounts_role_changes_between_staff_and_manager
        BEFORE UPDATE OF role ON accounts
        FOR EACH ROW WHEN (OLD.role IS DISTINCT FROM NEW.role)
        EXECUTE FUNCTION reject_disallowed_role_change()
    """,
    # The authority flag never goes back to false (contracts v1, Authority rule).
    """
    CREATE FUNCTION reject_authority_flag_clearing() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        RAISE EXCEPTION 'is_authority_required is never cleared'
            USING ERRCODE = 'check_violation';
    END
    $$
    """,
    """
    CREATE TRIGGER tickets_authority_flag_stays_set
        BEFORE UPDATE OF is_authority_required ON tickets
        FOR EACH ROW WHEN (OLD.is_authority_required AND NOT NEW.is_authority_required)
        EXECUTE FUNCTION reject_authority_flag_clearing()
    """,
)

# Exactly the privileges of the design's table, and nothing else (least privilege).
_GRANT_PRIVILEGES = (
    "GRANT USAGE ON SCHEMA public TO supportiq_app",
    """
    GRANT SELECT ON customers, products, orders, order_lines, shipments, refunds
        TO supportiq_app
    """,
    "GRANT SELECT, INSERT ON customer_messages, audit_log_entries TO supportiq_app",
    "GRANT SELECT ON accounts TO supportiq_app",
    "GRANT UPDATE (role, is_active) ON accounts TO supportiq_app",
    "GRANT SELECT, INSERT ON tickets TO supportiq_app",
    """
    GRANT UPDATE (status, is_authority_required, handling_started_at, closed_at) ON tickets
        TO supportiq_app
    """,
    "GRANT USAGE ON SEQUENCE ticket_number_seq TO supportiq_app",
    """
    GRANT SELECT, INSERT, UPDATE, DELETE ON sessions, sign_in_failures, idempotency_records
        TO supportiq_app
    """,
)

_DROP_ALL = (
    "REVOKE USAGE ON SCHEMA public FROM supportiq_app",
    "DROP TABLE audit_log_entries",
    "DROP TABLE customer_messages",
    "DROP TABLE tickets",
    "DROP TABLE refunds",
    "DROP TABLE shipments",
    "DROP TABLE order_lines",
    "DROP TABLE orders",
    "DROP TABLE products",
    "DROP TABLE idempotency_records",
    "DROP TABLE sign_in_failures",
    "DROP TABLE sessions",
    "DROP TABLE accounts",
    "DROP TABLE customers",
    "DROP FUNCTION reject_audit_log_change()",
    "DROP FUNCTION reject_disallowed_role_change()",
    "DROP FUNCTION reject_authority_flag_clearing()",
)


def upgrade() -> None:
    """Create every table, trigger, and privilege of the foundation schema."""
    for statement in (*_CREATE_TABLES, *_CREATE_TRIGGERS, *_GRANT_PRIVILEGES):
        op.execute(statement)


def downgrade() -> None:
    """Remove everything that `upgrade` created; the sequence goes with its table."""
    for statement in _DROP_ALL:
        op.execute(statement)

-- 001_audit_events.sql
CREATE TABLE IF NOT EXISTS audit.events (
    id UUID PRIMARY KEY,
    event_type TEXT NOT NULL,
    request_id UUID NOT NULL,
    ticket_id UUID,
    run_id UUID,
    actor_id UUID,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_events_ticket_occurred ON audit.events (ticket_id, occurred_at, id);
CREATE INDEX IF NOT EXISTS idx_audit_events_occurred_at ON audit.events (occurred_at);

-- Trigger to prevent any mutation (UPDATE, DELETE, TRUNCATE)
CREATE OR REPLACE FUNCTION audit.prevent_mutation()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'audit.events table is strictly immutable (append-only)';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_audit_events_immutable ON audit.events;
CREATE TRIGGER trg_audit_events_immutable
BEFORE UPDATE OR DELETE ON audit.events
FOR EACH ROW EXECUTE FUNCTION audit.prevent_mutation();

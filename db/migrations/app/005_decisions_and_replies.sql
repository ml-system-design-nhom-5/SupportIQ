-- 005_decisions_and_replies.sql
CREATE TABLE IF NOT EXISTS app.review_decisions (
    id UUID PRIMARY KEY,
    ticket_id UUID NOT NULL REFERENCES app.tickets(id) ON DELETE CASCADE,
    actor_id UUID NOT NULL REFERENCES app.users(id),
    source TEXT NOT NULL,
    action TEXT NOT NULL,
    draft_id UUID,
    body TEXT,
    reason TEXT,
    order_version INT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_review_decisions_ticket_id ON app.review_decisions (ticket_id);

CREATE TABLE IF NOT EXISTS app.replies (
    id UUID PRIMARY KEY,
    ticket_id UUID NOT NULL REFERENCES app.tickets(id) ON DELETE CASCADE,
    decision_id UUID NOT NULL UNIQUE REFERENCES app.review_decisions(id),
    actor_id UUID NOT NULL REFERENCES app.users(id),
    body TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_replies_ticket_id ON app.replies (ticket_id);

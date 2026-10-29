-- 001_idempotency_records.sql
CREATE TABLE IF NOT EXISTS app.idempotency_records (
    id UUID PRIMARY KEY,
    actor_id UUID NOT NULL,
    method TEXT NOT NULL,
    route TEXT NOT NULL,
    key TEXT NOT NULL,
    request_hmac TEXT NOT NULL,
    resource_id UUID,
    response_status INT,
    response_body JSONB,
    response_headers JSONB,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_idempotency_actor_method_route_key UNIQUE (actor_id, method, route, key)
);

CREATE INDEX IF NOT EXISTS idx_idempotency_expires_at ON app.idempotency_records (expires_at);

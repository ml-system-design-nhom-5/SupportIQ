-- 002_users_and_sessions.sql
CREATE TABLE IF NOT EXISTS app.users (
    id UUID PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    role_version INT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_email ON app.users (email);

CREATE TABLE IF NOT EXISTS app.sessions (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES app.users(id) ON DELETE CASCADE,
    refresh_token_hash TEXT NOT NULL,
    csrf_token_hash TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON app.sessions (user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_refresh_token_hash ON app.sessions (refresh_token_hash);

-- Seed demo accounts: password 'DemoPassword123!'
-- Argon2id hash for DemoPassword123!
INSERT INTO app.users (id, email, password_hash, role, active, role_version)
VALUES
    ('a0000000-0000-0000-0000-000000000001', 'admin@supportiq.demo', '$argon2id$v=19$m=65536,t=3,p=4$vO2hR5uH0u2n6zB/eNq8vQ$387Yg6nFfW3WdCg0W7P6bQ4w2F9r0y1Z7X5V8s9T0o4', 'admin', TRUE, 1),
    ('a0000000-0000-0000-0000-000000000002', 'manager1@supportiq.demo', '$argon2id$v=19$m=65536,t=3,p=4$vO2hR5uH0u2n6zB/eNq8vQ$387Yg6nFfW3WdCg0W7P6bQ4w2F9r0y1Z7X5V8s9T0o4', 'manager', TRUE, 1),
    ('a0000000-0000-0000-0000-000000000003', 'agent1@supportiq.demo', '$argon2id$v=19$m=65536,t=3,p=4$vO2hR5uH0u2n6zB/eNq8vQ$387Yg6nFfW3WdCg0W7P6bQ4w2F9r0y1Z7X5V8s9T0o4', 'agent', TRUE, 1),
    ('a0000000-0000-0000-0000-000000000004', 'customer1@supportiq.demo', '$argon2id$v=19$m=65536,t=3,p=4$vO2hR5uH0u2n6zB/eNq8vQ$387Yg6nFfW3WdCg0W7P6bQ4w2F9r0y1Z7X5V8s9T0o4', 'customer', TRUE, 1)
ON CONFLICT (email) DO NOTHING;

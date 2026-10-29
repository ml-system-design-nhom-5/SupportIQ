-- 001_token_mappings.sql
CREATE TABLE IF NOT EXISTS vault.token_mappings (
    id UUID PRIMARY KEY,
    run_id UUID NOT NULL,
    token TEXT NOT NULL,
    pii_type TEXT NOT NULL,
    encrypted_value BYTEA NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_vault_run_token UNIQUE (run_id, token)
);

CREATE INDEX IF NOT EXISTS idx_vault_tokens_expires_at ON vault.token_mappings (expires_at);

-- Role permissions
GRANT SELECT, INSERT, DELETE ON vault.token_mappings TO vault_resolver_role;

-- 004_releases_runs_jobs_and_attempts.sql
CREATE TABLE IF NOT EXISTS app.release_manifests (
    id UUID PRIMARY KEY,
    release_tag TEXT UNIQUE NOT NULL,
    intent_model_name TEXT NOT NULL,
    intent_model_version TEXT NOT NULL,
    embedding_model_name TEXT NOT NULL,
    embedding_model_version TEXT NOT NULL,
    llm_model_name TEXT NOT NULL,
    prompt_template_hash TEXT NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS app.pipeline_runs (
    id UUID PRIMARY KEY,
    ticket_id UUID NOT NULL REFERENCES app.tickets(id) ON DELETE CASCADE,
    customer_id UUID NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    stage TEXT NOT NULL DEFAULT 'pipeline',
    reason_codes JSONB NOT NULL DEFAULT '[]'::jsonb,
    deadline_at TIMESTAMPTZ NOT NULL,
    cost_status TEXT NOT NULL DEFAULT 'none',
    cost_micro BIGINT,
    draft_id UUID,
    release_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_ticket_id ON app.pipeline_runs (ticket_id);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_status ON app.pipeline_runs (status);

CREATE TABLE IF NOT EXISTS app.jobs (
    id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES app.pipeline_runs(id) ON DELETE CASCADE,
    stage TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    worker_id TEXT,
    lease_token UUID,
    lease_expires_at TIMESTAMPTZ,
    payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_jobs_run_stage UNIQUE (run_id, stage)
);

CREATE INDEX IF NOT EXISTS idx_jobs_stage_status ON app.jobs (stage, status);

CREATE TABLE IF NOT EXISTS app.llm_attempts (
    id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES app.pipeline_runs(id) ON DELETE CASCADE,
    attempt_no INT NOT NULL,
    status TEXT NOT NULL DEFAULT 'in_flight',
    cost_micro BIGINT,
    response_tokens INT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_llm_run_attempt UNIQUE (run_id, attempt_no)
);

CREATE TABLE IF NOT EXISTS app.evidence_snapshots (
    id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES app.pipeline_runs(id) ON DELETE CASCADE,
    citation_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    snippet TEXT NOT NULL,
    title TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_evidence_run_citation UNIQUE (run_id, citation_id)
);

CREATE TABLE IF NOT EXISTS app.drafts (
    id UUID PRIMARY KEY,
    run_id UUID NOT NULL UNIQUE REFERENCES app.pipeline_runs(id) ON DELETE CASCADE,
    draft_body TEXT NOT NULL,
    citation_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

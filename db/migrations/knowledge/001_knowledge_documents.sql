-- 001_knowledge_documents.sql
CREATE TABLE IF NOT EXISTS knowledge.documents (
    id UUID PRIMARY KEY,
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS knowledge.document_versions (
    id UUID PRIMARY KEY,
    document_id UUID NOT NULL REFERENCES knowledge.documents(id) ON DELETE CASCADE,
    version INT NOT NULL,
    policy_key TEXT NOT NULL,
    normalized_rule_value TEXT NOT NULL,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    allowed_roles JSONB NOT NULL DEFAULT '["agent", "staff", "manager", "admin"]'::jsonb,
    content_hash TEXT NOT NULL,
    sanitized_excerpt TEXT NOT NULL,
    search_tsv TSVECTOR,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_knowledge_doc_version UNIQUE (document_id, version)
);

CREATE INDEX IF NOT EXISTS idx_doc_versions_policy_key ON knowledge.document_versions (policy_key);
CREATE INDEX IF NOT EXISTS idx_doc_versions_status_dates ON knowledge.document_versions (status, valid_from, valid_to);

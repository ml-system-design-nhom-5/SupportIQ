-- 000_init_schemas_and_roles.sql
-- Create isolated schemas
CREATE SCHEMA IF NOT EXISTS app;
CREATE SCHEMA IF NOT EXISTS knowledge;
CREATE SCHEMA IF NOT EXISTS audit;
CREATE SCHEMA IF NOT EXISTS vault;

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Create service roles if they do not exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'core_app_role') THEN
        CREATE ROLE core_app_role WITH LOGIN PASSWORD 'core_app_password';
    END IF;
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'audit_writer_role') THEN
        CREATE ROLE audit_writer_role WITH LOGIN PASSWORD 'audit_writer_password';
    END IF;
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'audit_reader_role') THEN
        CREATE ROLE audit_reader_role WITH LOGIN PASSWORD 'audit_reader_password';
    END IF;
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'vault_resolver_role') THEN
        CREATE ROLE vault_resolver_role WITH LOGIN PASSWORD 'vault_resolver_password';
    END IF;
END $$;

-- Schema usage permissions
GRANT USAGE ON SCHEMA app TO core_app_role;
GRANT USAGE ON SCHEMA knowledge TO core_app_role;
GRANT USAGE ON SCHEMA audit TO core_app_role, audit_writer_role, audit_reader_role;
GRANT USAGE ON SCHEMA vault TO vault_resolver_role;

-- core_app_role permissions (Full CRUD on app, SELECT on knowledge, read audit, NO access to vault)
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA app TO core_app_role;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA app TO core_app_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA app GRANT ALL PRIVILEGES ON TABLES TO core_app_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA app GRANT ALL PRIVILEGES ON SEQUENCES TO core_app_role;

GRANT SELECT ON ALL TABLES IN SCHEMA knowledge TO core_app_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA knowledge GRANT SELECT ON TABLES TO core_app_role;

-- Zero privileges on vault for core_app_role
REVOKE ALL ON SCHEMA vault FROM core_app_role;

-- audit_writer_role: INSERT ONLY on audit schema (Append-only immutable audit)
GRANT INSERT ON ALL TABLES IN SCHEMA audit TO audit_writer_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA audit GRANT INSERT ON TABLES TO audit_writer_role;

-- audit_reader_role: SELECT ONLY on audit schema
GRANT SELECT ON ALL TABLES IN SCHEMA audit TO audit_reader_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA audit GRANT SELECT ON TABLES TO audit_reader_role;

-- vault_resolver_role: Full access to vault schema only
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA vault TO vault_resolver_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA vault GRANT ALL PRIVILEGES ON TABLES TO vault_resolver_role;

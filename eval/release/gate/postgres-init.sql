-- The owner role and the database of the backend guardrail tests of the gate, as the CI job
-- backend-tests creates them (.github/workflows/backend.yml). The password is a throwaway, never
-- a real secret: the database lives only in the tmpfs of one run of compose.yaml.
CREATE ROLE supportiq_owner LOGIN CREATEDB CREATEROLE PASSWORD 'gate-owner';
CREATE DATABASE supportiq OWNER supportiq_owner;

-- Create or update the role `supportiq_app`, which the backend replicas use (backend foundation
-- design, Database roles and privileges). Run it once per database as the database owner,
-- `supportiq_owner`, through `backend create-app-role`. That command first binds the password of
-- `database_url_app` to the transaction-local setting `supportiq.app_role_password`, so the
-- password never appears in this file or in a statement text (SEC-09, PY-42).
--
-- The owner has CREATEROLE but is not a superuser, so it can create the role without SUPERUSER,
-- REPLICATION, and BYPASSRLS, and cannot change those attributes later. An existing role that
-- has one of them was not created by this script and is refused.
--
-- The role gets no privilege on any table here. The first migration grants exactly the
-- privileges of the design's table, and nothing else.
DO $$
DECLARE
  app_role_password text := current_setting('supportiq.app_role_password');
BEGIN
  IF app_role_password IS NULL OR app_role_password = '' THEN
    RAISE EXCEPTION 'supportiq.app_role_password is not set';
  END IF;
  IF EXISTS (
    SELECT FROM pg_catalog.pg_roles
    WHERE rolname = 'supportiq_app' AND (rolsuper OR rolreplication OR rolbypassrls)
  ) THEN
    RAISE EXCEPTION 'supportiq_app has SUPERUSER, REPLICATION, or BYPASSRLS; drop it first';
  END IF;
  IF EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'supportiq_app') THEN
    EXECUTE format(
      'ALTER ROLE supportiq_app LOGIN NOINHERIT NOCREATEDB NOCREATEROLE PASSWORD %L',
      app_role_password
    );
  ELSE
    EXECUTE format(
      'CREATE ROLE supportiq_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT '
      'NOREPLICATION NOBYPASSRLS PASSWORD %L',
      app_role_password
    );
  END IF;
  EXECUTE format('GRANT CONNECT ON DATABASE %I TO supportiq_app', current_database());
END
$$;

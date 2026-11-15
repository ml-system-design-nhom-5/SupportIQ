"""Docker-specific PostgreSQL role provisioning, URL-escaped DSN wiring, and entrypoint."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Mapping
from urllib.parse import quote

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DOCKER_SECRETS_PATH = Path("/run/supportiq/application.json")
_REQUIRED_INIT_VARS = (
    "SUPPORTIQ_POSTGRES_OWNER_PASSWORD",
    "SUPPORTIQ_POSTGRES_APP_PASSWORD",
    "SUPPORTIQ_DEMO_CUSTOMER_PASSWORD",
    "SUPPORTIQ_DEMO_STAFF_PASSWORD",
    "SUPPORTIQ_DEMO_MANAGER_PASSWORD",
    "SUPPORTIQ_DEMO_ADMIN_PASSWORD",
)


def require_env_value(env: Mapping[str, str], name: str) -> str:
    """Return validated non-empty secret env var without leaking secret values on error."""
    raw = env.get(name, "")
    if not raw or not raw.strip() or raw.strip().lower().startswith("replace-with-"):
        raise ValueError(f"Missing or invalid required environment variable: {name}")
    return raw


def build_postgres_url(user: str, password: str, host: str, port: str | int, db: str) -> str:
    """Construct a PostgreSQL+psycopg DSN with RFC-3986 percent-escaped credentials."""
    if not user or not user.strip() or not host or not host.strip() or not db or not db.strip():
        raise ValueError("PostgreSQL user, host, and database name must be non-empty.")
    try:
        port_num = int(port)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid PostgreSQL port: {port!r}") from exc
    if not (1 <= port_num <= 65535):
        raise ValueError(f"PostgreSQL port out of range: {port_num}")
    return (
        f"postgresql+psycopg://{quote(user, safe='')}:{quote(password, safe='')}"
        f"@{host.strip()}:{port_num}/{quote(db.strip(), safe='')}"
    )


def write_docker_secrets(
    secrets_path: Path,
    payload: Mapping[str, object],
    *,
    repo_root: Path = REPO_ROOT,
) -> Path:
    """Write Docker-generated secrets JSON while refusing to overwrite native .local/application.json."""
    resolved_target = secrets_path.resolve()
    native_path = (repo_root / ".local/application.json").resolve()
    if resolved_target == native_path:
        raise RuntimeError("Refusing to overwrite native .local/application.json from Docker init.")
    resolved_target.parent.mkdir(parents=True, exist_ok=True)
    resolved_target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    try:
        os.chmod(resolved_target, 0o600)
    except OSError:
        pass
    return resolved_target


def _pg_coords(env: Mapping[str, str]) -> tuple[str, int, str]:
    host = env.get("SUPPORTIQ_POSTGRES_HOST", "postgres").strip()
    port_raw = env.get("SUPPORTIQ_POSTGRES_PORT", "5432").strip()
    db = env.get("SUPPORTIQ_POSTGRES_DB", "supportiq").strip()
    port = int(port_raw)
    if not host or not db or not (1 <= port <= 65535):
        raise ValueError("Invalid PostgreSQL host, port, or database configuration.")
    return host, port, db


def provision_app_role(host: str, port: int, db: str, owner_password: str, app_password: str) -> None:
    """Create or update the restricted supportiq_app login role using owner keyword auth."""
    import psycopg
    from psycopg import sql

    with psycopg.connect(
        host=host,
        port=port,
        dbname=db,
        user="supportiq_owner",
        password=owner_password,
        connect_timeout=5,
        autocommit=True,
    ) as conn:
        exists = conn.execute("SELECT 1 FROM pg_roles WHERE rolname = 'supportiq_app'").fetchone()
        verb = "ALTER" if exists else "CREATE"
        stmt = sql.SQL(
            f"{verb} ROLE supportiq_app WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD {{}}"
        ).format(sql.Literal(app_password))
        conn.execute(stmt)


def prepare_docker_secrets(env: Mapping[str, str], *, repo_root: Path = REPO_ROOT) -> tuple[Path, dict[str, object]]:
    """Validate Docker init env vars and materialize Docker-specific secrets JSON."""
    values = {name: require_env_value(env, name) for name in _REQUIRED_INIT_VARS}
    if values["SUPPORTIQ_POSTGRES_OWNER_PASSWORD"] == values["SUPPORTIQ_POSTGRES_APP_PASSWORD"]:
        raise ValueError("SUPPORTIQ_POSTGRES_OWNER_PASSWORD and SUPPORTIQ_POSTGRES_APP_PASSWORD must be distinct.")
    for url_var in ("SUPPORTIQ_DATABASE_URL_OWNER", "SUPPORTIQ_DATABASE_URL_APP"):
        if env.get(url_var, "").strip().lower().startswith("sqlite"):
            raise ValueError(f"SQLite URL is disallowed in Docker runtime ({url_var}).")

    host, port, db = _pg_coords(env)
    payload: dict[str, object] = {
        "database_url_owner": build_postgres_url(
            "supportiq_owner", values["SUPPORTIQ_POSTGRES_OWNER_PASSWORD"], host, port, db
        ),
        "database_url_app": build_postgres_url(
            "supportiq_app", values["SUPPORTIQ_POSTGRES_APP_PASSWORD"], host, port, db
        ),
        "passwords": {
            "customer": values["SUPPORTIQ_DEMO_CUSTOMER_PASSWORD"],
            "staff": values["SUPPORTIQ_DEMO_STAFF_PASSWORD"],
            "manager": values["SUPPORTIQ_DEMO_MANAGER_PASSWORD"],
            "admin": values["SUPPORTIQ_DEMO_ADMIN_PASSWORD"],
        },
    }
    target = Path(env.get("SUPPORTIQ_APPLICATION_SECRETS") or str(DEFAULT_DOCKER_SECRETS_PATH))
    written = write_docker_secrets(target, payload, repo_root=repo_root)
    return written, payload


def run_init() -> None:
    """Provision restricted Postgres role, run migrations/grants, and seed on first start."""
    host, port, db = _pg_coords(os.environ)
    secrets_path, _payload = prepare_docker_secrets(os.environ)
    provision_app_role(
        host,
        port,
        db,
        os.environ["SUPPORTIQ_POSTGRES_OWNER_PASSWORD"],
        os.environ["SUPPORTIQ_POSTGRES_APP_PASSWORD"],
    )
    os.environ["SUPPORTIQ_APPLICATION_SECRETS"] = str(secrets_path)
    from .manage import initialize

    initialize()


def run_backend() -> None:
    """Build escaped supportiq_app DSN, strip owner credentials, and exec backend uvicorn."""
    if os.environ.get("SUPPORTIQ_DATABASE_URL_APP", "").strip().lower().startswith("sqlite"):
        raise ValueError("SQLite is not supported in Docker backend runtime.")
    app_pw = require_env_value(os.environ, "SUPPORTIQ_POSTGRES_APP_PASSWORD")
    host, port, db = _pg_coords(os.environ)
    os.environ["SUPPORTIQ_DATABASE_URL_APP"] = build_postgres_url("supportiq_app", app_pw, host, port, db)
    for owner_key in ("SUPPORTIQ_DATABASE_URL_OWNER", "SUPPORTIQ_POSTGRES_OWNER_PASSWORD"):
        os.environ.pop(owner_key, None)
    bind_port = os.environ.get("SUPPORTIQ_PORT", "8080").strip() or "8080"
    os.execvp(
        "uvicorn",
        ["uvicorn", "apps.backend.main:create_app", "--factory", "--host", "0.0.0.0", "--port", bind_port, "--no-access-log"],
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["init", "backend"])
    mode = parser.parse_args().mode
    if mode == "init":
        run_init()
    else:
        run_backend()

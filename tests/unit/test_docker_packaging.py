"""Unit and static hygiene tests for Docker Compose packaging and init credential handling."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from apps.backend import docker_init
from apps.backend import manage as backend_manage

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_build_postgres_url_escapes_punctuation_safely() -> None:
    """Passwords with RFC-3986 reserved punctuation are percent-encoded cleanly."""
    url = docker_init.build_postgres_url(
        "supportiq_app",
        "p@ss:/?#%+= !&word",
        "postgres",
        5432,
        "supportiq",
    )
    assert url == "postgresql+psycopg://supportiq_app:p%40ss%3A%2F%3F%23%25%2B%3D%20%21%26word@postgres:5432/supportiq"


def test_prepare_docker_secrets_validates_env_without_leaking_values(tmp_path: Path) -> None:
    """Missing/placeholder env vars, matching passwords, or SQLite URLs fail closed."""
    base_env = {
        "SUPPORTIQ_POSTGRES_OWNER_PASSWORD": "owner!secret#1",
        "SUPPORTIQ_POSTGRES_APP_PASSWORD": "app!secret@2",
        "SUPPORTIQ_DEMO_CUSTOMER_PASSWORD": "cust$pw",
        "SUPPORTIQ_DEMO_STAFF_PASSWORD": "staff$pw",
        "SUPPORTIQ_DEMO_MANAGER_PASSWORD": "mgr$pw",
        "SUPPORTIQ_DEMO_ADMIN_PASSWORD": "adm$pw",
        "SUPPORTIQ_APPLICATION_SECRETS": str(tmp_path / "docker-app.json"),
    }

    for missing_key in base_env:
        if missing_key == "SUPPORTIQ_APPLICATION_SECRETS":
            continue
        env_copy = dict(base_env)
        env_copy.pop(missing_key)
        with pytest.raises(ValueError, match=missing_key):
            docker_init.prepare_docker_secrets(env_copy, repo_root=tmp_path)

        env_placeholder = dict(base_env, **{missing_key: "replace-with-strong-password"})
        with pytest.raises(ValueError, match=missing_key):
            docker_init.prepare_docker_secrets(env_placeholder, repo_root=tmp_path)

    same_pw_env = dict(base_env, SUPPORTIQ_POSTGRES_APP_PASSWORD=base_env["SUPPORTIQ_POSTGRES_OWNER_PASSWORD"])
    with pytest.raises(ValueError, match="distinct"):
        docker_init.prepare_docker_secrets(same_pw_env, repo_root=tmp_path)

    sqlite_env = dict(base_env, SUPPORTIQ_DATABASE_URL_APP="sqlite:///tmp/bad.db")
    with pytest.raises(ValueError, match="SQLite"):
        docker_init.prepare_docker_secrets(sqlite_env, repo_root=tmp_path)


def test_write_docker_secrets_never_overwrites_native_local_application_json(tmp_path: Path) -> None:
    """Refuses to touch native .local/application.json even if explicitly targeted."""
    native_secrets = tmp_path / ".local/application.json"
    native_secrets.parent.mkdir(parents=True)
    original_content = '{"native": "preserved"}\n'
    native_secrets.write_text(original_content, encoding="utf-8")

    with pytest.raises(RuntimeError, match="Refusing to overwrite native"):
        docker_init.write_docker_secrets(native_secrets, {"native": "clobbered"}, repo_root=tmp_path)

    assert native_secrets.read_text(encoding="utf-8") == original_content


def test_manage_initialize_supports_secrets_override_and_rejects_sqlite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SUPPORTIQ_APPLICATION_SECRETS overrides .local/application.json; SQLite URL is rejected."""
    bad_secrets = tmp_path / "sqlite-secrets.json"
    bad_secrets.write_text(json.dumps({"database_url_owner": "sqlite:///bad.db", "passwords": {}}), encoding="utf-8")
    monkeypatch.setenv("SUPPORTIQ_APPLICATION_SECRETS", str(bad_secrets))
    with pytest.raises(RuntimeError, match="SQLite is not supported"):
        backend_manage.initialize()


def test_first_start_seed_only_preserves_state_across_two_starts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Running manage.initialize() twice does not re-seed or overwrite user state when accounts already exist."""
    secrets_file = tmp_path / "docker-app.json"
    secrets_file.write_text(
        json.dumps(
            {
                "database_url_owner": "postgresql+psycopg://supportiq_owner:pw@postgres:5432/supportiq",
                "passwords": {"customer": "c", "staff": "s", "manager": "m", "admin": "a"},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("SUPPORTIQ_APPLICATION_SECRETS", str(secrets_file))

    seed_calls = []

    class _FakeConn:
        def execute(self, *_a, **_kw):
            return None

    class _FakeBegin:
        def __enter__(self):
            return _FakeConn()

        def __exit__(self, *_a):
            return False

    fake_engine = SimpleNamespace(begin=lambda: _FakeBegin(), dispose=lambda: None)

    state = {"seeded": False}

    def _fake_seed(_db, passwords):
        if state["seeded"]:
            return
        state["seeded"] = True
        seed_calls.append(passwords)

    with (
        patch.object(backend_manage, "create_engine", return_value=fake_engine),
        patch("alembic.command.upgrade"),
        patch.object(backend_manage, "seed", side_effect=_fake_seed),
    ):
        backend_manage.initialize()
        backend_manage.initialize()

    assert len(seed_calls) == 1


def test_real_seed_returns_early_when_accounts_exist() -> None:
    """Calling apps.backend.seed.seed() when accounts already exist adds zero rows."""
    from contextlib import contextmanager
    from apps.backend.seed import seed as real_seed

    added = []

    class _FakeSession:
        def scalar(self, *_a, **_kw):
            return "existing-account-id"

        def add(self, obj):
            added.append(obj)

    class _FakeDB:
        @contextmanager
        def transaction(self):
            yield _FakeSession()

    real_seed(_FakeDB(), {"customer": "c", "staff": "s", "manager": "m", "admin": "a"})
    assert added == []


def test_run_backend_strips_owner_creds_and_escapes_app_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    """run_backend constructs escaped supportiq_app DSN and drops any owner credentials."""
    monkeypatch.setenv("SUPPORTIQ_POSTGRES_APP_PASSWORD", "app@pw#1")
    monkeypatch.setenv("SUPPORTIQ_DATABASE_URL_OWNER", "postgresql+psycopg://supportiq_owner:secret@postgres/supportiq")
    monkeypatch.setenv("SUPPORTIQ_POSTGRES_OWNER_PASSWORD", "secret")
    monkeypatch.delenv("SUPPORTIQ_DATABASE_URL_APP", raising=False)

    exec_calls = []
    with patch("os.execvp", side_effect=lambda cmd, argv: exec_calls.append((cmd, argv))):
        docker_init.run_backend()

    assert "SUPPORTIQ_DATABASE_URL_OWNER" not in docker_init.os.environ
    assert "SUPPORTIQ_POSTGRES_OWNER_PASSWORD" not in docker_init.os.environ
    assert docker_init.os.environ["SUPPORTIQ_DATABASE_URL_APP"] == "postgresql+psycopg://supportiq_app:app%40pw%231@postgres:5432/supportiq"
    assert exec_calls == [("uvicorn", ["uvicorn", "apps.backend.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080", "--no-access-log"])]


def test_docker_packaging_static_security_and_topology() -> None:
    """Static inspection ensures no baked secrets, internal AI/PG, non-root users, and strict .dockerignore."""
    dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    compose = (REPO_ROOT / "compose.yaml").read_text(encoding="utf-8")
    dockerignore = (REPO_ROOT / ".dockerignore").read_text(encoding="utf-8")
    env_example = (REPO_ROOT / ".env.docker.example").read_text(encoding="utf-8")

    # Dockerfile invariants
    assert "FROM node:24-slim AS frontend-builder" in dockerfile
    assert "pnpm@10" in dockerfile
    assert "FROM python:3.12-slim AS backend" in dockerfile
    assert "FROM python:3.12-slim AS ai-service" in dockerfile
    assert "https://download.pytorch.org/whl/cpu" in dockerfile
    assert "spacy.load('en_core_web_sm')" in dockerfile
    assert "USER supportiq" in dockerfile
    assert "start-app.ps1" not in dockerfile and "native_runtime.py" not in dockerfile

    # .dockerignore strict allowlist excludes secrets, datasets, weights, tests, and docs
    first_non_comment = next(line.strip() for line in dockerignore.splitlines() if line.strip() and not line.strip().startswith("#"))
    assert first_non_comment == "*"
    for forbidden in (".local/", ".env", ".git", ".venv", "data/datasets", "artifacts/models", "tests/", "docs/"):
        assert f"!{forbidden}" not in dockerignore

    # Compose topology, RO mounts, pinned hashes, and loopback-only 8081 publish
    assert '"127.0.0.1:${SUPPORTIQ_HOST_PORT:-8081}:8080"' in compose
    assert "8002:" not in compose and "5432:" not in compose
    assert "pgdata:/var/lib/postgresql/data" in compose
    assert "reconstructed-fit2-supcon-20261113:ro" in compose
    assert "/cache/huggingface:ro" in compose
    assert "f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa" in compose
    assert "782c88db3fcd80615c3dceabbdb96ea2be7aa769119201f94229535becc7ae39" in compose
    assert "retrieval_ready" in compose and "model_verified" in compose

    # No real API keys or native passwords baked into example template
    assert "AIza" not in env_example

"""Cleanup regression tests for the isolated browser E2E verification helper."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from scripts import run_isolated_browser_e2e as runner


def test_temporary_worker_config_restores_existing_and_removes_new(tmp_path):
    existing = tmp_path / "existing" / "application.json"
    existing.parent.mkdir(parents=True)
    original_payload = '{"database_url_owner": "keep-me", "passwords": {"staff": "orig"}}'
    existing.write_text(original_payload, encoding="utf-8")

    with pytest.raises(RuntimeError, match="boom"):
        with runner.temporary_worker_application_config(existing, {"staff": "temp-synth"}):
            loaded = json.loads(existing.read_text(encoding="utf-8"))
            assert loaded["passwords"]["staff"] == "temp-synth"
            raise RuntimeError("boom")

    assert existing.read_text(encoding="utf-8") == original_payload

    fresh = tmp_path / "fresh" / "application.json"
    with pytest.raises(RuntimeError, match="boom"):
        with runner.temporary_worker_application_config(fresh, {"staff": "temp-synth"}):
            assert fresh.exists()
            raise RuntimeError("boom")

    assert not fresh.exists()


def test_run_e2e_pipeline_cleans_up_owned_resources_on_playwright_failure(tmp_path, monkeypatch):
    config_file = tmp_path / ".local" / "application.json"
    config_file.parent.mkdir(parents=True)
    original_text = '{"passwords": {"customer": "original-secret"}}'
    config_file.write_text(original_text, encoding="utf-8")

    out_dir = tmp_path / "artifacts" / "run-1"
    events = []

    class FakeCluster:
        port = 55999
        owner_url = "postgresql+psycopg://owner:pw@127.0.0.1:55999/supportiq"

        def start(self):
            events.append("pg_start")

        def stop(self):
            events.append("pg_stop")

    class FakeGateway:
        port = 55998
        base_url = "http://127.0.0.1:55998"

        def start(self):
            events.append("gateway_start")

        def stop(self):
            events.append("gateway_stop")

    executed_sql = []

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, stmt):
            executed_sql.append(str(stmt))

    class FakeEngine:
        def begin(self):
            return FakeConn()

        def dispose(self):
            events.append("engine_dispose")

    class FakeServer:
        def __init__(self, config):
            self.should_exit = False

        def run(self):
            pass

    monkeypatch.setattr(runner, "create_engine", lambda *a, **kw: FakeEngine())
    monkeypatch.setattr(runner, "Database", lambda engine: SimpleNamespace(create_schema=lambda: events.append("create_schema")))
    monkeypatch.setattr(runner, "seed", lambda db, pw: events.append(("seed", tuple(sorted(pw.keys())))))
    monkeypatch.setattr(runner, "create_app", lambda **kw: object())
    monkeypatch.setattr(runner.uvicorn, "Server", FakeServer)
    monkeypatch.setattr(runner.httpx, "get", lambda *a, **kw: SimpleNamespace(status_code=200))

    def fake_playwright(cmd, **kwargs):
        if "--version" in cmd:
            return SimpleNamespace(returncode=0, stdout="Version 1.64.1\n")
        # Confirm temporary synthetic passwords were active during Playwright execution
        active_cfg = json.loads(config_file.read_text(encoding="utf-8"))
        assert active_cfg["passwords"]["customer"] != "original-secret"
        return SimpleNamespace(returncode=1, stdout="1 failed")

    with pytest.raises(RuntimeError, match="exit code 1"):
        runner.run_e2e_pipeline(
            out_dir=out_dir,
            pg_cluster_factory=FakeCluster,
            mock_gateway_factory=FakeGateway,
            playwright_runner=fake_playwright,
            config_path=config_file,
        )

    assert "pg_stop" in events
    assert "gateway_stop" in events
    assert any(sql.startswith("CREATE SCHEMA ") for sql in executed_sql)
    assert any(sql.startswith("DROP SCHEMA IF EXISTS ") and sql.endswith(" CASCADE") for sql in executed_sql)
    assert config_file.read_text(encoding="utf-8") == original_text
    assert (out_dir / "manifest.json").exists()
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "incomplete_or_failed"

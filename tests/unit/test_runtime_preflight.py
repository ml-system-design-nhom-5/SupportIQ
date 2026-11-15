import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, MagicMock
import pytest

# Ensure scripts directory is importable
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.native_runtime import (
    check_privacy_ner,
    discover_pg_bin,
    configure_runtime_environment,
    ensure_psycopg_runtime,
    preflight,
)


@pytest.fixture(autouse=True)
def isolated_runtime_environment(monkeypatch):
    monkeypatch.setenv("PATH", os.environ.get("PATH", ""))
    monkeypatch.delenv("PSYCOPG_IMPL", raising=False)
    monkeypatch.setattr("scripts.native_runtime.discover_pg_bin", lambda: None)


def test_preflight_simulated_importerror_clean_message_no_secrets(monkeypatch):
    """Preflight should report clear dependency/policy guidance without leaking credentials."""
    secret = "SUPER_SECRET_PASSWORD_98765"
    db_url = f"postgresql+psycopg://supportiq_owner:{secret}@127.0.0.1:55432/supportiq"
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("SUPPORTIQ_DATABASE_URL", db_url)

    app_control_error = ImportError(
        "no pq wrapper available.\n"
        "Attempts made:\n"
        "- couldn't import psycopg 'c' implementation: No module named 'psycopg_c'\n"
        "- couldn't import psycopg 'binary' implementation: DLL load failed while importing pq: "
        "An Application Control policy has blocked this file.\n"
        "- couldn't import psycopg 'python' implementation: libpq library not found"
    )

    with patch.dict(sys.modules, {"psycopg": None}):
        with patch("scripts.native_runtime._import_psycopg", side_effect=app_control_error):
            with pytest.raises(RuntimeError) as exc_info:
                ensure_psycopg_runtime()

    message = str(exc_info.value)
    # Must report dependency/policy information
    assert "psycopg" in message.lower() or "libpq" in message.lower()
    assert "application control" in message.lower() or "supportiq_pg_bin" in message.lower()

    # Security check: MUST NOT leak credentials
    assert secret not in message
    assert "supportiq_owner:" not in message


def test_invalid_explicit_bin_does_not_select_another_installation(tmp_path, monkeypatch):
    monkeypatch.setenv("SUPPORTIQ_PG_BIN", str(tmp_path / "missing"))
    monkeypatch.setattr("shutil.which", lambda _: "another-installation/initdb.exe")
    with pytest.raises(RuntimeError, match="SUPPORTIQ_PG_BIN"):
        discover_pg_bin()


def test_dll_directory_handle_is_retained(tmp_path, monkeypatch):
    from scripts import native_runtime
    handle = MagicMock()
    monkeypatch.setattr(os, "add_dll_directory", lambda _: handle, raising=False)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(native_runtime, "_DLL_DIRECTORIES", {})
    configure_runtime_environment(tmp_path)
    assert handle in native_runtime._DLL_DIRECTORIES.values()
    handle.close.assert_not_called()


def test_discover_pg_bin_env_override(tmp_path, monkeypatch):
    """SUPPORTIQ_PG_BIN environment variable takes precedence when it points to valid binaries."""
    fake_bin = tmp_path / "pg_bin"
    fake_bin.mkdir()
    (fake_bin / "initdb.exe").touch()

    monkeypatch.setenv("SUPPORTIQ_PG_BIN", str(fake_bin))
    discovered = discover_pg_bin()
    assert discovered == fake_bin


def test_discover_pg_bin_not_found(monkeypatch):
    """When PostgreSQL binaries cannot be found, a descriptive error is raised."""
    monkeypatch.setenv("SUPPORTIQ_PG_BIN", "C:/nonexistent/postgres/bin")
    monkeypatch.setattr("shutil.which", lambda cmd: None)
    monkeypatch.setattr("scripts.native_runtime._registry_pg_candidates", lambda: [])
    monkeypatch.setattr("scripts.native_runtime._standard_pg_candidates", lambda: [])

    with pytest.raises(RuntimeError) as exc_info:
        discover_pg_bin()
    message = str(exc_info.value)
    assert "SUPPORTIQ_PG_BIN" in message
    assert "not found" in message.lower()


def test_configure_runtime_environment_sets_impl(tmp_path, monkeypatch):
    """Preflight configures PSYCOPG_IMPL and PATH."""
    fake_bin = tmp_path / "pg_bin"
    fake_bin.mkdir()
    (fake_bin / "initdb.exe").touch()
    monkeypatch.delenv("PSYCOPG_IMPL", raising=False)

    configure_runtime_environment(fake_bin)
    assert os.environ.get("PSYCOPG_IMPL") == "python"
    assert str(fake_bin) in os.environ.get("PATH", "")


def test_preflight_reports_missing_privacy_ner_without_failing_manual_mode(monkeypatch, capsys):
    """Preflight logs a clean NER diagnostic when en_core_web_sm is unavailable without leaking secrets."""
    monkeypatch.setattr("scripts.native_runtime.discover_pg_bin", lambda: Path("C:/pg/bin"))
    monkeypatch.setattr(
        "scripts.native_runtime.ensure_psycopg_runtime",
        lambda: (SimpleNamespace(__version__="3.3.8"), SimpleNamespace(__impl__="python", version=lambda: 180006)),
    )
    monkeypatch.setattr("spacy.load", lambda _name: (_ for _ in ()).throw(OSError("missing en_core_web_sm")))

    ok, msg = check_privacy_ner()
    assert ok is False
    assert "en_core_web_sm" in msg
    assert "fail closed" in msg.lower()

    assert preflight() == 0
    captured = capsys.readouterr().out
    assert "WARNING: Privacy NER" in captured

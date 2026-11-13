"""Focused portability & CLI path tests for Task A cleanup scripts (no weights/credentials)."""

from __future__ import annotations

import importlib
import json
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pytest

from scripts import collect_final_acceptance_evidence as collector_mod
from scripts import run_closure_candidate_audit as audit_mod

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_closure_audit_cli_requires_candidate_root_and_defaults_main_root(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        audit_mod.parse_args([])

    cand_root = tmp_path / "cand_ws"
    parsed_default = audit_mod.parse_args(["--candidate-root", str(cand_root)])
    assert parsed_default.main_root.resolve() == REPO_ROOT.resolve()
    assert parsed_default.candidate_root == cand_root

    alt_main = tmp_path / "alt_main"
    parsed_custom = audit_mod.parse_args(
        ["--main-root", str(alt_main), "--candidate-root", str(cand_root), "--output-dir", str(tmp_path / "out")]
    )
    resolved = audit_mod.resolve_audit_paths(parsed_custom.main_root, parsed_custom.candidate_root, parsed_custom.output_dir)
    assert resolved["serving_dir"] == alt_main.resolve() / "artifacts/models/trained/distilbert-supportiq"
    assert resolved["old_dir"] == cand_root.resolve() / "artifacts/evaluation/task_a_closure_20261113/candidate_model"
    assert resolved["fit2_dir"] == cand_root.resolve() / "artifacts/evaluation/task_a_boundary_20261113/candidate_model_fit2"
    assert resolved["b_ds"] == cand_root.resolve() / "artifacts/evaluation/task_a_boundary_20261113/datasets"
    assert resolved["out_dir"] == (tmp_path / "out").resolve()


@contextmanager
def _preserve_target_import_state() -> Iterator[None]:
    """Snapshot and restore sys.path and loaded apps/pipeline module families across bootstrap tests."""
    saved_path = list(sys.path)
    prefixes = ("apps", "pipeline")
    saved_modules = {
        k: v
        for k, v in sys.modules.items()
        if any(k == p or k.startswith(f"{p}.") for p in prefixes)
    }
    try:
        yield
    finally:
        for k in list(sys.modules):
            if any(k == p or k.startswith(f"{p}.") for p in prefixes):
                del sys.modules[k]
        sys.modules.update(saved_modules)
        sys.path[:] = saved_path
        importlib.invalidate_caches()


def test_closure_audit_bootstrap_switches_apps_root_before_model_load(tmp_path: Path) -> None:
    fake_main = tmp_path / "fake_main"
    (fake_main / "apps").mkdir(parents=True)
    (fake_main / "apps" / "__init__.py").write_text('MARKER = "temp_fake_main"\n', encoding="utf-8")

    with _preserve_target_import_state():
        import apps as initial_apps  # noqa: F401

        audit_mod._bootstrap_target_repo(fake_main)
        import apps as reloaded_apps

        assert Path(reloaded_apps.__file__).resolve().is_relative_to(fake_main.resolve())
        assert getattr(reloaded_apps, "MARKER", None) == "temp_fake_main"


def test_closure_audit_bootstrap_evicts_pipeline_namespace_package_across_two_roots(tmp_path: Path) -> None:
    root_old = tmp_path / "root_old"
    root_new = tmp_path / "root_new"
    for root, label in ((root_old, "from_old_root"), (root_new, "from_new_root")):
        eval_dir = root / "pipeline" / "evaluation"
        eval_dir.mkdir(parents=True)
        # Keep root pipeline/ without __init__.py (namespace package: __file__ is None) like repo root.
        (eval_dir / "__init__.py").write_text("", encoding="utf-8")
        (eval_dir / "probe.py").write_text(f'ORIGIN = "{label}"\n', encoding="utf-8")

    with _preserve_target_import_state():
        for k in list(sys.modules):
            if k == "pipeline" or k.startswith("pipeline."):
                del sys.modules[k]
        sys.path.insert(0, str(root_old))
        importlib.invalidate_caches()

        import pipeline
        import pipeline.evaluation.probe as old_probe

        assert getattr(pipeline, "__file__", None) is None
        assert old_probe.ORIGIN == "from_old_root"

        audit_mod._bootstrap_target_repo(root_new)

        import pipeline as reloaded_pipeline
        import pipeline.evaluation.probe as new_probe

        assert list(reloaded_pipeline.__path__)[0] == str((root_new / "pipeline").resolve())
        assert Path(new_probe.__file__).resolve().is_relative_to(root_new.resolve())
        assert new_probe.ORIGIN == "from_new_root"


def test_collector_secrets_resolution_uses_env_explicit_or_repo_relative_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_repo = tmp_path / "repo"
    (fake_repo / ".local").mkdir(parents=True)
    (fake_repo / ".local" / "application.json").write_text(
        json.dumps({"database_url_owner": "postgresql://repo-rel/db", "passwords": {"staff": "pw"}}),
        encoding="utf-8",
    )
    explicit_file = tmp_path / "explicit.json"
    explicit_file.write_text(
        json.dumps({"database_url_owner": "postgresql://explicit/db", "passwords": {"admin": "adm"}}),
        encoding="utf-8",
    )

    monkeypatch.delenv("SUPPORTIQ_APPLICATION_SECRETS", raising=False)
    monkeypatch.setattr(collector_mod, "REPO_ROOT", fake_repo)

    url_rel, pw_rel = collector_mod.resolve_database_url()
    assert url_rel == "postgresql://repo-rel/db"
    assert pw_rel == {"staff": "pw"}

    url_exp, pw_exp = collector_mod.resolve_database_url(str(explicit_file))
    assert url_exp == "postgresql://explicit/db"
    assert pw_exp == {"admin": "adm"}

    monkeypatch.setenv(
        "SUPPORTIQ_APPLICATION_SECRETS",
        json.dumps({"database_url_owner": "postgresql://env/db", "passwords": {}}),
    )
    url_env, _ = collector_mod.resolve_database_url(str(explicit_file))
    assert url_env == "postgresql://env/db"


def test_no_machine_specific_root_literals_remain_in_owned_scripts() -> None:
    for rel in ("scripts/run_closure_candidate_audit.py", "scripts/collect_final_acceptance_evidence.py"):
        txt = (REPO_ROOT / rel).read_text(encoding="utf-8")
        assert "F:/Năm 3" not in txt
        assert r"F:\Năm 3" not in txt
        assert r"C:\Users\PC" not in txt

"""Exercise destructive cleanup only in disposable miniature repositories."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


SHELL = shutil.which("pwsh") or shutil.which("powershell")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(sys.platform != "win32" or not SHELL, reason="Windows PowerShell cleaner"),
]
SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "clean_test_cache.ps1"


@pytest.fixture
def cache_repo(tmp_path):
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    shutil.copyfile(SCRIPT, repo / "scripts" / SCRIPT.name)
    subprocess.run(["git", "init", "--quiet", str(repo)], check=True)
    return repo


def write(repo, relative):
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("keep me", encoding="utf-8")
    return path


def clean(repo, *args):
    result = subprocess.run(
        [SHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(repo / "scripts" / SCRIPT.name), *args],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result


def test_dry_run_preserves_caches_and_apply_removes_only_allowlisted_caches(cache_repo):
    caches = [write(cache_repo, p) for p in (
        ".pytest-old/value", ".pytest_cache/value", ".review-system-probe-old/value",
        "tmp/pytest/old/value", "apps/nested/__pycache__/module.pyc",
    )]
    protected = [write(cache_repo, p) for p in (
        ".venv/__pycache__/module.pyc", "data/__pycache__/module.pyc", "data/valuable.txt",
    )]
    clean(cache_repo)
    assert all(path.exists() for path in caches + protected)
    clean(cache_repo, "-Apply")
    assert all(not path.exists() for path in caches)
    assert all(path.exists() for path in protected)


def test_apply_preserves_candidates_with_tracked_descendants(cache_repo):
    tracked = write(cache_repo, ".pytest-old/nested/valuable.txt")
    subprocess.run(["git", "-C", str(cache_repo), "add", "-f", ".pytest-old"], check=True)
    clean(cache_repo, "-Apply")
    assert tracked.read_text(encoding="utf-8") == "keep me"


@pytest.mark.parametrize("location", [".pytest-linked", ".pytest-old/nested", "tmp"])
def test_apply_preserves_junctions_and_their_targets(cache_repo, tmp_path, location):
    target = tmp_path / "outside"
    valuable = write(target, "pytest/old/valuable.txt")
    junction = cache_repo / location
    junction.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [SHELL, "-NoProfile", "-Command", "New-Item -ItemType Junction -Path $env:CLEANUP_JUNCTION -Target $env:CLEANUP_TARGET | Out-Null"],
        env={**os.environ, "CLEANUP_JUNCTION": str(junction), "CLEANUP_TARGET": str(target)}, check=True,
    )
    try:
        clean(cache_repo, "-Apply")
        assert junction.is_dir()
        assert valuable.read_text(encoding="utf-8") == "keep me"
    finally:
        # Remove only the junction, never recursively walk the external target.
        if junction.exists():
            junction.rmdir()


def test_apply_refuses_while_a_pytest_session_holds_the_lock(cache_repo):
    cache = write(cache_repo, ".pytest-old/value")
    lock = cache_repo / ".pytest-cleanup.lock"
    with lock.open("a+b"):
        result = subprocess.run(
            [SHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(cache_repo / "scripts" / SCRIPT.name), "-Apply"],
            capture_output=True, text=True, timeout=30,
        )
    assert cache.exists()
    assert result.returncode != 0

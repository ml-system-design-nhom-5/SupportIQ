"""Prepare an isolated PostgreSQL cluster using native Windows PostgreSQL binaries."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import string
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / ".local"


def cluster_directory():
    # PostgreSQL's Windows command-line tools cannot round-trip all Unicode paths.
    key = hashlib.sha256(str(ROOT).encode()).hexdigest()[:12]
    return Path(os.environ.get("LOCALAPPDATA", str(LOCAL))) / "SupportIQ" / key / "postgres"


def _standard_pg_candidates():
    candidates = []
    # Discover available drives on Windows (or standard root on non-Windows)
    if sys.platform == "win32":
        drives = [f"{d}:" for d in string.ascii_uppercase if os.path.exists(f"{d}:\\")]
    else:
        drives = ["/"]

    for drive in drives:
        for prefix in ("Program Files/PostgreSQL", "Program Files (x86)/PostgreSQL", "PostgreSQL"):
            base = Path(drive) / prefix
            if base.exists():
                if (base / "bin" / "initdb.exe").exists():
                    candidates.append(base / "bin")
                try:
                    for child in base.iterdir():
                        if child.is_dir() and (child / "bin" / "initdb.exe").exists():
                            candidates.append(child / "bin")
                except OSError:
                    pass
    return candidates


def _registry_pg_candidates():
    candidates = []
    if sys.platform != "win32":
        return candidates
    try:
        import winreg
        for root_key in (winreg.HKEY_LOCAL_MACHINE,):
            for subkey_path in (r"SOFTWARE\PostgreSQL\Installations", r"SOFTWARE\WOW6432Node\PostgreSQL\Installations"):
                try:
                    with winreg.OpenKey(root_key, subkey_path) as key:
                        for index in range(winreg.QueryInfoKey(key)[0]):
                            try:
                                with winreg.OpenKey(key, winreg.EnumKey(key, index)) as installation:
                                    base_dir = winreg.QueryValueEx(installation, "Base Directory")[0]
                                    candidates.append(Path(base_dir) / "bin")
                            except OSError:
                                pass
                except OSError:
                    pass
    except ImportError:
        pass
    return candidates


def discover_pg_bin():
    """Discover PostgreSQL bin directory portably without hardcoded machine paths."""
    # 1. Explicit user override
    env_bin = os.environ.get("SUPPORTIQ_PG_BIN")
    if env_bin:
        path = Path(env_bin)
        if (path / "initdb.exe").exists() or (path / "initdb").exists():
            return path.resolve()

    # 2. PATH resolution
    which_initdb = shutil.which("initdb.exe") or shutil.which("initdb") or shutil.which("pg_ctl.exe")
    if which_initdb:
        return Path(which_initdb).resolve().parent

    # 3. Registry candidates
    for path in _registry_pg_candidates():
        if (path / "initdb.exe").exists() or (path / "initdb").exists():
            return path.resolve()

    # 4. Standard drive paths
    for path in _standard_pg_candidates():
        if (path / "initdb.exe").exists() or (path / "initdb").exists():
            return path.resolve()

    raise RuntimeError(
        "PostgreSQL binaries not found. Set SUPPORTIQ_PG_BIN to the installed PostgreSQL bin directory "
        "(e.g., C:/Program Files/PostgreSQL/16/bin)."
    )


def pg_bin():
    return discover_pg_bin()


def configure_runtime_environment(bin_path=None):
    """Configure environment variables and DLL search paths for psycopg with libpq."""
    if "PSYCOPG_IMPL" not in os.environ:
        os.environ["PSYCOPG_IMPL"] = "python"

    if bin_path is None:
        try:
            bin_path = discover_pg_bin()
        except RuntimeError:
            bin_path = None

    if bin_path is not None and Path(bin_path).exists():
        bin_str = str(Path(bin_path).resolve())
        # Prepend to PATH so ctypes.util.find_library can locate libpq
        current_path = os.environ.get("PATH", "")
        if bin_str.lower() not in current_path.lower().split(os.pathsep):
            os.environ["PATH"] = bin_str + os.pathsep + current_path

        # On Windows Python >= 3.8, add DLL directory explicitly
        if sys.platform == "win32" and hasattr(os, "add_dll_directory"):
            try:
                os.add_dll_directory(bin_str)
            except OSError:
                pass
    return bin_path


def _import_psycopg():
    import psycopg
    from psycopg import pq
    return psycopg, pq


def ensure_psycopg_runtime():
    """Verify that psycopg and libpq are functional; sanitize errors so no secrets leak."""
    bin_path = configure_runtime_environment()
    try:
        psycopg, pq = _import_psycopg()
        return psycopg, pq
    except Exception as exc:
        err_msg = str(exc)
        diagnostics = [
            "Psycopg runtime preflight check failed: unable to load libpq wrapper.",
        ]
        if "application control" in err_msg.lower():
            diagnostics.append(
                "Windows Application Control blocked binary psycopg wrapper. "
                "Ensure PSYCOPG_IMPL=python is set and an allowed PostgreSQL libpq directory is configured."
            )
        if "no pq wrapper available" in err_msg.lower() or "not found" in err_msg.lower():
            diagnostics.append(
                f"Discovered PostgreSQL bin: {bin_path or 'None'}. "
                "Set SUPPORTIQ_PG_BIN to a valid PostgreSQL bin directory containing libpq.dll."
            )
        # Note: Do not include connection strings, passwords, or secrets in the error message.
        raise RuntimeError(" ".join(diagnostics)) from None


def run(command):
    subprocess.run([str(part) for part in command], check=True, cwd=ROOT)


def preflight():
    """Run standalone preflight diagnostics."""
    bin_path = discover_pg_bin()
    print(f"Discovered PostgreSQL binaries at: {bin_path}")
    psycopg, pq = ensure_psycopg_runtime()
    impl = getattr(pq, "__impl__", "unknown")
    ver = getattr(pq, "version", lambda: "unknown")()
    print(f"Psycopg {psycopg.__version__} initialized successfully (impl: {impl}, libpq version: {ver}).")
    return 0


def prepare():
    # Ensure psycopg environment is configured and driver is ready before importing
    psycopg, _ = ensure_psycopg_runtime()
    from psycopg import sql

    LOCAL.mkdir(exist_ok=True)
    config_file = LOCAL / "application.json"
    if config_file.exists():
        config = json.loads(config_file.read_text())
    else:
        owner_password, app_password = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        config = {"owner_password": owner_password, "app_password": app_password,
                  "database_url_owner": f"postgresql+psycopg://supportiq_owner:{owner_password}@127.0.0.1:55432/supportiq",
                  "database_url_app": f"postgresql+psycopg://supportiq_app:{app_password}@127.0.0.1:55432/supportiq",
                  "passwords": {role: secrets.token_urlsafe(16) for role in ("customer", "staff", "manager", "admin")}}
        config_file.write_text(json.dumps(config, indent=2), encoding="utf-8")
    binaries, data = discover_pg_bin(), cluster_directory()
    data.parent.mkdir(parents=True, exist_ok=True)
    (LOCAL / "postgres-location.json").write_text(json.dumps({"data_directory": str(data)}), encoding="utf-8")
    if not (data / "PG_VERSION").exists():
        password_file = data.parent / "postgres-password.tmp"
        password_file.write_text(config["owner_password"], encoding="utf-8")
        try:
            run([binaries / "initdb.exe", "-D", data, "-U", "supportiq_owner", "-A", "scram-sha-256", "--encoding=UTF8", "--locale=C", "--pwfile", password_file])
        finally:
            password_file.unlink(missing_ok=True)
    status = subprocess.run([str(binaries / "pg_ctl.exe"), "-D", str(data), "status"], capture_output=True)
    if status.returncode:
        run([binaries / "pg_ctl.exe", "-D", data, "-l", data.parent / "postgres.log", "-o", '-p 55432 -h 127.0.0.1', "-w", "start"])
    with psycopg.connect(host="127.0.0.1", port=55432, user="supportiq_owner", password=config["owner_password"], dbname="postgres", autocommit=True) as connection:
        if not connection.execute("SELECT 1 FROM pg_roles WHERE rolname='supportiq_app'").fetchone():
            connection.execute(sql.SQL("CREATE ROLE supportiq_app LOGIN PASSWORD {}").format(sql.Literal(config["app_password"])))
        if not connection.execute("SELECT 1 FROM pg_database WHERE datname='supportiq'").fetchone():
            connection.execute("CREATE DATABASE supportiq OWNER supportiq_owner")
    env = {"DATABASE_URL_APP": config["database_url_app"], "SESSION_COOKIE_SECURE": "false"}
    (LOCAL / "backend.env").write_text("\n".join(f"SUPPORTIQ_{key}={value}" for key, value in env.items()) + "\n", encoding="utf-8")
    print("Native PostgreSQL ready on 127.0.0.1:55432. Credentials: .local/application.json (never commit).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["prepare", "stop", "preflight"])
    action = parser.parse_args().action
    if action == "prepare":
        prepare()
    elif action == "preflight":
        preflight()
    else:
        data = cluster_directory().resolve()
        if data.name != "postgres" or data.parent.parent.name != "SupportIQ" or not (data / "PG_VERSION").exists():
            raise SystemExit("No project-local PostgreSQL cluster to stop.")
        run([discover_pg_bin() / "pg_ctl.exe", "-D", data, "-m", "fast", "stop"])

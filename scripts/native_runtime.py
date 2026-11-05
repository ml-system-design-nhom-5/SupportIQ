"""Prepare an isolated PostgreSQL cluster using native Windows PostgreSQL binaries."""

import argparse
import json
import hashlib
import os
from pathlib import Path
import secrets
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / ".local"


def cluster_directory():
    # PostgreSQL's Windows command-line tools cannot round-trip all Unicode paths.
    key = hashlib.sha256(str(ROOT).encode()).hexdigest()[:12]
    return Path(os.environ.get("LOCALAPPDATA", str(LOCAL))) / "SupportIQ" / key / "postgres"


def pg_bin():
    candidates = [Path(os.environ.get("SUPPORTIQ_PG_BIN", "F:/PostgreSQL/bin"))]
    for drive in ("C:/Program Files/PostgreSQL", "D:/PostgreSQL"):
        base = Path(drive)
        if base.exists():
            candidates.extend(path / "bin" for path in base.iterdir())
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\PostgreSQL\Installations") as key:
            for index in range(winreg.QueryInfoKey(key)[0]):
                with winreg.OpenKey(key, winreg.EnumKey(key, index)) as installation:
                    candidates.append(Path(winreg.QueryValueEx(installation, "Base Directory")[0]) / "bin")
    except OSError:
        pass
    for path in candidates:
        if (path / "initdb.exe").exists():
            return path
    raise SystemExit("PostgreSQL binaries not found. Set SUPPORTIQ_PG_BIN to the installed PostgreSQL bin directory.")


def run(command):
    subprocess.run([str(part) for part in command], check=True, cwd=ROOT)


def prepare():
    import psycopg
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
    binaries, data = pg_bin(), cluster_directory()
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
    parser.add_argument("action", choices=["prepare", "stop"])
    action = parser.parse_args().action
    if action == "prepare":
        prepare()
    else:
        data = cluster_directory().resolve()
        if data.name != "postgres" or data.parent.parent.name != "SupportIQ" or not (data / "PG_VERSION").exists():
            raise SystemExit("No project-local PostgreSQL cluster to stop.")
        run([pg_bin() / "pg_ctl.exe", "-D", data, "-m", "fast", "stop"])

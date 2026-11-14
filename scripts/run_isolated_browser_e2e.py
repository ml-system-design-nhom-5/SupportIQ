"""Fresh isolated browser E2E execution runner for SupportIQ acceptance.

Runs the complete Playwright E2E suite against:
1. An owned, ephemeral native PostgreSQL cluster on a separate free port with an
   isolated disposable schema (`browser_e2e_<uuid>`) and synthetic temporary credentials.
2. An owned loopback EphemeralMockAIGateway (mock AI boundary clearly labeled).
3. A dedicated backend server instance serving apps/frontend/dist on an isolated port.
4. All four configured viewports (desktop, tablet, mobile, small-phone) using msedge.
5. Produces machine-generated test report (JSON), execution log, screenshots, and SHA-256 manifest
   in a unique artifact directory without overwriting older assets.
6. Strictly stops and cleans up only owned processes, schema, temporary cluster directory,
   and temporary worker credential file on completion or failure.
"""

import argparse
from contextlib import contextmanager
import datetime
import hashlib
import http.server
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import socketserver
import subprocess
import sys
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.native_runtime import configure_runtime_environment, discover_pg_bin, ensure_psycopg_runtime

# Configure PSYCOPG_IMPL=python and PostgreSQL libpq path before importing sqlalchemy/apps.backend
configure_runtime_environment()

import httpx
from pydantic import SecretStr
from sqlalchemy import create_engine, text
import uvicorn

from apps.backend.main import create_app
from apps.backend.platform.config import Settings
from apps.backend.platform.database import Database
from apps.backend.seed import seed


def compute_sha256(path: Path | str) -> str:
    """Compute lowercase SHA-256 of file on disk."""
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def get_git_commit_hash() -> str:
    """Safely obtain current git commit hash."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=True,
            cwd=str(REPO_ROOT),
        )
        return res.stdout.strip()
    except Exception:
        return "unknown"


def find_free_port(start_port: int = 8089, span: int = 400) -> int:
    """Find an available TCP port starting from start_port."""
    for port in range(start_port, start_port + span):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No free TCP port available in search range {start_port}..{start_port + span}.")


class BrowserE2EMockGatewayHandler(http.server.BaseHTTPRequestHandler):
    """Loopback mock AI gateway handler serving deterministically for browser E2E."""

    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.path in ("/health/live", "/health/ready"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status": "ready", "mock": true, "llm_enabled": false}')
            return

        if "/asset-versions" in self.path:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "release_id": "mock-e2e-policies-v1",
                "versions": {
                    "model_version": "mock-v1.0.0",
                    "kb_version": "mock-v2.0",
                    "prompt_version": "mock-grounded-v3",
                    "routing_version": "mock-router-v1",
                    "index_version": "mock-index-v1.5",
                },
            }).encode("utf-8"))
            return

        if self.path.startswith("/v1/kb-documents/"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "title": "Return Policy",
                "version": "1.0",
                "body": "Mock policy fixture for isolated browser UI verification.",
            }).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(content_length)) if content_length > 0 else {}
        path = self.path
        message = body.get("message", "")

        analysis_res = {
            "intent": {
                "label": "return_policy" if "return" in message.lower() else "delivery_status",
                "probability": 0.95,
                "confidence_band": "high",
                "source": "mock_gateway",
                "score_kind": "uncalibrated_softmax",
                "model_mode": "mock",
                "verified": True,
            },
            "routing": {
                "recommendation": "draft",
                "reason_codes": [],
                "action": "retrieve_draft",
                "requested_team": "general_support",
            },
            "alternatives": [],
            "documents": [
                {
                    "doc_id": "return-policy",
                    "document_id": "return-policy",
                    "version": "1.0",
                    "title": "Return Policy",
                    "content_hash": "mock_policy_hash_001",
                    "snippet": "Items may be returned within 30 days of confirmed delivery in original packaging.",
                    "validity": "valid",
                }
            ],
            "warnings": [],
            "versions": {
                "release_id": "mock-e2e-policies-v1",
                "model_version": "mock-v1.0.0",
                "kb_version": "mock-v2.0",
                "prompt_version": "mock-grounded-v3",
                "routing_version": "mock-router-v1",
                "index_version": "mock-index-v1.5",
            },
            "step_latency_ms": {"classify_ms": 12, "route_ms": 2, "retrieve_ms": 14},
        }

        if "/analyses" in path:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(analysis_res).encode("utf-8"))
            return

        if "/drafts" in path:
            # Valid DRAFT_STATES status without external LLM calls; leaves Reply editor open for manual reply E2E.
            draft_res = {
                "status": "llm_unavailable",
                "reason_codes": ["llm_unavailable"],
                "analysis": analysis_res,
                "draft": None,
                "step_latency_ms": {"analysis_ms": 22, "draft_ms": 1, "llm_ms": 0},
                "llm_usage": {},
                "llm_metadata": {
                    "provider": "mock_loopback_gateway",
                    "model": "mock-disabled",
                    "model_version": "mock-disabled",
                    "prompt_version": "mock-grounded-v3",
                },
                "versions": analysis_res["versions"],
            }
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(draft_res).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()


class EphemeralMockAIGateway:
    """Spins up a local loopback mock AI server in a daemon thread."""

    def __init__(self):
        self.server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), BrowserE2EMockGatewayHandler)
        self.port = self.server.server_address[1]
        self.base_url = f"http://127.0.0.1:{self.port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def start(self):
        self.thread.start()

    def stop(self):
        try:
            self.server.shutdown()
        except Exception:
            pass
        try:
            self.server.server_close()
        except Exception:
            pass


class EphemeralPostgresCluster:
    """Manages an isolated, disposable worker-owned PostgreSQL cluster on a separate free port."""

    def __init__(self, base_dir: Optional[Path] = None, port: Optional[int] = None):
        self.run_id = uuid.uuid4().hex[:10]
        local_app_data = Path(os.environ.get("LOCALAPPDATA", str(REPO_ROOT / "tmp")))
        self.base_dir = Path(base_dir) if base_dir else (local_app_data / "SupportIQ" / f"worker-e2e-{self.run_id}")
        self.data_dir = self.base_dir / "postgres"
        self.port = port or find_free_port(55500)
        self.owner_password = secrets.token_urlsafe(24)
        self.app_password = secrets.token_urlsafe(24)
        self.binaries = discover_pg_bin()
        self.started = False

    @property
    def owner_url(self) -> str:
        return f"postgresql+psycopg://supportiq_owner:{self.owner_password}@127.0.0.1:{self.port}/supportiq"

    def start(self) -> None:
        psycopg, _ = ensure_psycopg_runtime()
        from psycopg import sql

        self.base_dir.mkdir(parents=True, exist_ok=True)
        pw_file = self.base_dir / "postgres-password.tmp"
        pw_file.write_text(self.owner_password, encoding="utf-8")
        try:
            subprocess.run(
                [
                    str(self.binaries / "initdb.exe"),
                    "-D", str(self.data_dir),
                    "-U", "supportiq_owner",
                    "-A", "scram-sha-256",
                    "--encoding=UTF8",
                    "--locale=C",
                    "--pwfile", str(pw_file),
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
        finally:
            pw_file.unlink(missing_ok=True)

        subprocess.run(
            [
                str(self.binaries / "pg_ctl.exe"),
                "-D", str(self.data_dir),
                "-l", str(self.base_dir / "postgres.log"),
                "-o", f"-p {self.port} -h 127.0.0.1",
                "-w", "start",
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.started = True

        with psycopg.connect(
            host="127.0.0.1",
            port=self.port,
            user="supportiq_owner",
            password=self.owner_password,
            dbname="postgres",
            autocommit=True,
        ) as connection:
            if not connection.execute("SELECT 1 FROM pg_roles WHERE rolname='supportiq_app'").fetchone():
                connection.execute(sql.SQL("CREATE ROLE supportiq_app LOGIN PASSWORD {}").format(sql.Literal(self.app_password)))
            if not connection.execute("SELECT 1 FROM pg_database WHERE datname='supportiq'").fetchone():
                connection.execute("CREATE DATABASE supportiq OWNER supportiq_owner")

    def stop(self) -> None:
        if self.started and (self.data_dir / "PG_VERSION").exists():
            try:
                subprocess.run(
                    [str(self.binaries / "pg_ctl.exe"), "-D", str(self.data_dir), "-m", "fast", "stop"],
                    check=False,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
            except Exception:
                pass
            self.started = False
        if self.base_dir.exists():
            shutil.rmtree(self.base_dir, ignore_errors=True)


@contextmanager
def temporary_worker_application_config(config_path: Path, synthetic_passwords: Dict[str, str]):
    """Temporarily provide synthetic account passwords in .local/application.json and restore afterward."""
    had_existing = config_path.exists()
    prior_bytes = config_path.read_bytes() if had_existing else None
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps({"synthetic_worker_temp": True, "passwords": synthetic_passwords}, indent=2),
        encoding="utf-8",
    )
    try:
        yield config_path
    finally:
        if had_existing and prior_bytes is not None:
            config_path.write_bytes(prior_bytes)
        else:
            config_path.unlink(missing_ok=True)


def run_e2e_pipeline(
    out_dir: Path,
    pg_cluster_factory=EphemeralPostgresCluster,
    mock_gateway_factory=EphemeralMockAIGateway,
    playwright_runner=subprocess.run,
    config_path: Optional[Path] = None,
    project_filter: Optional[str] = None,
    grep_filter: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute the full isolated browser E2E run and return manifest dictionary."""
    print("=== Starting Fresh Isolated Browser E2E Execution ===")
    t_start = time.perf_counter()
    start_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    commit_sha = get_git_commit_hash()
    print(f"Commit HEAD: {commit_sha}")

    synthetic_passwords = {
        role: f"Synth-{role}-{secrets.token_urlsafe(12)}"
        for role in ("customer", "staff", "manager", "admin")
    }
    worker_config_path = config_path or (REPO_ROOT / ".local" / "application.json")

    pg_cluster = pg_cluster_factory()
    mock_gateway = mock_gateway_factory()
    root_engine = None
    app_engine = None
    backend_server = None
    server_thread = None
    schema = f"browser_e2e_{uuid.uuid4().hex[:10]}"

    try:
        mock_gateway.start()
        print(f"EphemeralMockAIGateway started on {mock_gateway.base_url}")

        pg_cluster.start()
        print(f"Ephemeral PostgreSQL cluster started on 127.0.0.1:{pg_cluster.port}")

        root_engine = create_engine(pg_cluster.owner_url)
        with root_engine.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        print(f"Created isolated PostgreSQL schema: {schema}")

        app_engine = create_engine(pg_cluster.owner_url, connect_args={"options": f"-csearch_path={schema}"})
        database = Database(app_engine)
        database.create_schema()
        seed(database, synthetic_passwords)
        print("Database schema created and synthetic data seeded with temporary credentials.")

        backend_port = find_free_port(8089)
        backend_url = f"http://127.0.0.1:{backend_port}"
        print(f"Selected backend port: {backend_port}")

        settings = Settings(
            database_url_app=SecretStr(f"{pg_cluster.owner_url}?options=-csearch_path%3D{schema}"),
            database_url_owner=SecretStr(pg_cluster.owner_url),
            allowed_origins=[backend_url, f"http://localhost:{backend_port}"],
            session_cookie_secure=False,
            ai_service_base_url=mock_gateway.base_url,
            backend_build="browser-e2e-isolated",
        )
        app = create_app(settings=settings, database=database, start_worker=True)

        uvicorn_config = uvicorn.Config(
            app,
            host="127.0.0.1",
            port=backend_port,
            log_level="warning",
            access_log=False,
        )
        backend_server = uvicorn.Server(uvicorn_config)
        server_thread = threading.Thread(target=backend_server.run, daemon=True)
        server_thread.start()

        ready = False
        for _ in range(60):
            try:
                r = httpx.get(f"{backend_url}/health/ready", timeout=1.0)
                if r.status_code == 200:
                    ready = True
                    break
            except Exception:
                pass
            time.sleep(0.2)

        if not ready:
            raise RuntimeError(f"Backend failed to respond at {backend_url}")
        print(f"Backend ready at {backend_url}")

        out_dir.mkdir(parents=True, exist_ok=True)
        report_json_path = out_dir / "report.json"
        playwright_log_path = out_dir / "playwright.log"

        pnpm_cmd = shutil.which("pnpm") or shutil.which("pnpm.cmd") or "pnpm"
        playwright_env = os.environ.copy()
        playwright_env["PLAYWRIGHT_BASE_URL"] = backend_url
        playwright_env["PLAYWRIGHT_OUTPUT_DIR"] = str(out_dir.resolve())
        playwright_env["PLAYWRIGHT_JSON_OUTPUT_NAME"] = str(report_json_path.resolve())
        playwright_env["pnpm_config_verify_deps_before_run"] = "false"

        pw_ver_proc = playwright_runner(
            [pnpm_cmd, "--dir", str(REPO_ROOT / "apps" / "frontend"), "exec", "playwright", "--version"],
            cwd=str(REPO_ROOT),
            env=playwright_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
        )
        playwright_version = pw_ver_proc.stdout.strip() if pw_ver_proc.returncode == 0 else "unknown"

        playwright_cmd = [
            pnpm_cmd,
            "--dir",
            str(REPO_ROOT / "apps" / "frontend"),
            "exec",
            "playwright",
            "test",
            "--reporter=json,list",
        ]
        if project_filter:
            playwright_cmd.extend(["--project", project_filter])
        if grep_filter:
            playwright_cmd.extend(["--grep", grep_filter])

        print(f"Executing command: {' '.join(playwright_cmd)}")
        run_t0 = time.perf_counter()
        with temporary_worker_application_config(worker_config_path, synthetic_passwords):
            proc = playwright_runner(
                playwright_cmd,
                cwd=str(REPO_ROOT),
                env=playwright_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
            )
        run_duration = time.perf_counter() - run_t0
        print(f"Playwright completed in {run_duration:.2f}s with exit code {proc.returncode}")

        playwright_log_path.write_text(proc.stdout, encoding="utf-8")

        report_data: Dict[str, Any] = {}
        if report_json_path.exists():
            try:
                report_data = json.loads(report_json_path.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"Warning: could not parse report.json: {e}")

        expected_views = [project_filter] if project_filter else ["desktop", "tablet", "mobile", "small-phone"]
        expected_screens = [
            "sign-in", "products", "orders", "order-received", "console", "order-replied",
            "accounts", "account-confirmation", "versions", "reports",
            "general-support", "general-request",
        ]

        assets = []
        missing_assets = []
        for view in expected_views:
            for screen in expected_screens:
                filename = f"{screen}-{view}.png"
                filepath = out_dir / filename
                if filepath.exists():
                    rel_path = str(filepath.relative_to(REPO_ROOT)).replace("\\", "/") if filepath.is_relative_to(REPO_ROOT) else str(filepath)
                    assets.append({
                        "filename": filename,
                        "rel_path": rel_path,
                        "sha256": compute_sha256(filepath),
                        "size_bytes": filepath.stat().st_size,
                        "viewport": view,
                        "screen": screen,
                    })
                elif not grep_filter:
                    missing_assets.append(filename)

        expected_screenshot_count = len(assets) if grep_filter else len(expected_views) * len(expected_screens)
        print(f"Screenshots captured: {len(assets)} / {expected_screenshot_count}")
        if missing_assets:
            print(f"Missing screenshots ({len(missing_assets)}): {missing_assets}")

        stats = report_data.get("stats", {})
        tests_passed = stats.get("expected", 0)
        tests_failed = stats.get("unexpected", 0)
        tests_flaky = stats.get("flaky", 0)
        tests_skipped = stats.get("skipped", 0)

        total_duration = time.perf_counter() - t_start
        end_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        manifest = {
            "manifest_type": "fresh_isolated_browser_execution",
            "status": "verified_fresh_execution" if proc.returncode == 0 and len(assets) == expected_screenshot_count else "incomplete_or_failed",
            "started_at": start_iso,
            "created_at": end_iso,
            "git_commit": commit_sha,
            "command": " ".join(playwright_cmd),
            "playwright_version": playwright_version,
            "execution_environment": {
                "backend_url": backend_url,
                "backend_port": backend_port,
                "ephemeral_postgres_port": pg_cluster.port,
                "isolated_schema": schema,
                "synthetic_temporary_credentials": True,
                "ephemeral_mock_ai_gateway": mock_gateway.base_url,
                "ephemeral_mock_ai_port": mock_gateway.port,
                "browser_channel": "msedge",
                "headless": True,
                "viewports": {
                    "desktop": {"width": 1440, "height": 900},
                    "tablet": {"width": 768, "height": 1024},
                    "mobile": {"width": 390, "height": 844},
                    "small-phone": {"width": 360, "height": 800},
                },
                "raw_test_results_log_attached": True,
                "log_file": "playwright.log",
                "log_sha256": compute_sha256(playwright_log_path),
                "report_json_file": "report.json",
                "report_json_sha256": compute_sha256(report_json_path) if report_json_path.exists() else None,
            },
            "mock_ai_boundary": {
                "declaration": "AI service was mocked via loopback EphemeralMockAIGateway (llm_unavailable boundary).",
                "scope": "Verifies actual built frontend (apps/frontend/dist) + actual FastAPI backend + ephemeral PostgreSQL schema, routing, navigation, manual reply flow, admin confirmation/versions/reports, general support, responsive layouts, overflow, and axe WCAG 2.2 AA accessibility. This run DOES NOT claim real ML/LLM provider acceptance, factual AI claim support, or manager escalation approval.",
                "external_provider_calls": 0,
            },
            "execution_metrics": {
                "exit_code": proc.returncode,
                "tests_passed": tests_passed,
                "tests_failed": tests_failed,
                "tests_flaky": tests_flaky,
                "tests_skipped": tests_skipped,
                "total_scenarios_configured": 1 if grep_filter else 3,
                "total_project_viewports": len(expected_views),
                "total_test_executions": tests_passed + tests_failed + tests_flaky + tests_skipped,
                "test_run_duration_seconds": round(run_duration, 2),
                "total_pipeline_duration_seconds": round(total_duration, 2),
                "screenshots_captured": len(assets),
                "screenshots_expected": expected_screenshot_count,
                "missing_assets": missing_assets,
            },
            "assets": assets,
        }

        manifest_path = out_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(f"Manifest written to {manifest_path}")

        if proc.returncode != 0:
            print("=== PLAYWRIGHT FAILURE OUTPUT ===")
            print(proc.stdout[-2000:])
            raise RuntimeError(f"Playwright tests failed with exit code {proc.returncode}")

        return manifest

    finally:
        print("=== Teardown & Schema Cleanup ===")
        if backend_server:
            backend_server.should_exit = True
            if server_thread:
                server_thread.join(timeout=3)
            print("Backend server stopped.")

        mock_gateway.stop()
        print("EphemeralMockAIGateway stopped.")

        if app_engine:
            app_engine.dispose()

        if root_engine:
            try:
                with root_engine.begin() as conn:
                    conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
                print(f"Dropped isolated PostgreSQL schema: {schema}")
            finally:
                root_engine.dispose()

        pg_cluster.stop()
        print("Ephemeral PostgreSQL cluster stopped and cleaned up.")


def main():
    parser = argparse.ArgumentParser(description="Run SupportIQ browser E2E in an isolated environment.")
    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    default_out = REPO_ROOT / "artifacts" / "browser" / f"playwright-e2e-{timestamp}"
    parser.add_argument("--out-dir", type=Path, default=default_out, help="Unique output directory for artifacts.")
    parser.add_argument("--project", type=str, default=None, help="Optional Playwright project filter.")
    parser.add_argument("--grep", type=str, default=None, help="Optional Playwright test grep filter.")
    args = parser.parse_args()
    out_dir = args.out_dir if args.out_dir.is_absolute() else (REPO_ROOT / args.out_dir)
    run_e2e_pipeline(out_dir=out_dir, project_filter=args.project, grep_filter=args.grep)


if __name__ == "__main__":
    main()

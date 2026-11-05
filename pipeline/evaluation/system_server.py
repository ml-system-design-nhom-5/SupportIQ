"""Managed loopback Demo Server process for isolated E2E system evaluation."""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from pipeline.evaluation import EvaluationError
from pipeline.evaluation.system_contracts import VerifiedSystemInputs


def find_free_port() -> int:
    """Find and return an ephemeral open loopback port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class ManagedDemoServer:
    """Owns and manages an isolated loopback demo server subprocess with run nonce
    and input fingerprint handshake verification.
    """

    def __init__(
        self,
        run_nonce: Optional[str] = None,
        input_fingerprint: Optional[str] = None,
        port: Optional[int] = None,
    ):
        self.run_nonce = run_nonce or str(uuid.uuid4())
        self.input_fingerprint = input_fingerprint or "sys-eval-fp-default"
        self.port = port
        self.process: Optional[subprocess.Popen] = None
        self.base_url: Optional[str] = None
        self.runtime_dir: Optional[Path] = None
        self.ledger_path: Optional[Path] = None
        self._inputs: Optional[VerifiedSystemInputs] = None
        self._profile = "mock"

    def start(
        self,
        inputs: VerifiedSystemInputs,
        runtime_dir: Path | str,
        ledger_path: Path | str,
        profile: str = "mock",
    ) -> str:
        """Start the managed loopback demo server subprocess and perform handshake."""
        self._inputs = inputs
        self._profile = profile
        self.runtime_dir = Path(runtime_dir).resolve()
        self.ledger_path = Path(ledger_path).resolve()

        if self.port is None:
            self.port = find_free_port()

        db_path = str(self.runtime_dir / "demo.sqlite3")
        # Pass pinned inputs, never credentials; the worker shares this run's ledger.
        inputs_path = self.runtime_dir / "server_inputs.json"
        inputs_path.write_text(json.dumps({
            "cases": [c.model_dump() for c in inputs.cases],
            "config": inputs.config.model_dump(),
            "source_paths": {k: str(v) for k, v in inputs.source_paths.items()},
            "input_hashes": inputs.input_hashes, "as_of": inputs.as_of.isoformat(),
            "coverage": inputs.coverage, "manifest": inputs.manifest,
            "profile": profile,
        }), encoding="utf-8")
        cmd = [
            sys.executable,
            "-m",
            "pipeline.evaluation.system_server",
            "--port",
            str(self.port),
            "--db-path",
            db_path,
            "--nonce",
            self.run_nonce,
            "--fingerprint",
            self.input_fingerprint,
            "--inputs", str(inputs_path),
        ]

        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.base_url = f"http://127.0.0.1:{self.port}"

        # Local encoder initialization is outside measured request latency.
        deadline = time.time() + 60.0
        health_data = None
        last_error = None

        while time.time() < deadline:
            if self.process.poll() is not None:
                raise EvaluationError("Managed demo server process exited unexpectedly during startup")
            try:
                health_data = self.check_health()
                break
            except Exception as exc:
                last_error = exc
                time.sleep(0.1)

        if not health_data:
            self.close()
            raise EvaluationError(f"Managed demo server startup timed out: {last_error}")

        self._verify_handshake(health_data)
        return self.base_url

    def check_health(self) -> Dict[str, Any]:
        """Perform HTTP GET request to /api/demo/health."""
        if not self.base_url:
            raise EvaluationError("Server is not started")
        url = f"{self.base_url}/api/demo/health"
        req = urllib.request.Request(url, headers={"User-Agent": "SupportIQ-Evaluator"})
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body)

    def _verify_handshake(self, health_response: Dict[str, Any]) -> None:
        """Verify the health response contains expected run nonce and fingerprint."""
        if not isinstance(health_response, dict):
            raise EvaluationError("Handshake failed: invalid health response format")

        if health_response.get("status") != "ok":
            raise EvaluationError(f"Handshake failed: unhealthy status '{health_response.get('status')}'")

        nonce = health_response.get("nonce")
        if self.run_nonce and nonce != self.run_nonce:
            raise EvaluationError(
                f"Handshake failed: run nonce mismatch (expected '{self.run_nonce}', got '{nonce}')"
            )

        fp = health_response.get("fingerprint")
        if self.input_fingerprint and fp != self.input_fingerprint:
            raise EvaluationError(
                f"Handshake failed: input fingerprint mismatch (expected '{self.input_fingerprint}', got '{fp}')"
            )

    def is_running(self) -> bool:
        """Return True if subprocess is alive."""
        return self.process is not None and self.process.poll() is None

    def restart(self) -> str:
        """Restart server with preserved runtime directory and database."""
        if self._inputs is None or self.runtime_dir is None or self.ledger_path is None:
            raise EvaluationError("Cannot restart server: missing initial inputs or paths")

        self.close()
        time.sleep(0.2)
        # Allocate new free port on restart to avoid TIME_WAIT collisions
        self.port = find_free_port()
        return self.start(self._inputs, self.runtime_dir, self.ledger_path, profile=self._profile)

    def close(self) -> None:
        """Terminate server process and ensure clean cleanup."""
        if self.process is not None:
            try:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(self.process.pid), "/T", "/F"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
                else:
                    self.process.terminate()
                self.process.wait(timeout=2.0)
            except Exception:
                try:
                    self.process.kill()
                    self.process.wait(timeout=2.0)
                except Exception:
                    pass
            finally:
                self.process = None


def main() -> None:
    """CLI entrypoint for managed demo server worker process."""
    parser = argparse.ArgumentParser(description="SupportIQ Managed Demo Server Loopback Worker")
    parser.add_argument("--port", type=int, required=True, help="Port to listen on")
    parser.add_argument("--db-path", type=str, required=True, help="Path to demo SQLite database")
    parser.add_argument("--nonce", type=str, default="", help="Expected run nonce")
    parser.add_argument("--fingerprint", type=str, default="", help="Expected input fingerprint")
    parser.add_argument("--inputs", required=True, help="Pinned non-secret runtime inputs")
    args = parser.parse_args()

    import uvicorn
    from apps.demo.app import create_app

    health_meta = {
        "nonce": args.nonce,
        "fingerprint": args.fingerprint,
    }
    from datetime import datetime
    from pipeline.evaluation.system_contracts import SystemCase, SystemConfig, verify_input_snapshot
    from pipeline.evaluation.system_execution import build_system_dependencies
    from dotenv import load_dotenv
    data = json.loads(Path(args.inputs).read_text(encoding='utf-8'))
    if data['profile'] == 'live':
        load_dotenv(Path(__file__).resolve().parents[2] / '.env', override=False)
    inputs = VerifiedSystemInputs(
        cases=[SystemCase.model_validate(c) for c in data['cases']],
        config=SystemConfig.model_validate(data['config']),
        source_paths={k: Path(v) for k, v in data['source_paths'].items()},
        input_hashes=data['input_hashes'], as_of=datetime.fromisoformat(data['as_of']),
        coverage=data['coverage'], manifest=data['manifest'])
    verify_input_snapshot(inputs)
    deps = build_system_dependencies(inputs, data['profile'], Path(args.db_path).parent, start_server=False)
    app = create_app(db_path=args.db_path, runner=deps.runner, health_metadata=health_meta)

    try:
        uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
    finally:
        deps.close()


if __name__ == "__main__":
    main()

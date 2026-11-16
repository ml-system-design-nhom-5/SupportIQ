"""`ai-service serve` stops on bad settings or a bad release, or runs a replica (ARCH-34)."""

import importlib.abc
import importlib.machinery
import importlib.util
import logging
import os
import subprocess
import sys
import types
from collections.abc import Callable, Iterator
from dataclasses import asdict, dataclass, field
from datetime import UTC
from http import HTTPStatus
from pathlib import Path
from typing import cast

import httpx
import pytest
from fastapi import FastAPI

from supportiq_ai_service.composition_root import cli
from supportiq_ai_service.composition_root.release_assets import ReleaseModels
from supportiq_ai_service.intent.adapters.model_artifact import ModelArtifact
from supportiq_ai_service.platform.adapters.egress import (
    ALLOW_LIST_FILE_NAME,
    EgressAllowList,
    EgressAllowListInvalidError,
    packaged_egress_allow_list,
)
from supportiq_ai_service.platform.adapters.system_clock import SystemClock
from supportiq_ai_service.retrieval.adapters.index_file import IndexConfiguration
from tests.unit.composition_root.fakes import load_fake_models
from tests.unit.platform.fakes import LLM_ENVIRONMENT, RecordingEgressClientFactory
from tests.unit.release.fakes import EXAMPLE_VERSIONS
from tests.unit.release.release_folder import (
    ASSET_FILES,
    ROUTING_DOCUMENT,
    json_file,
    with_changes,
    write_release,
)

SERVE_ARGUMENTS = ["serve", "--host", "127.0.0.1", "--port", "8000"]
SERVICE_TOKEN = "service-token-for-unit-tests"
MODELS_MODULE = "supportiq_ai_service.composition_root.release_models"
# What keeps the model library offline and silent (ADR-0018, Egress).
OFFLINE_VARIABLES = ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_HUB_DISABLE_TELEMETRY")
# The real loader, kept before the fixture `fake_models` replaces it in every test.
REAL_LOAD_RELEASE_MODELS = cli.load_release_models
BASE_URL = "http://ai-service.test"
SERVICE_TOKEN_HEADERS = {"Authorization": f"Bearer {SERVICE_TOKEN}"}


@dataclass(slots=True)
class RecordingServer:
    """Keep the application and the options that `uvicorn.run` would get."""

    runs: list[tuple[FastAPI, dict[str, object]]] = field(
        default_factory=list[tuple[FastAPI, dict[str, object]]]
    )

    def run(self, app: FastAPI, **options: object) -> None:
        """Keep the application and the options instead of serving.

        Args:
            app: The application.
            **options: The options of `uvicorn.run`.
        """
        self.runs.append((app, options))


@pytest.fixture(autouse=True)
def restored_logging() -> Iterator[None]:
    root = logging.getLogger()
    handlers, level = tuple(root.handlers), root.level
    yield
    for handler in tuple(root.handlers):
        root.removeHandler(handler)
    for handler in handlers:
        root.addHandler(handler)
    root.setLevel(level)


@pytest.fixture(autouse=True)
def fake_models(monkeypatch: pytest.MonkeyPatch) -> None:
    # The command loads the two models through this function; torch is not needed here.
    monkeypatch.setattr(cli, "load_release_models", load_fake_models)


@pytest.fixture
def server(monkeypatch: pytest.MonkeyPatch) -> RecordingServer:
    recording = RecordingServer()
    monkeypatch.setattr(cli.uvicorn, "run", recording.run)
    return recording


@pytest.fixture
def release_manifest(tmp_path: Path) -> Path:
    return write_release(tmp_path)


@pytest.fixture
def environment(monkeypatch: pytest.MonkeyPatch, release_manifest: Path) -> None:
    _set_settings(monkeypatch, str(release_manifest))


def _set_settings(monkeypatch: pytest.MonkeyPatch, release_manifest_path: str) -> None:
    monkeypatch.setenv("SERVICE_TOKEN", SERVICE_TOKEN)
    monkeypatch.setenv("RELEASE_MANIFEST_PATH", release_manifest_path)
    for name, value in LLM_ENVIRONMENT.items():
        monkeypatch.setenv(name, value)


@pytest.fixture
def client_factory(monkeypatch: pytest.MonkeyPatch) -> RecordingEgressClientFactory:
    factory = RecordingEgressClientFactory()
    monkeypatch.setattr(cli, "create_egress_client", factory)
    return factory


@pytest.mark.usefixtures("environment")
def test_serve_runs_one_replica_without_access_log_or_server_header(
    server: RecordingServer,
) -> None:
    status = cli.main(SERVE_ARGUMENTS)

    assert status == cli.EXIT_SUCCESS
    ((_app, options),) = server.runs
    assert options == {
        "host": "127.0.0.1",
        "port": 8000,
        "log_config": None,
        "access_log": False,
        "server_header": False,
    }


@pytest.mark.usefixtures("environment")
def test_invalid_settings_stop_with_status_2_before_the_server_starts(
    monkeypatch: pytest.MonkeyPatch, server: RecordingServer, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("SERVICE_TOKEN")

    status = cli.main(SERVE_ARGUMENTS)

    assert status == cli.EXIT_CONFIGURATION_INVALID
    assert not server.runs
    assert '"event":"settings.invalid"' in capsys.readouterr().out


@pytest.mark.usefixtures("environment")
def test_an_invalid_egress_allow_list_stops_with_status_2_before_the_server_starts(
    monkeypatch: pytest.MonkeyPatch, server: RecordingServer, capsys: pytest.CaptureFixture[str]
) -> None:
    def invalid_allow_list() -> EgressAllowList:
        raise EgressAllowListInvalidError(ALLOW_LIST_FILE_NAME)

    monkeypatch.setattr(cli, "packaged_egress_allow_list", invalid_allow_list)

    status = cli.main(SERVE_ARGUMENTS)

    assert status == cli.EXIT_CONFIGURATION_INVALID
    assert not server.runs
    output = capsys.readouterr().out
    assert '"event":"egress_allow_list.invalid"' in output
    assert f'"file_name":"{ALLOW_LIST_FILE_NAME}"' in output


def _flip_a_byte_of_the_weights(manifest_path: Path) -> str:
    weights = manifest_path.parent / "model" / "model.safetensors"
    content = bytearray(weights.read_bytes())
    content[0] ^= 1
    weights.write_bytes(bytes(content))
    return str(manifest_path)


def _name_a_missing_manifest(manifest_path: Path) -> str:
    return str(manifest_path.with_name("missing.json"))


def _leave_the_value_empty(manifest_path: Path) -> str:
    del manifest_path
    return ""


def _write_a_candidate(manifest_path: Path) -> str:
    return str(write_release(manifest_path.parent, gate_run=False))


def _break_the_routing_file(manifest_path: Path) -> str:
    # An intent outside the 46 labels breaks the format of the routing file.
    routing = {**ROUTING_DOCUMENT, "sensitive_intents": ["refund_now"]}
    changes = {"routing": {"routing/routing.json": json_file(routing)}}
    return str(write_release(manifest_path.parent, assets=with_changes(changes)))


# Each way to break the release, with the attributes that `release.invalid` must carry.
RELEASE_BREAKS: dict[str, tuple[Callable[[Path], str], tuple[str, ...]]] = {
    "checksum": (
        _flip_a_byte_of_the_weights,
        (
            '"reason":"checksum_mismatch"',
            '"asset":"model"',
            '"file_path":"model/model.safetensors"',
        ),
    ),
    "missing": (_name_a_missing_manifest, ('"reason":"manifest_unreadable"',)),
    "empty": (_leave_the_value_empty, ('"reason":"manifest_unreadable"',)),
    "candidate": (_write_a_candidate, ('"reason":"gate_run_missing"',)),
    "asset": (
        _break_the_routing_file,
        ('"reason":"asset_invalid"', '"asset":"routing"', '"file_path":"routing/routing.json"'),
    ),
}


@pytest.fixture(params=sorted(RELEASE_BREAKS))
def broken_release(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch, release_manifest: Path
) -> tuple[str, ...]:
    break_release, expected_attributes = RELEASE_BREAKS[request.param]
    _set_settings(monkeypatch, break_release(release_manifest))
    return expected_attributes


def test_a_release_that_fails_its_check_stops_with_status_2_before_anything_is_created(
    server: RecordingServer,
    client_factory: RecordingEgressClientFactory,
    capsys: pytest.CaptureFixture[str],
    broken_release: tuple[str, ...],
) -> None:
    status = cli.main(SERVE_ARGUMENTS)

    assert status == cli.EXIT_CONFIGURATION_INVALID
    assert not server.runs
    assert not client_factory.created
    output = capsys.readouterr().out
    assert '"event":"release.invalid"' in output
    for attribute in broken_release:
        assert attribute in output
    assert '"event":"release.loaded"' not in output
    for files in ASSET_FILES.values():
        for content in files.values():
            assert content.decode().strip() not in output


@pytest.mark.usefixtures("environment")
def test_serve_creates_one_client_of_the_packaged_allow_list_before_the_server_starts(
    server: RecordingServer, client_factory: RecordingEgressClientFactory
) -> None:
    cli.main(SERVE_ARGUMENTS)

    ((allow_list, client),) = client_factory.created
    assert allow_list == packaged_egress_allow_list()
    assert not client.is_closed
    assert len(server.runs) == 1


async def _request(app: FastAPI, method: str, path: str, body: object = None) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        return await client.request(method, path, json=body, headers=SERVICE_TOKEN_HEADERS)


@pytest.mark.anyio
@pytest.mark.usefixtures("environment")
async def test_a_replica_serves_the_versions_of_its_verified_release(
    server: RecordingServer, capsys: pytest.CaptureFixture[str]
) -> None:
    cli.main(SERVE_ARGUMENTS)
    ((app, _options),) = server.runs

    ready = await _request(app, "GET", "/health/ready")
    versions = await _request(app, "GET", "/v1/asset-versions")

    assert ready.status_code == HTTPStatus.NO_CONTENT
    assert versions.status_code == HTTPStatus.OK
    assert versions.json() == asdict(EXAMPLE_VERSIONS)
    output = capsys.readouterr().out
    assert '"event":"release.loaded"' in output
    assert f'"release_id":"{EXAMPLE_VERSIONS.release_id}"' in output


@pytest.mark.anyio
@pytest.mark.usefixtures("environment")
async def test_a_replica_analyzes_with_the_pipeline_of_its_release(server: RecordingServer) -> None:
    cli.main(SERVE_ARGUMENTS)
    ((app, _options),) = server.runs

    response = await _request(
        app, "POST", "/v1/analyses", {"message": "Hello", "as_of": "2026-11-05T09:30:00Z"}
    )

    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["intent"]["label"] == "track_order"
    # The first release holds no KB document, so every request abstains (ADR-0021).
    assert body["routing"] == {"recommendation": "abstain", "reason_codes": ["no_valid_document"]}


@pytest.mark.anyio
@pytest.mark.usefixtures("environment")
async def test_a_draft_that_routing_abstains_never_calls_the_llm(server: RecordingServer) -> None:
    cli.main(SERVE_ARGUMENTS)
    ((app, _options),) = server.runs

    response = await _request(
        app, "POST", "/v1/drafts", {"message": "Hello", "as_of": "2026-11-05T09:30:00Z"}
    )

    # An LLM call would reach the network, which unit tests block, and fail the request.
    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert (body["status"], body["reason_codes"]) == ("abstained", ["no_valid_document"])
    assert "llm_usage" not in body


@pytest.mark.anyio
@pytest.mark.usefixtures("environment")
async def test_a_release_without_kb_documents_finds_none(server: RecordingServer) -> None:
    cli.main(SERVE_ARGUMENTS)
    ((app, _options),) = server.runs

    response = await _request(app, "GET", "/v1/kb-documents/SAMPLE-REFUND-001/versions/1.0")

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json()["type"] == "urn:supportiq:problem:not-found"


class _ModelsModuleFinder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Stand in for the models module, which needs torch, and read the environment on import."""

    def __init__(
        self, load: Callable[[ModelArtifact, IndexConfiguration, int], ReleaseModels]
    ) -> None:
        """Keep the loader that the module defines.

        Args:
            load: The loader of the module.
        """
        self.environment_at_import: dict[str, str | None] | None = None
        self._load = load

    def find_spec(
        self, fullname: str, path: object, target: object = None
    ) -> importlib.machinery.ModuleSpec | None:
        """Find only the models module."""
        del path, target
        if fullname != MODELS_MODULE:
            return None
        return importlib.util.spec_from_loader(fullname, self)

    def create_module(self, spec: importlib.machinery.ModuleSpec) -> None:
        """Let Python create the module."""
        del spec

    def exec_module(self, module: types.ModuleType) -> None:
        """Keep the offline variables as the import sees them, and define the loader."""
        self.environment_at_import = {name: os.environ.get(name) for name in OFFLINE_VARIABLES}
        module.__dict__["load_release_models"] = self._load


@pytest.fixture
def models_module_not_imported(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    # The import must run in the test, so neither the module nor the attribute of its package
    # may exist before it; both are put back afterwards.
    package = sys.modules["supportiq_ai_service.composition_root"]
    monkeypatch.delattr(package, "release_models", raising=False)
    previous = sys.modules.pop(MODELS_MODULE, None)
    yield
    sys.modules.pop(MODELS_MODULE, None)
    if previous is not None:
        sys.modules[MODELS_MODULE] = previous


@pytest.mark.usefixtures("models_module_not_imported")
def test_hugging_face_is_set_offline_before_the_models_module_is_imported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in OFFLINE_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    calls: list[tuple[ModelArtifact, IndexConfiguration, int]] = []

    def load(artifact: ModelArtifact, index: IndexConfiguration, cpu_threads: int) -> ReleaseModels:
        calls.append((artifact, index, cpu_threads))
        return load_fake_models(artifact, index, cpu_threads)

    finder = _ModelsModuleFinder(load)
    monkeypatch.setattr(sys, "meta_path", [finder, *sys.meta_path])
    artifact, index = cast("ModelArtifact", object()), cast("IndexConfiguration", object())

    REAL_LOAD_RELEASE_MODELS(artifact, index, 2)

    assert finder.environment_at_import == dict.fromkeys(OFFLINE_VARIABLES, "1")
    assert calls == [(artifact, index, 2)]


def test_the_command_imports_neither_the_models_module_nor_the_model_library() -> None:
    probe = (
        "import sys, supportiq_ai_service.composition_root.cli\n"
        f"print({MODELS_MODULE!r} in sys.modules, 'transformers' in sys.modules)"
    )

    result = subprocess.run(  # noqa: S603  # the interpreter of the tests, with a fixed probe
        [sys.executable, "-c", probe], capture_output=True, text=True, check=True
    )

    assert result.stdout.strip() == "False False"


def test_serve_needs_a_host_and_a_port_and_its_clock_is_utc() -> None:
    with pytest.raises(SystemExit):
        cli.parse_arguments(["serve"])
    assert SystemClock().now().tzinfo is UTC

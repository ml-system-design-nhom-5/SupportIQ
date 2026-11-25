"""The checks of a deploy, the settings of the image, the start of the server, and its wait.

`modal_app.py` checks the price file and the release folder when it is imported on the
deploying machine, so each test imports it as the container does, with `modal.is_local()`
False, and calls the checks with its own files. One test imports it as the deploying machine
does, and the import itself stops the deploy. These tests need the `deploy` group, which CI
installs.
"""

import importlib
import json
import pwd
import shutil
import sys
from collections.abc import Callable, Iterator
from datetime import date
from pathlib import Path
from types import ModuleType

import pytest

from app.platform.settings import Settings
from tests.unit.release.release_folder import write_release

pytest.importorskip("modal", reason="the deploy group is not installed")

AI_SERVICE = Path(__file__).resolve().parents[3]
PRICE_FILE = AI_SERVICE.parent / "deploy" / "llm-prices.env"
INPUT_PRICE = 300_000
PRICE_LINES = (
    "GEMINI_MODEL=gemini-3.5-flash-lite",
    f"LLM_INPUT_PRICE_MICRO_USD_PER_MILLION_TOKENS={INPUT_PRICE}",
    "LLM_OUTPUT_PRICE_MICRO_USD_PER_MILLION_TOKENS=2500000",
    "LLM_PRICES_SOURCE=https://ai.google.dev/gemini-api/docs/pricing",
    "LLM_PRICES_READ_ON=2026-11-23",
)
IMAGE_SETTINGS = {
    "RELEASE_MANIFEST_PATH": "/srv/release/release-manifest.json",
    "GEMINI_MODEL": "gemini-3.5-flash-lite",
    "LLM_INPUT_PRICE_MICRO_USD_PER_MILLION_TOKENS": "300000",
    "LLM_OUTPUT_PRICE_MICRO_USD_PER_MILLION_TOKENS": "2500000",
}
SERVER_ACCOUNT = pwd.struct_passwd(
    ("ai-service", "x", 10001, 10001, "", "/home/ai-service", "/usr/sbin/nologin")
)


def _import_modal_app(monkeypatch: pytest.MonkeyPatch, *, is_local: bool) -> ModuleType:
    import modal  # noqa: PLC0415  # after importorskip, so the module skips without the group

    monkeypatch.setattr(modal, "is_local", lambda: is_local)
    monkeypatch.delitem(sys.modules, "modal_app", raising=False)
    return importlib.import_module("modal_app")


@pytest.fixture
def modal_app(monkeypatch: pytest.MonkeyPatch) -> Iterator[ModuleType]:
    yield _import_modal_app(monkeypatch, is_local=False)
    sys.modules.pop("modal_app", None)


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    # A repository with the price file, and the records of one published release.
    root = tmp_path / "repository"
    (root / "deploy").mkdir(parents=True)
    (root / "deploy" / "llm-prices.env").write_text("\n".join(PRICE_LINES) + "\n")
    return root


@pytest.fixture
def release(tmp_path: Path, repository: Path) -> Path:
    folder = tmp_path / "release"
    folder.mkdir()
    manifest = write_release(folder)
    release_id = json.loads(manifest.read_text())["release_id"]
    records = repository / "eval" / "releases" / release_id
    records.mkdir(parents=True)
    shutil.copyfile(manifest, records / "release-manifest.json")
    return folder


def _write_prices(tmp_path: Path, *lines: str) -> Path:
    path = tmp_path / "llm-prices.env"
    path.write_text("\n".join(lines) + "\n")
    return path


def _records(repository: Path) -> Path:
    return repository / "eval" / "releases"


def test_importing_on_the_deploying_machine_without_a_release_folder_stops_the_deploy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SUPPORTIQ_RELEASE_FOLDER", raising=False)

    with pytest.raises(Exception, match="release_folder_not_set") as refused:
        _import_modal_app(monkeypatch, is_local=True)

    sys.modules.pop("modal_app", None)
    assert type(refused.value).__name__ == "DeployRefusedError"


def test_the_app_and_its_secret_have_their_own_names(modal_app: ModuleType) -> None:
    assert modal_app.APP_NAME == "supportiq-ai-service"
    assert modal_app.SECRET_NAME == "supportiq-ai-service"
    assert modal_app.SECRET_KEYS == ("GEMINI_API_KEY", "SERVICE_TOKEN")


def test_the_committed_price_file_gives_the_four_settings_of_the_image(
    modal_app: ModuleType,
) -> None:
    settings = modal_app.image_settings(modal_app.read_llm_prices(PRICE_FILE))

    assert settings == IMAGE_SETTINGS


def test_the_committed_prices_pass_every_rule_of_the_settings_of_ai_service(
    modal_app: ModuleType,
) -> None:
    prices = modal_app.read_llm_prices(PRICE_FILE)

    # The real validators of `Settings`, the sum cap included; the secrets are synthetic.
    settings = Settings.model_validate(
        {
            "service_token": "synthetic-service-token",
            "gemini_api_key": "synthetic-gemini-key",
            "release_manifest_path": Path("/srv/release/release-manifest.json"),
            "gemini_model": prices.gemini_model,
            "llm_input_price_micro_usd_per_million_tokens": prices.input_price,
            "llm_output_price_micro_usd_per_million_tokens": prices.output_price,
        }
    )

    assert settings.gemini_model == "gemini-3.5-flash-lite"
    assert prices.source == "https://ai.google.dev/gemini-api/docs/pricing#gemini-3.5-flash-lite"
    assert prices.read_on == date(2026, 11, 23)


def test_comments_and_empty_lines_anywhere_in_the_price_file_are_skipped(
    modal_app: ModuleType, tmp_path: Path
) -> None:
    path = _write_prices(
        tmp_path, "# first", "", *PRICE_LINES[:2], "# middle", "", *PRICE_LINES[2:], "", "# end"
    )

    assert modal_app.read_llm_prices(path).input_price == INPUT_PRICE


@pytest.mark.parametrize(
    "lines",
    [
        PRICE_LINES[:-1],
        (*PRICE_LINES, PRICE_LINES[0]),
        (*PRICE_LINES, "OTHER=1"),
        (PRICE_LINES[0] + " ", *PRICE_LINES[1:]),
        ('GEMINI_MODEL="gemini-3.5-flash-lite"', *PRICE_LINES[1:]),
        ("GEMINI_MODEL=$MODEL", *PRICE_LINES[1:]),
        (PRICE_LINES[0], "LLM_INPUT_PRICE_MICRO_USD_PER_MILLION_TOKENS=0.3", *PRICE_LINES[2:]),
        (PRICE_LINES[0], "LLM_INPUT_PRICE_MICRO_USD_PER_MILLION_TOKENS=-1", *PRICE_LINES[2:]),
        (*PRICE_LINES[:3], "LLM_PRICES_SOURCE=http://ai.google.dev", PRICE_LINES[4]),
        (*PRICE_LINES[:4], "LLM_PRICES_READ_ON=2026-13-01"),
        (*PRICE_LINES[:4], "LLM_PRICES_READ_ON=23.11.2026"),
        ("GEMINI_MODEL", *PRICE_LINES[1:]),
        tuple(f"{line}\r" for line in PRICE_LINES),
    ],
    ids=[
        "missing",
        "repeated",
        "unknown",
        "space",
        "quote",
        "dollar",
        "decimal-price",
        "negative-price",
        "http-source",
        "no-such-day",
        "other-date-format",
        "no-equals-sign",
        "crlf",
    ],
)
def test_a_price_file_that_breaks_its_format_stops_the_deploy(
    modal_app: ModuleType, tmp_path: Path, lines: tuple[str, ...]
) -> None:
    with pytest.raises(modal_app.DeployRefusedError) as refused:
        modal_app.read_llm_prices(_write_prices(tmp_path, *lines))

    assert refused.value.problem is modal_app.DeployProblem.PRICE_FILE_INVALID


def test_a_missing_price_file_stops_the_deploy(modal_app: ModuleType, tmp_path: Path) -> None:
    with pytest.raises(modal_app.DeployRefusedError) as refused:
        modal_app.read_llm_prices(tmp_path / "missing.env")

    assert refused.value.problem is modal_app.DeployProblem.PRICE_FILE_UNREADABLE


@pytest.mark.parametrize(
    ("field", "value"),
    [("gemini_model", "gpt-4"), ("gemini_model", "Gemini-3"), ("input_price", -1)],
)
def test_a_value_that_breaks_a_rule_of_the_settings_of_ai_service_stops_the_deploy(
    modal_app: ModuleType, tmp_path: Path, field: str, value: object
) -> None:
    prices = modal_app.read_llm_prices(_write_prices(tmp_path, *PRICE_LINES))
    changed = type(prices)(**{**{f: getattr(prices, f) for f in prices.__slots__}, field: value})

    with pytest.raises(modal_app.DeployRefusedError) as refused:
        modal_app.check_prices_with_ai_service(changed)

    assert refused.value.problem is modal_app.DeployProblem.PRICE_FILE_INVALID


def test_a_published_release_folder_is_accepted(
    modal_app: ModuleType, release: Path, repository: Path
) -> None:
    environment = {modal_app.RELEASE_FOLDER_VARIABLE: str(release)}

    folder = modal_app.checked_release_folder(environment, _records(repository))

    assert folder == release


def test_a_release_folder_that_is_not_set_stops_the_deploy(
    modal_app: ModuleType, repository: Path
) -> None:
    with pytest.raises(modal_app.DeployRefusedError) as refused:
        modal_app.checked_release_folder({}, _records(repository))

    assert refused.value.problem is modal_app.DeployProblem.RELEASE_FOLDER_NOT_SET


@pytest.mark.parametrize("value", ["release", "~/release", "./release"])
def test_a_release_folder_that_is_not_absolute_stops_the_deploy(
    modal_app: ModuleType, repository: Path, value: str
) -> None:
    environment = {modal_app.RELEASE_FOLDER_VARIABLE: value}

    with pytest.raises(modal_app.DeployRefusedError) as refused:
        modal_app.checked_release_folder(environment, _records(repository))

    assert refused.value.problem is modal_app.DeployProblem.RELEASE_FOLDER_NOT_ABSOLUTE


def _a_file(path: Path, _release: Path) -> None:
    path.write_bytes(b"x")


def _a_link(path: Path, release: Path) -> None:
    path.symlink_to(release, target_is_directory=True)


def _nothing(_path: Path, _release: Path) -> None:
    pass


@pytest.mark.parametrize("make_entry", [_a_file, _a_link, _nothing], ids=["file", "link", "none"])
def test_a_release_folder_that_is_not_a_folder_stops_the_deploy(
    modal_app: ModuleType,
    release: Path,
    repository: Path,
    tmp_path: Path,
    make_entry: Callable[[Path, Path], None],
) -> None:
    entry = tmp_path / "entry"
    make_entry(entry, release)

    with pytest.raises(modal_app.DeployRefusedError) as refused:
        modal_app.checked_release_folder(
            {modal_app.RELEASE_FOLDER_VARIABLE: str(entry)}, _records(repository)
        )

    assert refused.value.problem is modal_app.DeployProblem.RELEASE_FOLDER_NOT_A_FOLDER


def test_a_release_folder_that_verify_release_refuses_stops_the_deploy(
    modal_app: ModuleType, release: Path, repository: Path
) -> None:
    (release / ".DS_Store").write_bytes(b"x")

    with pytest.raises(modal_app.DeployRefusedError) as refused:
        modal_app.checked_release_folder(
            {modal_app.RELEASE_FOLDER_VARIABLE: str(release)}, _records(repository)
        )

    assert refused.value.problem is modal_app.DeployProblem.RELEASE_REFUSED
    assert "file_unlisted" in str(refused.value)


def test_a_release_folder_whose_manifest_in_git_differs_stops_the_deploy(
    modal_app: ModuleType, release: Path, repository: Path
) -> None:
    (manifest,) = _records(repository).glob("*/release-manifest.json")
    manifest.write_bytes(manifest.read_bytes() + b"\n")

    with pytest.raises(modal_app.DeployRefusedError) as refused:
        modal_app.checked_release_folder(
            {modal_app.RELEASE_FOLDER_VARIABLE: str(release)}, _records(repository)
        )

    assert refused.value.problem is modal_app.DeployProblem.MANIFEST_DIFFERS_FROM_GIT


def test_a_release_folder_without_a_manifest_in_git_stops_the_deploy(
    modal_app: ModuleType, release: Path, repository: Path
) -> None:
    (manifest,) = _records(repository).glob("*/release-manifest.json")
    manifest.unlink()

    with pytest.raises(modal_app.DeployRefusedError) as refused:
        modal_app.checked_release_folder(
            {modal_app.RELEASE_FOLDER_VARIABLE: str(release)}, _records(repository)
        )

    assert refused.value.problem is modal_app.DeployProblem.MANIFEST_DIFFERS_FROM_GIT


def test_on_the_deploying_machine_the_image_adds_the_four_settings_and_the_checked_folder(
    modal_app: ModuleType, release: Path, repository: Path
) -> None:
    inputs = modal_app.deploy_inputs(
        is_local=True,
        environment={modal_app.RELEASE_FOLDER_VARIABLE: str(release)},
        repository=repository,
    )

    assert inputs.settings == IMAGE_SETTINGS
    assert inputs.release_folder == release


def test_in_the_container_nothing_of_the_machine_is_read(
    modal_app: ModuleType, tmp_path: Path
) -> None:
    inputs = modal_app.deploy_inputs(
        is_local=False, environment={}, repository=tmp_path / "no-such-repository"
    )

    assert inputs.settings == {}
    assert inputs.release_folder == Path("/srv/release")


def test_a_deploy_without_a_release_folder_defines_no_image(
    modal_app: ModuleType, repository: Path
) -> None:
    with pytest.raises(modal_app.DeployRefusedError) as refused:
        modal_app.deploy_image(is_local=True, environment={}, repository=repository)

    assert refused.value.problem is modal_app.DeployProblem.RELEASE_FOLDER_NOT_SET


@pytest.mark.parametrize(
    ("path", "is_outside"),
    [
        ("pyproject.toml", False),
        ("uv.lock", False),
        ("README.md", False),
        ("app/composition_root/cli.py", False),
        (".env", True),
        (".venv/bin/python", True),
        ("tests/conftest.py", True),
        ("modal_app.py", True),
        ("app/__pycache__/cli.cpython-314.pyc", True),
        ("app/.DS_Store", True),
        ("", True),
    ],
)
def test_only_the_entries_that_the_dockerfile_copies_enter_the_build_context(
    modal_app: ModuleType, path: str, is_outside: bool
) -> None:
    assert modal_app.is_outside_the_image(Path(path)) is is_outside


def _server_account(_name: str) -> pwd.struct_passwd:
    return SERVER_ACCOUNT


class _Starter:
    """Records the one process that it is asked to start."""

    def __init__(self) -> None:
        self.command: tuple[str, ...] = ()
        self.options: dict[str, object] = {}

    def __call__(self, command: tuple[str, ...], **options: object) -> "_Process":
        self.command = command
        self.options = options
        return _Process(None)


def test_the_server_starts_as_the_user_and_group_of_the_image_without_other_groups(
    modal_app: ModuleType,
) -> None:
    starter = _Starter()
    container = {"PATH": "/opt/venv/bin", "HOME": "/root", "SERVICE_TOKEN": "synthetic"}

    modal_app.start_server(starter, _server_account, container)

    assert starter.command == (
        "/opt/venv/bin/ai-service",
        "serve",
        "--host",
        "0.0.0.0",  # noqa: S104  # the interface that Modal reaches
        "--port",
        "8000",
    )
    assert starter.options == {
        "user": 10001,
        "group": 10001,
        "extra_groups": [],
        "env": {"PATH": "/opt/venv/bin", "HOME": "/home/ai-service", "SERVICE_TOKEN": "synthetic"},
    }


def test_the_server_gets_no_variable_of_the_modal_runtime(modal_app: ModuleType) -> None:
    container = {"PATH": "/opt/venv/bin", "MODAL_TASK_ID": "task", "MODAL_IDENTITY_TOKEN": "x"}

    environment = modal_app.server_environment(container, "/home/ai-service")

    assert environment == {"PATH": "/opt/venv/bin", "HOME": "/home/ai-service"}
    assert "MODAL_TASK_ID" in container


class _Process:
    def __init__(self, exits_after_polls: int | None, exit_status: int = 2) -> None:
        self._polls_left = exits_after_polls
        self._exit_status = exit_status

    def poll(self) -> int | None:
        if self._polls_left is None:
            return None
        if self._polls_left == 0:
            return self._exit_status
        self._polls_left -= 1
        return None


class _Clock:
    def __init__(self) -> None:
        self.now_ms = 0.0
        self.waits = 0

    def read(self) -> float:
        return self.now_ms

    def sleep(self, wait_ms: float) -> None:
        self.now_ms += wait_ms
        self.waits += 1


def test_a_server_that_exits_before_it_serves_fails_at_once_with_its_status(
    modal_app: ModuleType,
) -> None:
    clock = _Clock()

    with pytest.raises(modal_app.ServerExitedError) as exited:
        modal_app.wait_until_serving(_Process(1), lambda: False, clock.read, clock.sleep)

    assert exited.value.exit_status == 2  # noqa: PLR2004  # the status of release.invalid
    assert clock.waits == 1


def test_a_server_whose_port_opens_is_serving(modal_app: ModuleType) -> None:
    clock = _Clock()
    answers = iter([False, False, True])

    modal_app.wait_until_serving(_Process(None), lambda: next(answers), clock.read, clock.sleep)

    assert clock.waits == 2  # noqa: PLR2004  # two closed answers before the open one


def test_a_server_that_never_opens_its_port_times_out(modal_app: ModuleType) -> None:
    clock = _Clock()

    with pytest.raises(modal_app.ServerStartTimeoutError):
        modal_app.wait_until_serving(_Process(None), lambda: False, clock.read, clock.sleep)

    assert clock.now_ms >= modal_app.SERVER_STARTUP_TIMEOUT_MS

"""The Modal app of ai-service: one web function that runs `ai-service serve` (ADR-0030).

The project lead deploys it from the repository root, with the folder that
`supportiq-release download-release` printed (deploy/README.md, Modal):

    SUPPORTIQ_RELEASE_FOLDER="<release folder>" uv run --locked --project ai-service \
        --group deploy modal deploy ai-service/modal_app.py

- The image is `ai-service/Dockerfile`, the image that CI builds and that the local run uses.
  Only the four entries that it copies enter the build context, so a `.env` or `.venv` of the
  deploying machine never reaches Modal. The checked release folder is added last, with
  `copy=True` (ADR-0018, Deploy, statement 3).
- The image sets four settings: the manifest path, and the model and its two prices from
  `deploy/llm-prices.env`. The Gemini API key and the service token come only from the Modal
  Secret `supportiq-ai-service`, both keys required; this module never names a value, a default,
  or a stand-in for either (ADR-0030, The Modal function, statement 6).
- The function starts `ai-service serve` as the user `ai-service` of the image, because Modal
  runs every container as root (SEC-29), and returns only once the port accepts a connection.
  A server that exits first, such as on `release.invalid`, fails the container at once.

Modal imports this module on the deploying machine and again in the container. The checks of a
deploy run only on the deploying machine (`modal.is_local()`): in the container, the image is
built already, so nothing on the machine is read there.
"""

import os
import pwd
import re
import socket
import subprocess
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Protocol

import modal

APP_NAME = "supportiq-ai-service"
SECRET_NAME = "supportiq-ai-service"  # noqa: S105  # the name of the Modal Secret, not a secret
# The two secrets of ai-service, which only the Modal Secret holds.
SECRET_KEYS = ("GEMINI_API_KEY", "SERVICE_TOKEN")
RELEASE_FOLDER_VARIABLE = "SUPPORTIQ_RELEASE_FOLDER"
RELEASE_IN_IMAGE = "/srv/release"
MANIFEST_FILE_NAME = "release-manifest.json"
SERVER_PORT = 8000
SERVER_USER = "ai-service"
SERVER_COMMAND = (
    "/opt/venv/bin/ai-service",
    "serve",
    "--host",
    "0.0.0.0",  # noqa: S104  # Modal reaches a web server only on the external interface
    "--port",
    str(SERVER_PORT),
)
# ADR-0030, The Modal function, statements 4 and 5, and ADR-0018, Platform and scaling.
CPU_CORES = 2.0
MEMORY_MIB = 2048
SCALEDOWN_WINDOW_MS = 1_200_000
MAX_CONTAINERS = 1
MAX_CONCURRENT_INPUTS = 10
# The default `timeout` of a Modal function, until the measured cold start sets it.
SERVER_STARTUP_TIMEOUT_MS = 300_000
PRICE_NAMES = (
    "GEMINI_MODEL",
    "LLM_INPUT_PRICE_MICRO_USD_PER_MILLION_TOKENS",
    "LLM_OUTPUT_PRICE_MICRO_USD_PER_MILLION_TOKENS",
    "LLM_PRICES_SOURCE",
    "LLM_PRICES_READ_ON",
)
_POLL_INTERVAL_MS = 500
_CONNECT_TIMEOUT_MS = 1000
_MILLISECONDS_PER_SECOND = 1000
_HERE = Path(__file__).resolve().parent
# The entries of the build context that ai-service/Dockerfile copies, and nothing else.
_IMAGE_ENTRIES = frozenset({"pyproject.toml", "uv.lock", "README.md", "app"})
# A value of the price file: no space, quote, or `$`, which Compose would interpolate.
_PLAIN_VALUE = re.compile(r"[^\s'\"$]+")
_WHOLE_NUMBER = re.compile(r"0|[1-9][0-9]*")
_ISO_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


class DeployProblem(StrEnum):
    """Why a deploy stops before Modal receives anything."""

    PRICE_FILE_UNREADABLE = "price_file_missing_or_unreadable"
    PRICE_FILE_INVALID = "price_file_breaks_its_format"
    RELEASE_FOLDER_NOT_SET = "release_folder_not_set"
    RELEASE_FOLDER_NOT_ABSOLUTE = "release_folder_not_an_absolute_path"
    RELEASE_FOLDER_NOT_A_FOLDER = "release_folder_not_a_folder"
    RELEASE_REFUSED = "release_refused_by_verify_release"
    MANIFEST_DIFFERS_FROM_GIT = "manifest_differs_from_git"


class ModalAppError(Exception):
    """The root of every error of the Modal app."""


class DeployRefusedError(ModalAppError):
    """A deploy stops before Modal receives anything. The message names the problem only."""

    def __init__(self, problem: DeployProblem, detail: str = "") -> None:
        """Build the error with a message that names the problem and its detail.

        Args:
            problem: Why the deploy stops.
            detail: A name, a line number, or the refusal of `verify_release`, never a value.
        """
        super().__init__(f"The deploy is refused: {problem}.{f' ({detail})' if detail else ''}")
        self.problem = problem


class ServerExitedError(ModalAppError):
    """`ai-service serve` exited before its port opened, such as on `release.invalid`."""

    def __init__(self, exit_status: int) -> None:
        """Build the error with the exit status of the server.

        Args:
            exit_status: The exit status of `ai-service serve`.
        """
        super().__init__(f"ai-service serve exited with status {exit_status} before it served.")
        self.exit_status = exit_status


class ServerStartTimeoutError(ModalAppError):
    """`ai-service serve` did not open its port within the startup timeout."""

    def __init__(self) -> None:
        """Build the error with the timeout."""
        super().__init__(f"ai-service serve did not serve within {SERVER_STARTUP_TIMEOUT_MS} ms.")


class ServerProcess(Protocol):
    """The process of `ai-service serve`, as the wait sees it."""

    def poll(self) -> int | None:
        """Return the exit status, or None while the process runs."""
        ...


@dataclass(frozen=True, slots=True)
class LlmPrices:
    """The model of the drafts and its prices, from `deploy/llm-prices.env`.

    Attributes:
        gemini_model: The Gemini model.
        input_price: Micro-dollars for one million input tokens.
        output_price: Micro-dollars for one million output tokens, thinking tokens included.
        source: The page that the prices were read from.
        read_on: The day they were read.
    """

    gemini_model: str
    input_price: int
    output_price: int
    source: str
    read_on: date


def read_llm_prices(path: Path) -> LlmPrices:
    """Read the price file strictly: comments, empty lines, and five `NAME=value` lines.

    Args:
        path: `deploy/llm-prices.env`.

    Returns:
        The model and its prices.

    Raises:
        DeployRefusedError: The file is missing or unreadable, holds a CR, which the bash of the
            local run would read as part of a value, a name is missing, unknown, or repeated,
            or a value breaks its rule.
    """
    try:
        text = path.read_bytes().decode("ascii")
    except (OSError, UnicodeDecodeError) as error:
        raise DeployRefusedError(DeployProblem.PRICE_FILE_UNREADABLE) from error
    if "\r" in text:
        raise DeployRefusedError(DeployProblem.PRICE_FILE_INVALID, "a CR in a line end")
    values: dict[str, str] = {}
    for number, line in enumerate(text.split("\n"), start=1):
        if not line or line.startswith("#"):
            continue
        name, separator, value = line.partition("=")
        if name not in PRICE_NAMES or name in values or not separator:
            raise DeployRefusedError(DeployProblem.PRICE_FILE_INVALID, f"line {number}")
        if _PLAIN_VALUE.fullmatch(value) is None:
            raise DeployRefusedError(DeployProblem.PRICE_FILE_INVALID, f"line {number}")
        values[name] = value
    return _prices(values)


def image_settings(prices: LlmPrices) -> dict[str, str]:
    """Return the settings that the image sets: the manifest path, the model, and its prices.

    Args:
        prices: The model and its prices.

    Returns:
        The four settings, by their names in ai-service. No secret is among them.
    """
    model, input_price, output_price = PRICE_NAMES[:3]
    return {
        "RELEASE_MANIFEST_PATH": f"{RELEASE_IN_IMAGE}/{MANIFEST_FILE_NAME}",
        model: prices.gemini_model,
        input_price: str(prices.input_price),
        output_price: str(prices.output_price),
    }


def check_prices_with_ai_service(prices: LlmPrices) -> None:
    """Check the model and both prices with the rules of the settings of ai-service itself.

    The rules are those of the fields of `Settings` in `app/platform/settings.py`, read from the
    fields and never copied (CODE-48). ai-service checks the cap of the sum of both prices at
    startup. Called only on the deploying machine, like every check of a deploy.

    Args:
        prices: The model and its prices.

    Raises:
        DeployRefusedError: A value breaks the rule of its field.
    """
    # ai-service is imported only on the deploying machine (`_verified_release_id`).
    from pydantic import TypeAdapter, ValidationError  # noqa: PLC0415

    from app.platform.settings import Settings  # noqa: PLC0415

    values = {
        "gemini_model": prices.gemini_model,
        "llm_input_price_micro_usd_per_million_tokens": prices.input_price,
        "llm_output_price_micro_usd_per_million_tokens": prices.output_price,
    }
    for name, value in values.items():
        rule = TypeAdapter[object](Settings.model_fields[name].rebuild_annotation())
        try:
            rule.validate_python(value, strict=True)
        except ValidationError as error:
            raise DeployRefusedError(DeployProblem.PRICE_FILE_INVALID, name.upper()) from error


@dataclass(frozen=True, slots=True)
class DeployInputs:
    """What the image adds to `ai-service/Dockerfile`.

    Attributes:
        settings: The settings that the image sets, none of them a secret.
        release_folder: The folder that the image copies to `/srv/release`.
    """

    settings: Mapping[str, str]
    release_folder: Path


def deploy_inputs(
    *, is_local: bool, environment: Mapping[str, str], repository: Path
) -> DeployInputs:
    """Return what the image adds; on the deploying machine, after every check of a deploy.

    In the container, the image is built already, so nothing of the machine is read there.

    Args:
        is_local: Whether the module runs on the deploying machine, not in the container.
        environment: The environment of the deploy.
        repository: The root of the repository, which holds the price file and the records.

    Returns:
        On the deploying machine, the four settings and the checked release folder; in the
        container, no setting and `/srv/release`.

    Raises:
        DeployRefusedError: On the deploying machine, the price file or the release folder
            breaks its rule.
    """
    if not is_local:
        return DeployInputs(settings={}, release_folder=Path(RELEASE_IN_IMAGE))
    prices = read_llm_prices(repository / "deploy" / "llm-prices.env")
    check_prices_with_ai_service(prices)
    return DeployInputs(
        settings=image_settings(prices),
        release_folder=checked_release_folder(environment, repository / "eval" / "releases"),
    )


def checked_release_folder(environment: Mapping[str, str], records: Path) -> Path:
    """Return the release folder to deploy, once it is exactly a published release.

    Args:
        environment: The environment of the deploy, which names the folder.
        records: The release records of the repository, `eval/releases`.

    Returns:
        The folder, an absolute path.

    Raises:
        DeployRefusedError: The folder is not set, not absolute, or not a folder, or
            `verify_release` refuses it, or its manifest is not byte for byte the one in git.
    """
    text = environment.get(RELEASE_FOLDER_VARIABLE, "")
    if not text:
        raise DeployRefusedError(DeployProblem.RELEASE_FOLDER_NOT_SET, RELEASE_FOLDER_VARIABLE)
    folder = Path(text)
    if not folder.is_absolute():
        problem = DeployProblem.RELEASE_FOLDER_NOT_ABSOLUTE
        raise DeployRefusedError(problem, RELEASE_FOLDER_VARIABLE)
    if folder.is_symlink() or not folder.is_dir():
        problem = DeployProblem.RELEASE_FOLDER_NOT_A_FOLDER
        raise DeployRefusedError(problem, RELEASE_FOLDER_VARIABLE)
    release_id = _verified_release_id(folder / MANIFEST_FILE_NAME)
    in_git = records / release_id / MANIFEST_FILE_NAME
    content = (folder / MANIFEST_FILE_NAME).read_bytes()
    if in_git.is_symlink() or not in_git.is_file() or in_git.read_bytes() != content:
        raise DeployRefusedError(DeployProblem.MANIFEST_DIFFERS_FROM_GIT, release_id)
    return folder


def deploy_image(
    *, is_local: bool, environment: Mapping[str, str], repository: Path
) -> modal.Image:
    """Define the image of the function; on the deploying machine, check what it adds first.

    Args:
        is_local: Whether the module runs on the deploying machine, not in the container.
        environment: The environment of the deploy.
        repository: The root of the repository, which holds the price file and the records.

    Returns:
        The image of `ai-service/Dockerfile`, with the settings and the release folder.

    Raises:
        DeployRefusedError: On the deploying machine, the price file or the release folder
            breaks its rule.
    """
    inputs = deploy_inputs(is_local=is_local, environment=environment, repository=repository)
    settings = dict(inputs.settings)
    return (
        modal.Image.from_dockerfile(
            _HERE / "Dockerfile", context_dir=_HERE, ignore=is_outside_the_image
        )
        .env(settings)
        .add_local_dir(inputs.release_folder, RELEASE_IN_IMAGE, copy=True)
    )


def is_outside_the_image(path: Path) -> bool:
    """Tell whether a path of the build context stays out of the image.

    Modal passes each path relative to the context, and True leaves it out. Only the entries
    that the Dockerfile copies go in, without the bytecode or the Finder files of the machine.

    Args:
        path: A path of the build context, relative to it.

    Returns:
        True for every path outside `pyproject.toml`, `uv.lock`, `README.md`, and `app/`.
    """
    if not path.parts or path.parts[0] not in _IMAGE_ENTRIES:
        return True
    return "__pycache__" in path.parts or path.name == ".DS_Store"


def wait_until_serving(
    process: ServerProcess,
    accepts_connections: Callable[[], bool],
    clock_ms: Callable[[], float],
    sleep_ms: Callable[[float], None],
) -> None:
    """Wait until the server accepts a connection, and fail at once when it exits first.

    Args:
        process: The process of `ai-service serve`.
        accepts_connections: Whether its port accepts a connection now.
        clock_ms: A monotonic clock in milliseconds.
        sleep_ms: Waits the given milliseconds.

    Raises:
        ServerExitedError: The server exited before its port opened.
        ServerStartTimeoutError: The port did not open within `SERVER_STARTUP_TIMEOUT_MS`.
    """
    deadline_ms = clock_ms() + SERVER_STARTUP_TIMEOUT_MS
    while clock_ms() < deadline_ms:
        exit_status = process.poll()
        if exit_status is not None:
            raise ServerExitedError(exit_status)
        if accepts_connections():
            return
        sleep_ms(_POLL_INTERVAL_MS)
    raise ServerStartTimeoutError


def server_environment(environment: Mapping[str, str], home: str) -> dict[str, str]:
    """Return the environment of the server: the container's, without Modal's own variables.

    The server runs as an unprivileged user, so the variables of the Modal runtime, which
    ai-service never reads, stay with the root process and never reach it.

    Args:
        environment: The environment of the container, the two secrets included.
        home: The home folder of the user `ai-service`, which the image never creates.

    Returns:
        Every variable except those that start with `MODAL_`, with `HOME` of the user instead
        of the home of root.
    """
    kept = {name: value for name, value in environment.items() if not name.startswith("MODAL_")}
    return {**kept, "HOME": home}


def start_server(
    starter: Callable[..., ServerProcess],
    find_account: Callable[[str], pwd.struct_passwd],
    environment: Mapping[str, str],
) -> ServerProcess:
    """Start `ai-service serve` as the user and group `ai-service`, without other groups.

    Modal runs the container as root, so the process that serves drops to the user of the
    image (SEC-29).

    Args:
        starter: Starts a process, `subprocess.Popen` in the container.
        find_account: Finds the account of a user, `pwd.getpwnam` in the container.
        environment: The environment of the container.

    Returns:
        The process of the server.
    """
    account = find_account(SERVER_USER)
    return starter(
        SERVER_COMMAND,
        user=account.pw_uid,
        group=account.pw_gid,
        extra_groups=[],
        env=server_environment(environment, account.pw_dir),
    )


def port_accepts_connections() -> bool:
    """Tell whether the port of the server accepts a connection on the loopback interface.

    Returns:
        True once `ai-service serve` listens.
    """
    try:
        with socket.create_connection(
            ("127.0.0.1", SERVER_PORT), timeout=_CONNECT_TIMEOUT_MS / _MILLISECONDS_PER_SECOND
        ):
            return True
    except OSError:
        return False


def _prices(values: Mapping[str, str]) -> LlmPrices:
    missing = [name for name in PRICE_NAMES if name not in values]
    if missing:
        raise DeployRefusedError(DeployProblem.PRICE_FILE_INVALID, f"missing {missing[0]}")
    model, input_price, output_price, source, read_on = (values[name] for name in PRICE_NAMES)
    if not (_WHOLE_NUMBER.fullmatch(input_price) and _WHOLE_NUMBER.fullmatch(output_price)):
        raise DeployRefusedError(DeployProblem.PRICE_FILE_INVALID, "a price is not a whole number")
    if not source.startswith("https://"):
        raise DeployRefusedError(DeployProblem.PRICE_FILE_INVALID, "LLM_PRICES_SOURCE")
    return LlmPrices(model, int(input_price), int(output_price), source, _day(read_on))


def _day(text: str) -> date:
    if _ISO_DATE.fullmatch(text) is None:
        raise DeployRefusedError(DeployProblem.PRICE_FILE_INVALID, "LLM_PRICES_READ_ON")
    try:
        return date.fromisoformat(text)
    except ValueError as error:
        raise DeployRefusedError(DeployProblem.PRICE_FILE_INVALID, "LLM_PRICES_READ_ON") from error


def _verified_release_id(manifest: Path) -> str:
    # ai-service is imported only on the deploying machine: in the container, Modal imports this
    # module with its own Python, which need not hold ai-service.
    from app.release.manifest import ReleaseInvalidError, verify_release  # noqa: PLC0415

    try:
        return verify_release(manifest).manifest.release_id
    except ReleaseInvalidError as error:
        raise DeployRefusedError(DeployProblem.RELEASE_REFUSED, str(error)) from error


# ----- The app and its function -----
# Last in the module, because the module-level definition of the image runs the checks of a
# deploy on the deploying machine, and they use every function above.

_SERVER_STARTUP_TIMEOUT_S = SERVER_STARTUP_TIMEOUT_MS / _MILLISECONDS_PER_SECOND
app = modal.App(
    APP_NAME,
    image=deploy_image(is_local=modal.is_local(), environment=os.environ, repository=_HERE.parent),
)


@app.function(
    cpu=CPU_CORES,
    memory=MEMORY_MIB,
    scaledown_window=SCALEDOWN_WINDOW_MS // _MILLISECONDS_PER_SECOND,
    max_containers=MAX_CONTAINERS,
    secrets=[modal.Secret.from_name(SECRET_NAME, required_keys=list(SECRET_KEYS))],
)
@modal.concurrent(max_inputs=MAX_CONCURRENT_INPUTS)
@modal.web_server(SERVER_PORT, startup_timeout=_SERVER_STARTUP_TIMEOUT_S)  # pyright: ignore[reportUnknownMemberType]  # the Modal SDK types the function it wraps with Any, #46
def ai_service() -> None:
    """Start `ai-service serve` as its own user, and return once it serves."""
    process = start_server(subprocess.Popen, pwd.getpwnam, os.environ)
    wait_until_serving(
        process,
        port_accepts_connections,
        lambda: time.monotonic() * _MILLISECONDS_PER_SECOND,
        lambda wait_ms: time.sleep(wait_ms / _MILLISECONDS_PER_SECOND),
    )

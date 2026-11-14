"""Configuration shared by every test layer (TEST-14 to TEST-16).

Unit tests run with sockets disabled (`--disable-socket` in pyproject.toml). The integration
and contract layers get the `allow_hosts` marker here, which limits them to the loopback
addresses. Every test runs with Hugging Face offline and an empty Hugging Face home, so no
test downloads a model or reads a cached one, and without the API keys of the LLM provider,
so no test can call it (ADR-0021, CI, statement 2). Tests that load real weights carry the
marker `real_model` and point at the release assets themselves.
"""

import os
import shutil
import tempfile
from pathlib import Path

import pytest
from hypothesis import settings

OFFLINE_ENVIRONMENT = {"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"}
HUGGING_FACE_HOME_VARIABLE = "HF_HOME"
PROVIDER_KEY_VARIABLES = ("GEMINI_API_KEY", "GOOGLE_API_KEY")
_TESTS_ROOT = Path(__file__).parent
_LAYERS_WITH_LOOPBACK = frozenset({"integration", "contract"})
_LOOPBACK_ADDRESSES = ["127.0.0.1", "::1"]
_HYPOTHESIS_PROFILE = "deterministic"
_HUGGING_FACE_HOME_PREFIX = "supportiq-hf-home-"


def pytest_configure() -> None:
    """Make Hypothesis repeatable, and set the environment before any test imports a library.

    The Hugging Face libraries read their environment when they are imported, so the
    environment is set here, before the test modules are collected.
    """
    settings.register_profile(_HYPOTHESIS_PROFILE, derandomize=True, database=None, deadline=None)
    settings.load_profile(_HYPOTHESIS_PROFILE)
    os.environ.update(OFFLINE_ENVIRONMENT)
    os.environ[HUGGING_FACE_HOME_VARIABLE] = tempfile.mkdtemp(prefix=_HUGGING_FACE_HOME_PREFIX)
    for name in PROVIDER_KEY_VARIABLES:
        os.environ.pop(name, None)


def pytest_unconfigure() -> None:
    """Remove the empty Hugging Face home of the session."""
    shutil.rmtree(os.environ[HUGGING_FACE_HOME_VARIABLE], ignore_errors=True)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Let the tests of the integration and contract layers reach the loopback addresses.

    Args:
        items: The collected tests.
    """
    for item in items:
        layer = item.path.relative_to(_TESTS_ROOT).parts[0]
        if layer in _LAYERS_WITH_LOOPBACK:
            item.add_marker(pytest.mark.allow_hosts(_LOOPBACK_ADDRESSES))


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    """Run async tests on asyncio, the event loop of uvicorn."""
    return "asyncio"

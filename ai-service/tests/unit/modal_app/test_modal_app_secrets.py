"""The Modal app never sets a secret: the Modal Secret is the only source of both values.

The project lead required on 2026-11-22 that the app never sets the Gemini API key or the
service token, a default, or a stand-in (ADR-0030, The Modal function, statement 6). These tests
read the source of `modal_app.py`, so they run without the `deploy` group.
"""

import ast
from pathlib import Path

MODAL_APP = Path(__file__).resolve().parents[3] / "modal_app.py"
SECRET_NAMES = frozenset({"GEMINI_API_KEY", "SERVICE_TOKEN"})
# Every way to name a Modal Secret other than by its name in the workspace.
OTHER_SECRET_SOURCES = frozenset({"from_dict", "from_local_environ", "from_dotenv", "from_id"})
ENVIRONMENT_WRITES = frozenset({"update", "setdefault", "__setitem__", "putenv", "unsetenv"})


def _tree() -> ast.Module:
    return ast.parse(MODAL_APP.read_text(encoding="utf-8"))


def _secret_keys_value(tree: ast.Module) -> ast.expr:
    for node in tree.body:
        if isinstance(node, ast.Assign) and [ast.unparse(t) for t in node.targets] == [
            "SECRET_KEYS"
        ]:
            return node.value
    message = "modal_app.py defines no SECRET_KEYS"
    raise AssertionError(message)


def test_the_two_secret_names_appear_only_in_secret_keys() -> None:
    tree = _tree()
    allowed = {id(node) for node in ast.walk(_secret_keys_value(tree))}

    named = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and node.value in SECRET_NAMES
    ]

    assert sorted(str(node.value) for node in named) == sorted(SECRET_NAMES)
    assert all(id(node) in allowed for node in named)


def test_no_code_writes_the_environment() -> None:
    tree = _tree()

    writes = [
        ast.unparse(node)
        for node in ast.walk(tree)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in ENVIRONMENT_WRITES
            and "environ" in ast.unparse(node.func.value)
        )
        or (isinstance(node, ast.Call) and ast.unparse(node.func) in {"os.putenv", "os.unsetenv"})
        or (
            isinstance(node, (ast.Assign, ast.AugAssign, ast.Delete))
            and "environ[" in ast.unparse(node)
        )
    ]

    assert writes == []


def test_the_only_secret_is_the_named_one_with_both_keys_required() -> None:
    calls = [
        node
        for node in ast.walk(_tree())
        if isinstance(node, ast.Call) and ast.unparse(node.func).startswith("modal.Secret.")
    ]

    assert [ast.unparse(call) for call in calls] == [
        "modal.Secret.from_name(SECRET_NAME, required_keys=list(SECRET_KEYS))"
    ]
    assert not any(ast.unparse(call.func).split(".")[-1] in OTHER_SECRET_SOURCES for call in calls)


def test_the_image_sets_only_the_settings_that_image_settings_returns() -> None:
    env_calls = [
        ast.unparse(node)
        for node in ast.walk(_tree())
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "env"
    ]

    assert env_calls[-1].endswith(".env(settings)")
    assert len(env_calls) == 1

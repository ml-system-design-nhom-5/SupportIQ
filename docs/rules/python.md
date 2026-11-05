# Python rules

> **Status:** Active · **Owner:** backend and ai-service · **Last reviewed:** 2026-10-23

Python-specific rules for `backend`, `ai-service`, `ml`, `eval`, and Python scripts. They build on [code.md](code.md); where both apply, both must hold.

## Toolchain

**PY-01.** All Python code uses one Python version, pinned in `.python-version` and in `requires-python` of each `pyproject.toml`. The version is fixed at scaffold ([ADR-0003](../decisions/0003-tech-stack.md)).

**PY-02.** `uv` manages environments and dependencies. `uv.lock` is committed. Instructions and scripts never use `pip install`.

**PY-03.** The following tools run in pre-commit and CI with zero warnings:

| Tool | Purpose | Required configuration |
|---|---|---|
| `ruff format` | Formatting | `line-length = 100` |
| `ruff check` | Linting | Rule sets below |
| `pyright` | Type checking | `typeCheckingMode = "strict"` |
| `pytest` | Tests | Random order, network disabled, coverage thresholds ([testing.md](testing.md#coverage)) |
| `import-linter` | Layer and feature boundaries | Contracts matching [architecture.md](architecture.md#layers) |

**PY-04.** Ruff enables at least these rule sets:

| Rule set | Why |
|---|---|
| `E`, `W`, `F` | Style errors and undefined or unused names |
| `I` | Import sorting |
| `N` | Naming conventions |
| `D` with `convention = "google"` | Docstrings |
| `ANN` | Complete annotations; no `Any` (`ANN401`) |
| `B`, `PIE`, `RUF` | Likely bugs |
| `S` | Security checks |
| `ASYNC` | Blocking calls in async code |
| `DTZ` | Naive datetimes |
| `T20` | No `print` |
| `ERA` | No commented-out code |
| `C90`, `PL` | Complexity limits |
| `PT` | Pytest style |
| `PTH` | `pathlib` instead of `os.path` |
| `RET`, `SIM`, `C4` | Simpler control flow and comprehensions |
| `TRY`, `EM` | Exception style |
| `ARG` | Unused arguments |
| `TID` | Banned imports, no relative imports |

**PY-05.** Complexity limits are configured to match [CODE-11](code.md#functions): `max-complexity = 8`, `max-args = 5`, `max-branches = 8`, `max-returns = 4`, `max-statements = 30`, and `max-nested-blocks = 3` where available.

## Project layout

**PY-06.** Each component uses the `src` layout: `src/supportiq_<component>/`. Package and module names are `snake_case`.

**PY-07.** Tests live under `tests/unit/`, `tests/integration/`, and `tests/contract/`, mirroring the source tree.

**PY-08.** Every package `__init__.py` declares `__all__` for its public API and contains no logic.

## Naming

**PY-09.** `snake_case` for functions, methods, variables, and modules. `PascalCase` for classes, protocols, type aliases, and enums. `UPPER_SNAKE_CASE` for module-level constants and enum members.

**PY-10.** Enum member values match the contract exactly: `ReasonCode.LOW_CONFIDENCE = "low_confidence"`.

**PY-11.** Names starting with `_` are private. Importing a private name from another module is forbidden.

## Types

**PY-12.** Every function and method is fully annotated, including `-> None`. `Any` is forbidden. `object` is not used as a substitute for `Any`. `typing.cast` is allowed only in boundary parsing, with a comment.

**PY-13.** Suppressions follow [RULE-04](README.md#suppressions): `# type: ignore[<code>]  # <reason>, #<issue>` and `# noqa: <code>  # <reason>`. Bare forms fail CI.

**PY-14.** Identifiers and domain quantities use `NewType` or small frozen dataclasses: `TicketId = NewType("TicketId", str)`.

**PY-15.** Ports are `typing.Protocol` classes defined in the domain layer.

**PY-16.** Domain objects are `@dataclass(frozen=True, slots=True)`. Pydantic models exist only at boundaries: interface models generated from contracts, adapters, and settings. Mapping between Pydantic and domain types happens in the interface and adapter layers.

**PY-17.** String enums use `enum.StrEnum`. Closed sets are never typed as plain `str`.

**PY-18.** Exhaustive matching uses `match` with `typing.assert_never` in the final `case _:`.

**PY-19.** Use built-in generics (`list[int]`), `X | None`, and the `type` statement for aliases. Domain collections are `tuple[...]`, `frozenset[...]`, or `Mapping[...]`.

## Errors

**PY-20.** Each component defines one root error class (`BackendError`, `AiServiceError`, `MlError`) and specific subclasses per failure (`NoValidDocumentError`). Domain failures never raise built-in exceptions such as `Exception`, `ValueError`, or `RuntimeError`.

**PY-21.** Bare `except:` is forbidden. `except Exception` is allowed only in the interface layer's exception handler and in top-level task runners, which log the error once and convert it.

**PY-22.** Re-raise with `raise NewError(...) from error`. Never drop the cause.

**PY-23.** Error messages are built inside the exception class, not at the raise site (ruff `EM`, `TRY003`). Messages never contain confidential data ([security-and-privacy.md](security-and-privacy.md#data-classification)).

## Functions, state, and standard library

**PY-24.** Mutable default arguments, `global`, and `nonlocal` are forbidden.

**PY-25.** Optional parameters are keyword-only: `def fetch_order_context(order_id: OrderId, *, timeout_ms: int) -> OrderContext`.

**PY-26.** Datetimes are timezone-aware and in UTC. The current time comes from the injected `Clock`. Naive datetimes are bugs.

**PY-27.** Paths use `pathlib.Path`. String concatenation of paths is forbidden.

**PY-28.** `print` is forbidden. Logging goes through the component's logging setup ([logging-and-observability.md](logging-and-observability.md)).

**PY-29.** `assert` is used only in tests and for `assert_never`. Runtime checks raise specific errors.

## Async and I/O

**PY-30.** HTTP handlers and adapters that do I/O are `async`. Blocking calls (synchronous HTTP clients, `time.sleep`, synchronous database drivers) inside async code are forbidden.

**PY-31.** CPU-bound work that can take more than a few milliseconds, such as model inference, runs in a worker thread (`asyncio.to_thread`) so it never blocks the event loop.

**PY-32.** Every awaited I/O has a timeout: client-level timeouts on `httpx.AsyncClient`, plus `asyncio.timeout()` around composite operations, using values from settings.

**PY-33.** Concurrent calls use `asyncio.TaskGroup`. Fire-and-forget tasks are forbidden; every task is awaited or owned by a supervised group.

**PY-34.** HTTP clients, database engines, and loaded models are created once in the FastAPI lifespan and closed on shutdown.

## FastAPI

**PY-35.** Request and response models are generated from `contracts/`. Handlers declare them explicitly and never return raw dictionaries.

**PY-36.** Handlers are thin: parse, call one use case, map the result. Handlers contain no business logic and never access the database or the LLM.

**PY-37.** Dependencies reach handlers only through FastAPI dependency injection, provided by the composition root. Module-level clients are forbidden.

**PY-38.** One exception handler per component maps domain errors to contract responses and Problem Details. Handlers never build error responses themselves.

## Persistence (`backend`)

**PY-39.** SQLAlchemy 2 typed ORM models (`Mapped[...]`) exist only inside adapters. Repositories return domain objects, never ORM objects.

**PY-40.** Every schema change is one Alembic migration with a working downgrade. A merged migration is never edited.

**PY-41.** Transactions belong to the application layer (unit of work). Repositories and handlers never commit.

**PY-42.** SQL is never built with string formatting. Use the ORM or bound parameters.

## Settings

**PY-43.** Each component has one settings class (`pydantic-settings`) created in the composition root. Reading `os.environ` anywhere else is forbidden.

**PY-44.** Secrets are typed `SecretStr` and never appear in logs, error messages, or `repr`.

## Docstrings

**PY-45.** Docstrings use the Google style. The summary line is in the imperative mood and ends with a period.

## Dependencies

**PY-46.** Runtime and development dependencies are separate dependency groups in `pyproject.toml`. Every dependency is justified in the PR that adds it ([WF-27](workflow.md#dependencies)).

# The images of the offline evaluation gate (DATA-57, ADR-0021), built by run-gate.sh from the
# repository root with this file's Dockerfile.dockerignore, so each image matches one commit.
# Both base images are pinned by digest, as in ai-service/Dockerfile and backend/Dockerfile
# (WF-20). No image holds a secret, a model weight, or a development credential (SEC-29): the
# candidate is mounted read-only at run time.
#
# - gate: one environment with ai-service and its torch and dev groups, the release command,
#   and the tests of ai-service, for its guardrail tests and `supportiq-release run-gate`.
# - backend-guardrails: backend with its dev group, for its guardrail tests against the
#   throwaway PostgreSQL of compose.yaml.

# ----- gate -----

# Python 3.14.4, the version of .python-version (PY-01).
FROM python:3.14.4-slim@sha256:2ca02f32b4d9d893863367ce07ec1972819f476dd38d8612f2a9cb6a41cbb727 AS gate-build
# uv 0.11.11, the version that CI pins.
COPY --from=ghcr.io/astral-sh/uv:0.11.11@sha256:798712e57f879c5393777cbda2bb309b29fcdeb0532129d4b1c3125c5385975a /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
# The two projects keep their layout, so the path dependency ../../ai-service of eval/release
# resolves and `uv export --locked` can check that its lock is current.
WORKDIR /build/ai-service
# 1. ai-service from its lock, with the torch group to load the model of a candidate and the
#    dev group to run its guardrail tests (ADR-0021, Python and dependencies, statement 2).
COPY ai-service/pyproject.toml ai-service/uv.lock ai-service/README.md ./
RUN uv sync --locked --group torch --group dev --no-install-project
COPY ai-service/src ./src
RUN uv sync --locked --group torch --group dev --no-editable
# 2. The runtime dependencies of eval/release from its lock, with their hashes and without
#    resolving. A package that both locks pin at different versions stops the build with its
#    name and both versions, so this step never replaces a version of step 1 without a word.
WORKDIR /build/eval/release
COPY eval/release/pyproject.toml eval/release/uv.lock eval/release/README.md ./
COPY eval/release/gate/check_locks.py /build/check_locks.py
RUN uv export --locked --no-dev --no-emit-project --no-emit-package supportiq-ai-service \
        --format requirements-txt --output-file /tmp/release-requirements.txt \
    && uv pip freeze --python /opt/venv > /tmp/installed.txt \
    && python3 -I /build/check_locks.py /tmp/installed.txt /tmp/release-requirements.txt \
    && uv pip install --python /opt/venv --require-hashes --no-deps \
        --requirement /tmp/release-requirements.txt
# 3. The release command itself, without dependencies, then a check that every installed
#    package has its requirements.
COPY eval/release/src ./src
RUN uv pip install --python /opt/venv --no-deps . \
    && uv pip check --python /opt/venv

FROM python:3.14.4-slim@sha256:2ca02f32b4d9d893863367ce07ec1972819f476dd38d8612f2a9cb6a41cbb727 AS gate
# A non-root user without a home or a shell (SEC-29). run-gate.sh runs every container as the
# caller instead, so the records and the test reports belong to them.
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin gate
COPY --from=gate-build /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1
# The tests of ai-service and the pytest settings of its pyproject.toml, so that
# `pytest tests/integration/guardrails` runs here against the installed ai-service.
WORKDIR /srv/ai-service
COPY ai-service/pyproject.toml ./
COPY ai-service/tests ./tests
USER gate

# ----- backend-guardrails -----

FROM python:3.14.4-slim@sha256:2ca02f32b4d9d893863367ce07ec1972819f476dd38d8612f2a9cb6a41cbb727 AS backend-guardrails
COPY --from=ghcr.io/astral-sh/uv:0.11.11@sha256:798712e57f879c5393777cbda2bb309b29fcdeb0532129d4b1c3125c5385975a /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
# A non-root user without a home or a shell (SEC-29); run-gate.sh runs the tests as the caller.
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin backend
WORKDIR /srv/backend
# backend with its dev group from its lock, as the CI job backend-tests installs it.
COPY backend/pyproject.toml backend/uv.lock backend/README.md ./
RUN uv sync --locked --no-install-project
COPY backend/src ./src
RUN uv sync --locked
# The tests read the source of backend (the outbound guardrail), and the default TLS of a
# replica reads the authority in certs/ (backend README, TLS to the database).
COPY backend/tests ./tests
COPY backend/seed ./seed
COPY backend/certs ./certs
USER backend

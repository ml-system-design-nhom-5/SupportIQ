# The image of one ai-service replica (ARCH-10). CI builds it. Both base images are pinned
# by digest, so every build starts from the same layers (WF-20). The image holds no secret,
# no model weight, and no development credential (SEC-29): settings come from the
# environment at run time, and the release assets are added at deploy time (ADR-0018,
# Deploy).

# Python 3.14.4, the version of ../.python-version (PY-01).
FROM python:3.14.4-slim@sha256:2ca02f32b4d9d893863367ce07ec1972819f476dd38d8612f2a9cb6a41cbb727 AS build
# uv 0.11.11, the version that CI pins.
COPY --from=ghcr.io/astral-sh/uv:0.11.11@sha256:798712e57f879c5393777cbda2bb309b29fcdeb0532129d4b1c3125c5385975a /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /build
# The runtime dependencies first, from the lockfile only, so code changes reuse this layer.
# The image runs the real model, so it installs torch from the CPU index (ADR-0021, Python
# and dependencies, statement 2).
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --group torch --no-install-project
COPY src ./src
RUN uv sync --locked --no-dev --group torch --no-editable

FROM python:3.14.4-slim@sha256:2ca02f32b4d9d893863367ce07ec1972819f476dd38d8612f2a9cb6a41cbb727 AS runtime
# A non-root user without a home or a shell (SEC-29).
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin ai-service
COPY --from=build /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1
WORKDIR /srv/ai-service
USER ai-service
EXPOSE 8000

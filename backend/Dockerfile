# The image of one backend replica (ARCH-10). CI builds it; Docker Compose comes with deploy/
# once ADR-0011 or the hosting ADR is accepted (backend foundation design, Rollout, step 4).
# Both base images are pinned by digest, so every build starts from the same layers (WF-20).
# The image holds no secret and no development credential (SEC-29): settings come from the
# environment at run time.

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
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project
COPY src ./src
RUN uv sync --locked --no-dev --no-editable

FROM python:3.14.4-slim@sha256:2ca02f32b4d9d893863367ce07ec1972819f476dd38d8612f2a9cb6a41cbb727 AS runtime
# A non-root user without a home or a shell (SEC-29).
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin backend
COPY --from=build /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
# The seed and reset commands read the seed file from the working directory.
WORKDIR /srv/backend
COPY seed ./seed
USER backend
EXPOSE 8000
# Migrate, seed, and reset run as one-off commands of this image, never at startup (ADR-0011).
CMD ["backend", "serve", "--host", "0.0.0.0", "--port", "8000"]

# syntax=docker/dockerfile:1

FROM node:24-slim AS frontend-builder
WORKDIR /app/apps/frontend
RUN npm install -g pnpm@10
COPY apps/frontend/package.json apps/frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY apps/frontend/ ./
RUN pnpm build

FROM python:3.12-slim AS backend
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
COPY apps/backend/requirements.txt /tmp/backend-requirements.txt
RUN pip install --no-cache-dir -r /tmp/backend-requirements.txt \
    && rm -f /tmp/backend-requirements.txt \
    && python -c "import spacy; spacy.load('en_core_web_sm')"
COPY apps/__init__.py /app/apps/__init__.py
COPY apps/backend /app/apps/backend
COPY apps/core_backend /app/apps/core_backend
COPY data/knowledge/mock_orders.json /app/data/knowledge/mock_orders.json
COPY --from=frontend-builder /app/apps/frontend/dist /app/apps/frontend/dist
RUN groupadd --gid 10001 supportiq \
    && useradd --uid 10001 --gid 10001 --create-home supportiq \
    && mkdir -p /run/supportiq \
    && chown supportiq:supportiq /run/supportiq
USER supportiq
EXPOSE 8080
CMD ["python", "-m", "apps.backend.docker_init", "backend"]

FROM python:3.12-slim AS ai-service
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/cache/huggingface \
    HF_HUB_CACHE=/cache/huggingface/hub \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    HF_HUB_DISABLE_TELEMETRY=1
WORKDIR /app
COPY pipeline/requirements-transformers.txt /tmp/requirements-transformers.txt
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu "torch>=2.0.0" \
    && pip install --no-cache-dir -r /tmp/requirements-transformers.txt \
       fastapi==0.162.0 uvicorn==0.54.0 httpx==0.28.1 pydantic-settings==2.16.2 numpy \
    && rm -f /tmp/requirements-transformers.txt \
    && python -c "import torch; assert torch.version.cuda is None and not torch.cuda.is_available()"
COPY apps/__init__.py /app/apps/__init__.py
COPY apps/ai_service /app/apps/ai_service
COPY apps/ml_inference /app/apps/ml_inference
COPY apps/core_backend /app/apps/core_backend
COPY data/knowledge/approved_kb.v2.json /app/data/knowledge/approved_kb.v2.json
RUN groupadd --gid 10001 supportiq \
    && useradd --uid 10001 --gid 10001 --create-home supportiq \
    && mkdir -p /cache/huggingface
USER supportiq
EXPOSE 8002
CMD ["uvicorn", "apps.ai_service.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8002", "--no-access-log"]

"""Local AI gateway. External LLM calls are disabled until explicitly enabled."""

from contextlib import asynccontextmanager
import hashlib
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from supportiq_ai_service.platform.adapters.egress import (
    create_egress_client,
    packaged_egress_allow_list,
)

from .engine import Engine
from .drafting import BudgetedDraftClient


_ROOT = Path(__file__).resolve().parents[2]


class AiSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(_ROOT / ".env"), ".env"),
        extra="ignore"
    )
    gemini_api_key: SecretStr = SecretStr("")
    gemini_model: str = "gemini-3.5-flash-lite"
    supportiq_enable_llm: bool = True


class SuggestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=4000)
    order_context: dict = Field(default_factory=dict)
    as_of: str
    intent_override: str | None = None

    @model_validator(mode="after")
    def check_context(self):
        allowed = {"order_status", "placed_at", "order_total", "shipping_cost", "shipment_status", "estimated_delivery_at", "delivered_at", "refund_status", "refund_amount", "refund_requested_at"}
        if not self.order_context.keys() <= allowed:
            raise ValueError("Order context must not contain identifiers or personal data")
        from datetime import datetime, timezone
        as_of_clean = self.as_of.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(as_of_clean)
        except ValueError:
            raise ValueError("as_of requires a valid timestamp")
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
            self.as_of = dt.isoformat()
        return self


_BOUNDED_GATEWAY_CODES = frozenset({
    "ml_timeout",
    "ml_error",
    "ml_unavailable",
    "encoder_unavailable",
    "encoder_failure",
    "encoder_failed",
    "ai_service_unavailable",
})


def _gateway_http_error(
    status_code: int,
    error_code: str,
    message: str,
    reason_codes: list[str] | None = None,
) -> HTTPException:
    codes = reason_codes or (
        [error_code] if error_code == "ai_service_unavailable" else [error_code, "ai_service_unavailable"]
    )
    return HTTPException(
        status_code=status_code,
        detail={"error_code": error_code, "reason_codes": codes, "message": message},
        headers={"X-SupportIQ-Error-Code": error_code},
    )


def _execute_gateway_call(call, *, unavailability_message: str):
    try:
        return call()
    except HTTPException:
        raise
    except TimeoutError:
        raise _gateway_http_error(504, "ml_timeout", "Inference timed out") from None
    except Exception as exc:
        explicit_code = getattr(exc, "code", None)
        if explicit_code == "ml_timeout":
            raise _gateway_http_error(504, "ml_timeout", "Inference timed out") from None
        if isinstance(explicit_code, str) and explicit_code in _BOUNDED_GATEWAY_CODES:
            reason_codes = (
                ["encoder_failure", "encoder_failed", "ai_service_unavailable"]
                if explicit_code in ("encoder_failure", "encoder_failed")
                else [explicit_code, "ai_service_unavailable"]
            )
            canonical = "encoder_failure" if explicit_code == "encoder_failed" else explicit_code
            raise _gateway_http_error(503, canonical, unavailability_message, reason_codes=reason_codes) from None
        raise _gateway_http_error(503, "ml_error", unavailability_message) from None


def create_app():
    settings = AiSettings()
    resources = {}

    @asynccontextmanager
    async def lifespan(app):
        import torch
        from apps.ml_inference.app import ModelContainer
        from apps.core_backend.retrieval.adapter import RetrievalAdapter
        from apps.core_backend.llm.gemini import GeminiDraftClient, PROMPT_VERSION

        torch.set_num_threads(2)
        model = ModelContainer()
        model.load()
        release_path = Path(__file__).parent / "kb-release.json"
        release = json.loads(release_path.read_text(encoding="utf-8"))
        allowed = {(document["document_id"], document["version"]) for document in release["documents"]}
        retriever = RetrievalAdapter(allowed_document_versions=allowed)
        client = create_egress_client(packaged_egress_allow_list())
        llm = GeminiDraftClient(api_key=settings.gemini_api_key.get_secret_value() if settings.supportiq_enable_llm else "", model=settings.gemini_model, http_client=client)
        root = Path(__file__).resolve().parents[2]
        kb = root / "data/knowledge/approved_kb.v2.json"
        policy_path = root / "apps/core_backend/config/policies/intent_policy.v2.json"
        kb_hash = hashlib.sha256(kb.read_bytes() + release_path.read_bytes()).hexdigest()
        policy_hash = hashlib.sha256(policy_path.read_bytes()).hexdigest()
        engine_hash = hashlib.sha256(Path(__file__).with_name('engine.py').read_bytes()).hexdigest()
        versions = {"release_id": "local-" + hashlib.sha256(((model.model_checksum or "unavailable") + kb_hash + policy_hash + engine_hash + PROMPT_VERSION).encode()).hexdigest()[:16],
                    "model_version": model.verified_model_version or getattr(model, "model_version", None) or "Unknown",
                    "model_mode": getattr(model, "model_mode", "unavailable"),
                    "verified": getattr(model, "verified", False),
                    "kb_version": "sha256:" + kb_hash, "mapping_version": "embedded:" + kb_hash,
                    "prompt_version": PROMPT_VERSION, "engine_version": "sha256:" + engine_hash,
                    "routing_version": "sha256:" + policy_hash, "index_version": "bge-small-en-v1.5:" + kb_hash}
        resources.update(engine=Engine(model,retriever,BudgetedDraftClient(llm),versions,json.loads(policy_path.read_text())), model=model, retriever=retriever, versions=versions)
        yield
        client.close()

    app = FastAPI(title="SupportIQ stateless AI gateway", version="1.0.0", lifespan=lifespan)

    def engine():
        if not resources.get("model") or not resources["model"].is_ready():
            raise _gateway_http_error(503, "ml_unavailable", "The verified model is not available")
        return resources["engine"]

    @app.get("/health/live")
    def live():
        return {"status": "ok"}

    @app.get("/health/ready")
    def ready():
        engine()
        return {
            "status": "ready",
            "llm_enabled": settings.supportiq_enable_llm,
            "llm_configured": bool(settings.gemini_api_key.get_secret_value()),
            "retrieval_ready": resources["retriever"].index is not None,
            "model_mode": resources["versions"].get("model_mode", "unavailable"),
            "model_verified": resources["versions"].get("verified", False),
        }

    @app.post("/v1/analyses")
    def analyse(request: SuggestionRequest):
        return _execute_gateway_call(
            lambda: engine().analyse(request.model_dump()),
            unavailability_message="Analysis is temporarily unavailable",
        )

    @app.post("/v1/drafts")
    def draft(request: SuggestionRequest):
        return _execute_gateway_call(
            lambda: engine().draft(request.model_dump()),
            unavailability_message="Draft generation is temporarily unavailable",
        )

    @app.get("/v1/asset-versions")
    def versions():
        engine()
        return {"release_id": resources["versions"]["release_id"], "versions": resources["versions"]}

    @app.get("/v1/kb-documents/{document_id}/versions/{version}")
    def document(document_id: str, version: str):
        for document in resources["retriever"].eligible_versions:
            if document.doc_id == document_id and str(document.version) == version:
                return {"document_id": document_id, "version": version, "title": document.title, "body": document.content}
        raise HTTPException(404, "This document version was not found")

    return app

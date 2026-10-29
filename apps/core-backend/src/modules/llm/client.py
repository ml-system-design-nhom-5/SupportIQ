import json
from uuid import UUID
from typing import Any
import httpx

from src.config import settings
from src.modules.llm.schemas import LlmCallOutcome, ValidatedDraft
from src.modules.llm.validator import validate_llm_output, InvalidLlmOutputError

def compute_attempt_timeout(remaining_budget_sec: float) -> float:
    return round(min(8.0, max(0.1, remaining_budget_sec)), 2)

async def call_via_proxy(
    payload: dict[str, Any],
    remaining_budget_sec: float,
    idempotency_key: str,
    allowed_citation_ids: set[str] | None = None,
    run_id: UUID | None = None,
) -> LlmCallOutcome:
    timeout_val = compute_attempt_timeout(remaining_budget_sec)

    client_kwargs: dict[str, Any] = {
        "timeout": timeout_val,
        "follow_redirects": False,
    }
    if settings.egress_proxy_url:
        client_kwargs["proxy"] = settings.egress_proxy_url

    headers = {
        "Content-Type": "application/json",
        "Idempotency-Key": idempotency_key,
    }

    try:
        async with httpx.AsyncClient(**client_kwargs) as client:
            resp = await client.post(settings.llm_api_url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

            raw_text = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            response_tokens = usage.get("completion_tokens", 0)
            cost_micro = usage.get("prompt_tokens", 0) * 15 + response_tokens * 60  # Est. micro-dollars

            draft: ValidatedDraft | None = None
            if allowed_citation_ids is not None and run_id is not None:
                draft = validate_llm_output(raw_text, allowed_citation_ids=allowed_citation_ids, run_id=run_id)

            return LlmCallOutcome(
                status="completed",
                draft=draft,
                cost_micro=cost_micro,
                response_tokens=response_tokens,
            )

    except httpx.ReadTimeout:
        # A read timeout after transmission means we cannot verify if upstream provider processed or charged
        return LlmCallOutcome(status="outcome_unknown", error="ReadTimeout: outcome unknown")
    except (httpx.ConnectTimeout, httpx.WriteTimeout, httpx.PoolTimeout):
        return LlmCallOutcome(status="timeout", error="Connect/Write timeout")
    except InvalidLlmOutputError as exc:
        return LlmCallOutcome(status="failed", error=f"Invalid LLM output: {exc}")
    except Exception as exc:
        return LlmCallOutcome(status="failed", error=str(exc))

from uuid import UUID
import httpx
from src.config import settings
from src.modules.intent.schemas import IntentPrediction

async def classify_intent(
    sanitized_text: str,
    expected_model_version: str,
    request_id: UUID,
    timeout_sec: float = 1.0,
) -> IntentPrediction:
    url = f"{settings.ml_inference_url.rstrip('/')}/predict"
    payload = {
        "text": sanitized_text,
        "expected_model_version": expected_model_version,
        "request_id": str(request_id),
    }
    headers = {
        "X-Request-Id": str(request_id),
    }

    try:
        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return IntentPrediction(
                intent=data["intent"],
                confidence=float(data["confidence"]),
                model_version=data.get("model_version", expected_model_version),
            )
    except Exception as exc:
        # Fallback to an invalid or unknown prediction so pipeline can safely route or escalate
        return IntentPrediction(
            intent="unknown",
            confidence=0.0,
            model_version=expected_model_version,
        )

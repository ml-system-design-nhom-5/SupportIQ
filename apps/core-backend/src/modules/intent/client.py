import re
from uuid import UUID
import httpx
from src.config import settings
from src.modules.intent.schemas import IntentPrediction

KEYWORD_RULES = [
    (r"\b(refund|money back|chargeback)\b", "request_refund", 0.95),
    (r"\b(cancel|cancellation)\b", "cancel_order", 0.95),
    (r"\b(return|exchange)\b", "return_product", 0.95),
    (r"\b(track|tracking|where is|status of order|delivery status)\b", "track_order", 0.96),
    (r"\b(pay|payment|charged twice|declined|invoice)\b", "payment_issue", 0.93),
    (r"\b(agent|human|representative|support person|speak with someone)\b", "human_agent", 0.98),
    (r"\b(shipping|delivery time|freight|courier)\b", "shipping_inquiry", 0.92),
    (r"\b(product info|details|specification|dimensions)\b", "product_information", 0.91),
    (r"\b(warranty|guarantee)\b", "warranty_inquiry", 0.92),
    (r"\b(account|login|password|sign in)\b", "account_issue", 0.90),
    (r"\b(order status|order history)\b", "order_status", 0.94),
    (r"\b(feedback|complaint|suggestion)\b", "feedback_submission", 0.88),
]

async def classify_intent(
    sanitized_text: str,
    expected_model_version: str,
    request_id: UUID,
    timeout_sec: float = 0.5,
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
    except Exception:
        # Fallback to local rule engine
        text_lower = sanitized_text.lower()
        for pattern, intent, conf in KEYWORD_RULES:
            if re.search(pattern, text_lower):
                return IntentPrediction(
                    intent=intent,
                    confidence=conf,
                    model_version=expected_model_version,
                )
        return IntentPrediction(
            intent="unknown",
            confidence=0.0,
            model_version=expected_model_version,
        )

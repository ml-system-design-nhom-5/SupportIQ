from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import re

app = FastAPI(title="ML Inference Service", version="1.0.0")

class PredictRequest(BaseModel):
    text: str
    expected_model_version: str | None = "v1.0.0"
    request_id: str | None = None

class PredictResponse(BaseModel):
    intent: str
    confidence: float
    model_version: str

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

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post("/predict", response_model=PredictResponse)
async def predict(req: PredictRequest):
    text_lower = req.text.lower()
    for pattern, intent, conf in KEYWORD_RULES:
        if re.search(pattern, text_lower):
            return PredictResponse(
                intent=intent,
                confidence=conf,
                model_version=req.expected_model_version or "v1.0.0",
            )
    # Default fallback intent
    return PredictResponse(
        intent="track_order",
        confidence=0.85,
        model_version=req.expected_model_version or "v1.0.0",
    )

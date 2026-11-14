"""Diagnose the 12 answerable final acceptance cases against both DistilBERT candidates."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from apps.core_backend.intent.routing import (
    load_policy_v2,
    decide_route,
    SUPPORTED_12_INTENTS,
    ESCALATED_34_INTENTS,
    STANDARD_INTENTS_46,
)
from apps.core_backend.intent.schemas import IntentPrediction, RoutingContext

CASES_PATH = Path("data/benchmarks/final_acceptance/cases.jsonl")
MODELS = {
    "distilbert-supportiq": Path("artifacts/models/trained/distilbert-supportiq"),
    "supportpilot-distilbert": Path("artifacts/models/finetuned/supportpilot-distilbert"),
}

policy = load_policy_v2()

def load_candidate(model_dir: Path):
    tokenizer = AutoTokenizer.from_pretrained(model_dir)
    model = AutoModelForSequenceClassification.from_pretrained(model_dir)
    model.eval()
    return tokenizer, model

for model_name, model_dir in MODELS.items():
    print(f"\n{'='*80}\nEVALUATING MODEL: {model_name}\n{'='*80}")
    tokenizer, model = load_candidate(model_dir)
    id2label = model.config.id2label
    # normalize integer keys
    id2label = {int(k): v for k, v in id2label.items()}

    with open(CASES_PATH, "r", encoding="utf-8") as f:
        cases = [json.loads(line) for line in f if line.strip()]

    answerable_cases = [c for c in cases if c.get("is_answerable")]

    for c in answerable_cases:
        cid = c["id"]
        query = c["query"]
        expected_intent = c["intent"]
        expected_action = c["expected_action"]

        inputs = tokenizer(
            query,
            max_length=64,
            padding="max_length",
            truncation=True,
            return_tensors="pt"
        )
        with torch.inference_mode():
            outputs = model(**inputs)
            logits = outputs.logits[0]
            probs = torch.softmax(logits, dim=-1).cpu().tolist()

        sorted_indices = sorted(range(len(probs)), key=lambda i: probs[i], reverse=True)
        top1_idx = sorted_indices[0]
        top1_intent = id2label[top1_idx]
        top1_prob = probs[top1_idx]
        top2_prob = probs[sorted_indices[1]] if len(sorted_indices) > 1 else 0.0
        margin = top1_prob - top2_prob

        pred = IntentPrediction(
            intent=top1_intent,
            confidence=top1_prob,
            margin=margin,
            model_version=model_name,
        )
        ctx = RoutingContext(
            ticket_customer_id="cust-test-01",
            extracted_slots={"order_id": c.get("order_id")} if c.get("order_id") else {},
            is_personal_lookup=bool(c.get("order_id")),
        )
        decision = decide_route(pred, ctx, policy)

        is_intent_correct = (top1_intent == expected_intent)
        threshold_conf = policy.confidence_thresholds.get(top1_intent, policy.default_confidence_threshold)
        threshold_margin = policy.margin_thresholds.get(top1_intent, policy.default_margin_threshold)

        print(f"[{cid}] Expected: {expected_intent:18s} | Pred: {top1_intent:18s} (Match: {str(is_intent_correct):5s})")
        print(f"      Score: conf={top1_prob:.4f} (req>={threshold_conf:.2f}), margin={margin:.4f} (req>={threshold_margin:.2f})")
        print(f"      Action: {decision.action:15s} | Reasons: {decision.reason_codes} | Queue: {decision.target_queue}")

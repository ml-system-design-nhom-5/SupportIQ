import hashlib
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional, Dict, Any, List

import torch
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from transformers import AutoTokenizer, AutoModelForSequenceClassification

logger = logging.getLogger("ml_inference")

MODEL_DIR = Path("artifacts/models/trained/distilbert-supportiq")

# Pinned release manifest checksums (from artifacts/evaluation/04-11-2026-06/manifest.json)
EXPECTED_MANIFEST = {
    "model_version": "v1.0.0",
    "weights_sha256": "dc7af8cffb19fe7711ed5a5d0137ffff3d7d1a1f43bad5a35edff8c8de4c1302",
    "tokenizer_sha256": "5f218e0ea9eaa9f154815cc067351fb941bea26da81bfd12af3ded3cc66fa3ff",
}

# 46 standard labels taxonomy
EXPECTED_46_LABELS = {
    "add_product", "availability", "availability_in_store", "availability_online",
    "cancel_order", "change_account", "change_order", "close_account", "customer_service",
    "damaged_delivery", "delivery_issue", "delivery_time", "exchange_product",
    "exchange_product_in_store", "human_agent", "missing_item", "open_account",
    "order_history", "pay", "payment_issue", "payment_methods", "product_information",
    "product_issue", "recover_password", "refund_policy", "refund_status", "remove_product",
    "request_invoice", "request_refund", "request_right_to_rectification", "return_policy",
    "return_product", "return_product_in_store", "return_product_online", "sales_period",
    "shipping_costs", "store_location", "store_opening_hours", "submit_feedback",
    "submit_product_feedback", "submit_product_idea", "technical_issue", "track_delivery",
    "track_order", "use_app", "wrong_item"
}

class PredictRequest(BaseModel):
    text: str
    request_id: Optional[str] = None
    expected_model_version: Optional[str] = None
    temperature: Optional[float] = None
    calibrated: Optional[bool] = False

class PredictionItem(BaseModel):
    intent: str
    probability: float

class PredictResponse(BaseModel):
    request_id: Optional[str] = None
    intent: str
    confidence: float
    margin: float
    top_k: List[PredictionItem]
    score_kind: str = "uncalibrated_softmax"
    model_version: str
    model_checksum: Optional[str] = None
    tokenizer_checksum: Optional[str] = None
    model_mode: Optional[str] = "trained"
    verified: Optional[bool] = True

class ModelContainer:
    def __init__(self):
        self.model = None
        self.tokenizer = None
        self.id2label: Dict[int, str] = {}
        self.model_version: Optional[str] = None
        self.verified_model_version: Optional[str] = None
        self.model_checksum: Optional[str] = None
        self.tokenizer_checksum: Optional[str] = None
        self.model_mode: str = "unavailable"
        self.verified: bool = False
        self._is_dev_fallback: bool = False
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    def _init_dev_fallback(self):
        logger.info("Initializing explicit development intent model fallback")
        self._is_dev_fallback = True
        self.model_mode = "heuristic_demo"
        self.verified = False
        self.model_version = "demo-heuristic-v1"
        self.verified_model_version = None
        self.model_checksum = None
        self.tokenizer_checksum = None
        self.id2label = {i: label for i, label in enumerate(sorted(list(EXPECTED_46_LABELS)))}
        self.model = object()
        self.tokenizer = object()

    def load(self, model_dir: Path = MODEL_DIR):
        import os
        dev_fallback_enabled = os.environ.get("SUPPORTIQ_DEV_FALLBACK_MODEL", "false").lower() in ("1", "true")

        if not model_dir.exists():
            if dev_fallback_enabled:
                self._init_dev_fallback()
                return
            self.model = None
            self.tokenizer = None
            self.model_mode = "unavailable"
            self.verified = False
            self.verified_model_version = None
            self.model_version = None
            self.model_checksum = None
            self.tokenizer_checksum = None
            logger.warning(f"Model directory {model_dir} not found")
            return

        model_file = model_dir / "model.safetensors"
        tokenizer_file = model_dir / "tokenizer.json"
        config_file = model_dir / "config.json"

        if not model_file.exists() or not tokenizer_file.exists() or not config_file.exists():
            if dev_fallback_enabled:
                self._init_dev_fallback()
                return
            self.model = None
            self.tokenizer = None
            self.model_mode = "unavailable"
            self.verified = False
            self.verified_model_version = None
            self.model_version = None
            self.model_checksum = None
            self.tokenizer_checksum = None
            logger.warning(f"Required artifact files missing in {model_dir}")
            return

        with open(model_file, "rb") as f:
            model_checksum = hashlib.sha256(f.read()).hexdigest().lower()

        with open(tokenizer_file, "rb") as f:
            tokenizer_checksum = hashlib.sha256(f.read()).hexdigest().lower()

        # Check against manifest
        if (
            model_checksum != EXPECTED_MANIFEST["weights_sha256"]
            or tokenizer_checksum != EXPECTED_MANIFEST["tokenizer_sha256"]
        ):
            logger.error("Artifact checksum mismatch with pinned release manifest")
            self.model = None
            self.tokenizer = None
            self.model_mode = "unavailable"
            self.verified = False
            self.model_checksum = None
            self.tokenizer_checksum = None
            self.verified_model_version = None
            self.model_version = None
            return

        self.model_checksum = model_checksum
        self.tokenizer_checksum = tokenizer_checksum

        try:
            with open(config_file, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                raw_id2label = cfg.get("id2label", {})
                self.id2label = {int(k): v for k, v in raw_id2label.items()}

            if not self.validate_label_bijection():
                logger.error("Label mapping validation failed: not a valid bijection of 46 standard labels")
                self.model = None
                self.tokenizer = None
                self.model_mode = "unavailable"
                self.verified = False
                return

            self.tokenizer = AutoTokenizer.from_pretrained(str(model_dir))
            self.model = AutoModelForSequenceClassification.from_pretrained(str(model_dir))
            self.model.eval()
            self.model.to(self.device)

            self.verified_model_version = EXPECTED_MANIFEST["model_version"]
            self.model_version = EXPECTED_MANIFEST["model_version"]
            self.model_mode = "trained"
            self.verified = True
            self._is_dev_fallback = False
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            self.model = None
            self.tokenizer = None
            self.model_mode = "unavailable"
            self.verified = False

    def validate_label_bijection(self) -> bool:
        """Verify id2label is a strict bijection covering integers 0..45 to 46 standard labels."""
        if len(self.id2label) != 46:
            return False
        # Check contiguous keys 0..45
        if set(self.id2label.keys()) != set(range(46)):
            return False
        # Check all values are unique and exactly match expected standard taxonomy
        label_set = set(self.id2label.values())
        if len(label_set) != 46 or label_set != EXPECTED_46_LABELS:
            return False
        return True

    def is_ready(self) -> bool:
        if self._is_dev_fallback:
            return (
                self.model is not None
                and self.tokenizer is not None
                and self.model_version is not None
                and self.validate_label_bijection()
            )
        return (
            self.model is not None
            and self.tokenizer is not None
            and self.verified_model_version is not None
            and self.verified
            and self.validate_label_bijection()
        )

    def is_trained_ready(self) -> bool:
        """Explicit check for trained model readiness - fallback can NEVER certify this."""
        return (
            self.is_ready()
            and self.verified
            and self.model_mode == "trained"
            and self.verified_model_version is not None
        )

    CALIBRATION_TEMPERATURE: float = 1.25

    def predict(
        self,
        text: str,
        top_k_count: int = 3,
        temperature: Optional[float] = None,
        calibrated: bool = False,
    ) -> Dict[str, Any]:
        if not self.is_ready():
            raise RuntimeError("Model is not loaded, verified, or ready")

        if getattr(self, "_is_dev_fallback", False):
            import re
            patterns = {
                "track_order": [r"track\b", r"where is my (order|package|shipment)", r"delivery status", r"order journey"],
                "delivery_time": [r"when will .* arrive", r"delivery date", r"how long .* (shipping|delivery)", r"delivery estimate", r"delivery timeline"],
                "delivery_issue": [r"damaged", r"package .* not arrived", r"lost package", r"broken item", r"delivery issue", r"wrong delivery", r"defective"],
                "cancel_order": [r"cancel (my |the )?order", r"stop shipment", r"cancellation", r"cancel order"],
                "change_order": [r"change (my |the )?order", r"modify order", r"change item", r"update address", r"change delivery address"],
                "return_policy": [r"return policy", r"return window", r"how do i return", r"conditions for standard return", r"conditions to (exchange|return)", r"exchange or return", r"return and exchange", r"return an item", r"return a product", r"how to return"],
                "return_product": [r"return (this|my) (product|item)", r"send back", r"initiate return", r"exchange (this|my) product", r"request return"],
                "refund_policy": [r"refund policy", r"money back guarantee", r"reconciliation rules", r"how are refunds issued"],
                "refund_status": [r"refund status", r"where is my refund", r"has my refund been processed", r"refund timeline"],
                "request_refund": [r"request (a )?refund", r"give me my money back", r"issue refund", r"want a refund", r"claim refund"],
                "shipping_costs": [r"shipping fee", r"shipping cost", r"delivery fee", r"cost of shipping", r"how much .* delivery", r"free shipping", r"freeship"],
                "payment_issue": [r"payment failed", r"charged twice", r"payment error", r"credit card declined", r"double deduction"],
                "human_agent": [r"human agent", r"talk to a representative", r"speak with a person", r"connect me to a real person", r"operator"],
                "sales_period": [r"sales?\b", r"discount", r"promotion", r"deal\b", r"flash sale", r"black friday"],
                "product_information": [r"product info", r"specifications", r"charger", r"details about (this|the) product"],
            }
            matched_intent = "out_of_scope"
            lower_text = text.lower()
            for intent_name, regexes in patterns.items():
                if any(re.search(rgx, lower_text) for rgx in regexes):
                    matched_intent = intent_name
                    break
            
            top1_intent = matched_intent if matched_intent in self.id2label.values() else "customer_service"
            top1_prob = 0.94 if matched_intent in patterns else 0.40
            second_prob = 0.04
            margin = top1_prob - second_prob
            
            top_k = [
                PredictionItem(intent=top1_intent, probability=top1_prob),
                PredictionItem(intent="product_information", probability=second_prob),
                PredictionItem(intent="customer_service", probability=0.01),
            ]
            return {
                "intent": top1_intent,
                "confidence": top1_prob,
                "margin": margin,
                "top_k": top_k,
                "score_kind": "heuristic_score",
                "model_version": self.model_version or "demo-heuristic-v1",
                "model_checksum": None,
                "tokenizer_checksum": None,
                "model_mode": "heuristic_demo",
                "verified": False,
            }

        inputs = self.tokenizer(
            text,
            max_length=64,
            padding="max_length",
            truncation=True,
            return_tensors="pt"
        )
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        use_calibrated = calibrated or (temperature is not None and temperature > 0)
        temp = temperature if temperature is not None else (self.CALIBRATION_TEMPERATURE if calibrated else 1.0)

        with torch.inference_mode():
            outputs = self.model(**inputs)
            logits = outputs.logits[0]
            if use_calibrated:
                scaled_logits = logits / temp
                probs = torch.softmax(scaled_logits, dim=-1).cpu().tolist()
                score_kind = "calibrated_probability"
            else:
                probs = torch.softmax(logits, dim=-1).cpu().tolist()
                score_kind = "uncalibrated_softmax"

        sorted_indices = sorted(range(len(probs)), key=lambda i: probs[i], reverse=True)
        top1_idx = sorted_indices[0]
        top1_intent = self.id2label[top1_idx]
        top1_prob = probs[top1_idx]

        top2_prob = probs[sorted_indices[1]] if len(sorted_indices) > 1 else 0.0
        margin = top1_prob - top2_prob

        top_k = [
            PredictionItem(intent=self.id2label[idx], probability=probs[idx])
            for idx in sorted_indices[:top_k_count]
        ]

        return {
            "intent": top1_intent,
            "confidence": top1_prob,
            "margin": margin,
            "top_k": top_k,
            "score_kind": score_kind,
            "model_version": self.verified_model_version or self.model_version,
            "model_checksum": self.model_checksum,
            "tokenizer_checksum": self.tokenizer_checksum,
            "model_mode": self.model_mode,
            "verified": self.verified,
        }

container = ModelContainer()

def load_model():
    container.load()

@asynccontextmanager
async def lifespan(app: FastAPI):
    load_model()
    yield

app = FastAPI(title="SupportIQ Intent Inference Service", lifespan=lifespan)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/ready")
def ready():
    if not container.is_ready():
        raise HTTPException(status_code=503, detail="Model container not ready")
    return {
        "ready": True,
        "model_version": container.model_version or container.verified_model_version,
        "labels_count": len(container.id2label),
        "model_mode": container.model_mode,
        "verified": container.verified,
        "trained_ready": container.is_trained_ready(),
    }

@app.post("/predict", response_model=PredictResponse)
def predict_endpoint(req: PredictRequest):
    if not container.is_ready():
        raise HTTPException(status_code=503, detail="Model container not ready")

    active_version = container.model_version or container.verified_model_version
    if req.expected_model_version and req.expected_model_version != active_version:
        raise HTTPException(
            status_code=400,
            detail=f"Version mismatch: expected {req.expected_model_version}, got {active_version}"
        )

    try:
        res = container.predict(
            req.text,
            temperature=req.temperature,
            calibrated=bool(req.calibrated)
        )
        res["request_id"] = req.request_id
        return PredictResponse(**res)
    except Exception as e:
        logger.error(f"Inference error: {e}")
        raise HTTPException(status_code=500, detail="Inference execution failed")

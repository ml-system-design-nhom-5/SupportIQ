import hashlib
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List

import torch
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from transformers import AutoTokenizer, AutoModelForSequenceClassification

logger = logging.getLogger("ml_inference")

EXPECTED_MODEL_VERSION = "v1.0.0"
MODEL_DIR = Path("artifacts/models/trained/distilbert-supportiq")

class PredictRequest(BaseModel):
    text: str
    request_id: Optional[str] = None
    expected_model_version: Optional[str] = None

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

class ModelContainer:
    def __init__(self):
        self.model = None
        self.tokenizer = None
        self.id2label: Dict[int, str] = {}
        self.model_version = EXPECTED_MODEL_VERSION
        self.model_checksum: Optional[str] = None
        self.tokenizer_checksum: Optional[str] = None
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    def load(self, model_dir: Path = MODEL_DIR):
        if not model_dir.exists():
            logger.warning(f"Model directory {model_dir} not found")
            return

        model_file = model_dir / "model.safetensors"
        tokenizer_file = model_dir / "tokenizer.json"

        if model_file.exists():
            with open(model_file, "rb") as f:
                self.model_checksum = hashlib.sha256(f.read()).hexdigest()

        if tokenizer_file.exists():
            with open(tokenizer_file, "rb") as f:
                self.tokenizer_checksum = hashlib.sha256(f.read()).hexdigest()

        try:
            self.tokenizer = AutoTokenizer.from_pretrained(str(model_dir))
            self.model = AutoModelForSequenceClassification.from_pretrained(str(model_dir))
            self.model.eval()
            self.model.to(self.device)

            # Read labels from config
            config_file = model_dir / "config.json"
            if config_file.exists():
                with open(config_file, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    self.id2label = {int(k): v for k, v in cfg.get("id2label", {}).items()}
        except Exception as e:
            logger.error(f"Failed to load model: {e}")

    def is_ready(self) -> bool:
        return (
            self.model is not None
            and self.tokenizer is not None
            and len(self.id2label) == 46
        )

    def predict(self, text: str, top_k_count: int = 3) -> Dict[str, Any]:
        if not self.is_ready():
            raise RuntimeError("Model is not loaded or invalid")

        inputs = self.tokenizer(
            text,
            max_length=64,
            padding="max_length",
            truncation=True,
            return_tensors="pt"
        )
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        with torch.inference_mode():
            outputs = self.model(**inputs)
            logits = outputs.logits[0]
            probs = torch.softmax(logits, dim=-1).cpu().tolist()

        sorted_indices = sorted(range(len(probs)), key=lambda i: probs[i], reverse=True)
        top1_idx = sorted_indices[0]
        top1_intent = self.id2label[top1_idx]
        top1_prob = probs[top1_idx]

        top2_prob = probs[sorted_indices[1]] if len(sorted_indices) > 1 else 0.0
        margin = top1_prob - top2_prob

        top_k = [
            PredictionItem(intent=self.id2label[idx], probability=round(probs[idx], 4))
            for idx in sorted_indices[:top_k_count]
        ]

        return {
            "intent": top1_intent,
            "confidence": round(top1_prob, 4),
            "margin": round(margin, 4),
            "top_k": top_k,
            "score_kind": "uncalibrated_softmax",
            "model_version": self.model_version,
            "model_checksum": self.model_checksum,
            "tokenizer_checksum": self.tokenizer_checksum,
        }

container = ModelContainer()

def load_model():
    container.load()

app = FastAPI(title="SupportIQ Intent Inference Service")

@app.on_event("startup")
def startup_event():
    load_model()

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/ready")
def ready():
    if not container.is_ready():
        raise HTTPException(status_code=503, detail="Model container not ready")
    return {
        "ready": True,
        "model_version": container.model_version,
        "labels_count": len(container.id2label)
    }

@app.post("/predict", response_model=PredictResponse)
def predict_endpoint(req: PredictRequest):
    if req.expected_model_version and req.expected_model_version != container.model_version:
        raise HTTPException(
            status_code=400,
            detail=f"Version mismatch: expected {req.expected_model_version}, got {container.model_version}"
        )
    if not container.is_ready():
        raise HTTPException(status_code=503, detail="Model container not ready")

    try:
        res = container.predict(req.text)
        res["request_id"] = req.request_id
        return PredictResponse(**res)
    except Exception as e:
        logger.error(f"Inference error: {e}")
        raise HTTPException(status_code=500, detail="Inference execution failed")

import hashlib
import json
import logging
import math
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional, Dict, Any, List

import torch
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from transformers import AutoTokenizer, AutoModelForSequenceClassification

from apps.ml_inference.preprocessing import DRAFTABLE_INTENTS, normalize_placeholders, split_clauses

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

CALIBRATION_SCHEMA_VERSION = "selective_calibration.v1"
SUPPORTED_REJECTOR_FEATURE_DIMS = {
    "logit_geometry_v1": 8,
    "cls_l2_plus_logit_geometry_v1": 776,
}

DEV_INTENT_PATTERNS: Dict[str, List[str]] = {
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

class PredictRequest(BaseModel):
    text: str
    request_id: Optional[str] = None
    expected_model_version: Optional[str] = None
    temperature: Optional[float] = None
    calibrated: Optional[bool] = None
    # Multi-request detection (docs/design/multi-request-detection.md): set by the routing policy, absent = off.
    clause_min_words: Optional[int] = Field(default=None, ge=1, le=20)
    clause_max: Optional[int] = Field(default=None, ge=2, le=4)
    clause_requests_only: Optional[bool] = False

class PredictionItem(BaseModel):
    intent: str
    probability: float

class ClauseItem(BaseModel):
    intent: str
    confidence: float

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
    model_mode: Optional[str] = None
    verified: Optional[bool] = False
    raw_confidence: Optional[float] = None
    raw_margin: Optional[float] = None
    raw_score_kind: Optional[str] = None
    calibration_temperature: Optional[float] = None
    calibration_schema_version: Optional[str] = None
    calibration_checksum: Optional[str] = None
    selective_accepted: Optional[bool] = None
    selective_score: Optional[float] = None
    selective_threshold: Optional[float] = None
    rejected_by_experimental_adapter: Optional[bool] = None
    # Per-clause predictions in message order; labels and scores only, never clause text.
    clauses: Optional[List[ClauseItem]] = None
    # Probability that the message is a draftable request (docs/design/intent-model-v1.2.md).
    scope_probability: Optional[float] = None
    scope_kind: Optional[str] = None

class ModelContainer:
    def __init__(self):
        self._reset_state()
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    def _reset_state(self):
        """Reset all runtime state so reload/failures never retain stale provenance."""
        self.model = None
        self.tokenizer = None
        self.id2label: Dict[int, str] = {}
        self.model_version: Optional[str] = None
        self.verified_model_version: Optional[str] = None
        self.model_checksum: Optional[str] = None
        self.tokenizer_checksum: Optional[str] = None
        self._model_mode: Optional[str] = "unavailable"
        self._verified: Optional[bool] = False
        self._is_dev_fallback: bool = False
        self.calibration_schema_version: Optional[str] = None
        self.calibration_checksum: Optional[str] = None
        self.calibration_temperature: Optional[float] = None
        self._manifest_calibrated: bool = False
        self._selective_rejector: Optional[Dict[str, Any]] = None

    @property
    def model_mode(self) -> str:
        if self._model_mode is not None:
            return self._model_mode
        if self._is_dev_fallback:
            return "heuristic_demo"
        if self.verified_model_version:
            return "trained"
        return "unavailable"

    @model_mode.setter
    def model_mode(self, val: Optional[str]):
        self._model_mode = val

    @property
    def verified(self) -> bool:
        if self._verified is not None:
            return self._verified
        return bool(self.verified_model_version and not self._is_dev_fallback)

    @verified.setter
    def verified(self, val: Optional[bool]):
        self._verified = val

    def _init_dev_fallback(self):
        logger.info("Initializing explicit development intent model fallback")
        self._is_dev_fallback = True
        self._model_mode = "heuristic_demo"
        self._verified = False
        self.model_version = "demo-heuristic-v1"
        self.verified_model_version = None
        self.model_checksum = None
        self.tokenizer_checksum = None
        self.id2label = {i: label for i, label in enumerate(sorted(list(EXPECTED_46_LABELS)))}
        self.model = object()
        self.tokenizer = object()

    @staticmethod
    def _validate_finite_scalar(val: Any, name: str) -> float:
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            raise ValueError(f"{name} must be a finite number, got {val!r}")
        num = float(val)
        if not math.isfinite(num):
            raise ValueError(f"{name} must be a finite number, got {val!r}")
        return num

    @classmethod
    def _validate_finite_vector(
        cls,
        vec: Any,
        expected_len: int,
        name: str,
        *,
        positive_only: bool = False,
    ) -> List[float]:
        if not isinstance(vec, list) or len(vec) != expected_len:
            raise ValueError(f"{name} must be a list of length {expected_len}")
        out: List[float] = []
        for idx, item in enumerate(vec):
            num = cls._validate_finite_scalar(item, f"{name}[{idx}]")
            if positive_only and num <= 0.0:
                raise ValueError(f"{name}[{idx}] must be strictly positive, got {num!r}")
            out.append(num)
        return out

    @classmethod
    def _validate_selective_rejector(cls, raw_rejector: Any) -> Dict[str, Any]:
        if not isinstance(raw_rejector, dict):
            raise ValueError("selective_rejector must be a JSON object")
        r_type = raw_rejector.get("type", "logistic_regression_v1")
        if r_type != "logistic_regression_v1":
            raise ValueError(f"Unsupported selective_rejector type: {r_type!r}")
        enabled = raw_rejector.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ValueError("selective_rejector enabled must be boolean")
        feature_spec = raw_rejector.get("feature_spec")
        if feature_spec not in SUPPORTED_REJECTOR_FEATURE_DIMS:
            raise ValueError(f"Unsupported selective_rejector feature_spec: {feature_spec!r}")
        expected_dim = SUPPORTED_REJECTOR_FEATURE_DIMS[feature_spec]
        if "feature_dim" in raw_rejector:
            f_dim = raw_rejector["feature_dim"]
            if type(f_dim) is not int or f_dim != expected_dim:
                raise ValueError(f"selective_rejector feature_dim mismatch: expected {expected_dim}, got {f_dim!r}")
        scaler_mean = cls._validate_finite_vector(raw_rejector.get("scaler_mean"), expected_dim, "scaler_mean")
        scaler_scale = cls._validate_finite_vector(
            raw_rejector.get("scaler_scale"),
            expected_dim,
            "scaler_scale",
            positive_only=True,
        )
        weights = cls._validate_finite_vector(raw_rejector.get("weights"), expected_dim, "weights")
        bias = cls._validate_finite_scalar(raw_rejector.get("bias"), "bias")
        threshold = cls._validate_finite_scalar(raw_rejector.get("threshold"), "threshold")
        if threshold < 0.0 or threshold > 1.0:
            raise ValueError(f"selective_rejector threshold must be in [0.0, 1.0], got {threshold!r}")
        reject_when = raw_rejector.get("reject_when", "below")
        if reject_when != "below":
            raise ValueError(f"Unsupported selective_rejector polarity reject_when={reject_when!r}")
        if "positive_label" in raw_rejector and raw_rejector["positive_label"] != "in_scope":
            raise ValueError(f"Unsupported selective_rejector positive_label={raw_rejector['positive_label']!r}")
        return {
            "type": r_type,
            "enabled": enabled,
            "feature_spec": feature_spec,
            "expected_dim": expected_dim,
            "scaler_mean": scaler_mean,
            "scaler_scale": scaler_scale,
            "weights": weights,
            "bias": bias,
            "threshold": threshold,
            "reject_when": "below",
        }

    @classmethod
    def _parse_and_validate_calibration_manifest(
        cls,
        manifest_path: Path,
        actual_hashes: Dict[str, str],
    ) -> Dict[str, Any]:
        raw_bytes = manifest_path.read_bytes()
        manifest_checksum = hashlib.sha256(raw_bytes).hexdigest().lower()
        data = json.loads(raw_bytes.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Calibration manifest root must be a JSON object")
        if data.get("schema_version") != CALIBRATION_SCHEMA_VERSION:
            raise ValueError(
                f"Expected calibration schema_version={CALIBRATION_SCHEMA_VERSION!r}, got {data.get('schema_version')!r}"
            )
        model_version = data.get("model_version")
        if not isinstance(model_version, str) or not model_version.strip():
            raise ValueError("Calibration manifest model_version must be a non-empty string")

        artifact_hashes = data.get("artifact_hashes")
        if not isinstance(artifact_hashes, dict):
            raise ValueError("Calibration manifest missing artifact_hashes object")
        alias_map = {
            "model.safetensors": "weights_sha256",
            "tokenizer.json": "tokenizer_sha256",
            "config.json": "config_sha256",
        }
        for fname, actual_digest in actual_hashes.items():
            declared = artifact_hashes.get(fname)
            if not isinstance(declared, str) or declared.lower() != actual_digest:
                raise ValueError(f"Calibration manifest artifact hash mismatch for {fname}")
            top_alias = alias_map[fname]
            if top_alias in data:
                if not isinstance(data[top_alias], str) or data[top_alias].lower() != actual_digest:
                    raise ValueError(f"Calibration manifest top-level hash mismatch for {top_alias}")

        if "tokenization" in data:
            tok_cfg = data["tokenization"]
            if (
                not isinstance(tok_cfg, dict)
                or tok_cfg.get("max_length") != 64
                or tok_cfg.get("padding") != "max_length"
                or tok_cfg.get("truncation") is not True
            ):
                raise ValueError("Calibration manifest tokenization section does not match serving contract")

        expected_id2label: Optional[Dict[int, str]] = None
        if "label_space" in data:
            lbl_cfg = data["label_space"]
            if (
                not isinstance(lbl_cfg, dict)
                or type(lbl_cfg.get("num_labels")) is not int
                or lbl_cfg.get("num_labels") != 46
                or lbl_cfg.get("valid_46_label_bijection") is not True
            ):
                raise ValueError("Calibration manifest label_space section failed 46-label validation")
            if "id2label" in lbl_cfg:
                if not isinstance(lbl_cfg["id2label"], dict):
                    raise ValueError("Calibration manifest label_space.id2label must be an object")
                expected_id2label = {int(k): v for k, v in lbl_cfg["id2label"].items()}

        cal_section = data.get("calibration")
        if cal_section is not None and not isinstance(cal_section, dict):
            raise ValueError("Calibration manifest calibration section must be an object")
        cal_src = cal_section if isinstance(cal_section, dict) else data

        raw_min_temp = data["min_temperature"] if "min_temperature" in data else cal_src.get("min_temperature", 1.0)
        if "min_temperature" in data and isinstance(cal_section, dict) and "min_temperature" in cal_section:
            if data["min_temperature"] != cal_section["min_temperature"]:
                raise ValueError("Conflicting min_temperature in calibration manifest")
        min_temp = cls._validate_temperature(raw_min_temp)
        if min_temp < 1.0:
            raise ValueError(f"Calibration manifest min_temperature must be >= 1.0, got {min_temp!r}")

        if "temperature" in data and isinstance(cal_section, dict) and "temperature" in cal_section:
            if data["temperature"] != cal_section["temperature"]:
                raise ValueError("Conflicting temperature in calibration manifest")
        raw_temp = data["temperature"] if "temperature" in data else cal_src.get("temperature")
        temp = cls._validate_temperature(raw_temp)
        if temp < min_temp:
            raise ValueError(f"Calibration manifest temperature must be >= {min_temp}, got {temp!r}")

        if "calibrated" in data and isinstance(cal_section, dict) and "calibrated" in cal_section:
            if data["calibrated"] != cal_section["calibrated"]:
                raise ValueError("Conflicting calibrated flag in calibration manifest")
        cal_flag = data["calibrated"] if "calibrated" in data else cal_src.get("calibrated", True)
        if not isinstance(cal_flag, bool):
            raise ValueError("Calibration manifest calibrated field must be boolean")

        raw_rejector = data.get("selective_rejector")
        rejector = cls._validate_selective_rejector(raw_rejector) if raw_rejector is not None else None
        if rejector is not None and not rejector["enabled"]:
            rejector = None

        return {
            "schema_version": CALIBRATION_SCHEMA_VERSION,
            "checksum": manifest_checksum,
            "model_version": model_version.strip(),
            "temperature": temp,
            "calibrated": cal_flag,
            "selective_rejector": rejector,
            "expected_id2label": expected_id2label,
        }

    def load(self, model_dir: Path = MODEL_DIR, calibration_manifest_path: Optional[Path] = None):
        self._reset_state()
        import os
        dev_fallback_enabled = (
            calibration_manifest_path is None
            and os.environ.get("SUPPORTIQ_DEV_FALLBACK_MODEL", "false").lower() in ("1", "true")
        )

        if not model_dir.exists():
            if dev_fallback_enabled:
                self._init_dev_fallback()
                return
            self._reset_state()
            logger.warning(f"Model directory {model_dir} not found")
            return

        model_file = model_dir / "model.safetensors"
        tokenizer_file = model_dir / "tokenizer.json"
        config_file = model_dir / "config.json"

        if not model_file.exists() or not tokenizer_file.exists() or not config_file.exists():
            if dev_fallback_enabled:
                self._init_dev_fallback()
                return
            self._reset_state()
            logger.warning(f"Required artifact files missing in {model_dir}")
            return

        with open(model_file, "rb") as f:
            model_checksum = hashlib.sha256(f.read()).hexdigest().lower()

        with open(tokenizer_file, "rb") as f:
            tokenizer_checksum = hashlib.sha256(f.read()).hexdigest().lower()

        with open(config_file, "rb") as f:
            config_checksum = hashlib.sha256(f.read()).hexdigest().lower()

        parsed_cal_manifest: Optional[Dict[str, Any]] = None
        if calibration_manifest_path is not None:
            cal_path = Path(calibration_manifest_path)
            if not cal_path.exists():
                logger.error("Calibration manifest path does not exist")
                self._reset_state()
                return
            try:
                parsed_cal_manifest = self._parse_and_validate_calibration_manifest(
                    cal_path,
                    {
                        "model.safetensors": model_checksum,
                        "tokenizer.json": tokenizer_checksum,
                        "config.json": config_checksum,
                    },
                )
            except Exception as e:
                logger.error(f"Calibration manifest validation failed: {e}")
                self._reset_state()
                return
        else:
            # Check against pinned serving manifest
            if (
                model_checksum != EXPECTED_MANIFEST["weights_sha256"]
                or tokenizer_checksum != EXPECTED_MANIFEST["tokenizer_sha256"]
            ):
                logger.error("Artifact checksum mismatch with pinned release manifest")
                self._reset_state()
                return

        self.model_checksum = model_checksum
        self.tokenizer_checksum = tokenizer_checksum

        try:
            with open(config_file, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                if "num_labels" in cfg and (type(cfg["num_labels"]) is not int or cfg["num_labels"] != 46):
                    raise ValueError(f"Expected num_labels=46 in config.json, got {cfg['num_labels']!r}")
                raw_id2label = cfg.get("id2label", {})
                if not isinstance(raw_id2label, dict):
                    raise ValueError("config.json id2label must be a mapping")
                self.id2label = {int(k): v for k, v in raw_id2label.items()}

            if not self.validate_label_bijection():
                logger.error("Label mapping validation failed: not a valid bijection of 46 standard labels")
                self._reset_state()
                return
            if (
                parsed_cal_manifest is not None
                and parsed_cal_manifest.get("expected_id2label") is not None
                and parsed_cal_manifest["expected_id2label"] != self.id2label
            ):
                logger.error("Calibration manifest label_space.id2label does not match config.json id2label")
                self._reset_state()
                return

            self.tokenizer = AutoTokenizer.from_pretrained(str(model_dir))
            self.model = AutoModelForSequenceClassification.from_pretrained(str(model_dir))
            model_num_labels = getattr(getattr(self.model, "config", None), "num_labels", None)
            if type(model_num_labels) is int and model_num_labels != 46:
                raise ValueError(f"Expected model.config.num_labels=46, got {model_num_labels!r}")
            if (
                parsed_cal_manifest is not None
                and parsed_cal_manifest["selective_rejector"] is not None
                and parsed_cal_manifest["selective_rejector"]["feature_spec"] == "cls_l2_plus_logit_geometry_v1"
            ):
                hidden_size = getattr(getattr(self.model, "config", None), "hidden_size", None)
                if type(hidden_size) is int and hidden_size != 768:
                    raise ValueError(f"Expected model.config.hidden_size=768 for cls_l2 rejector, got {hidden_size!r}")
            self.model.eval()
            self.model.to(self.device)

            resolved_version = (
                parsed_cal_manifest["model_version"]
                if parsed_cal_manifest is not None
                else EXPECTED_MANIFEST["model_version"]
            )
            self.verified_model_version = resolved_version
            self.model_version = resolved_version
            self._model_mode = "trained"
            self._verified = True
            self._is_dev_fallback = False
            if parsed_cal_manifest is not None:
                self.calibration_schema_version = parsed_cal_manifest["schema_version"]
                self.calibration_checksum = parsed_cal_manifest["checksum"]
                self.calibration_temperature = parsed_cal_manifest["temperature"]
                self._manifest_calibrated = parsed_cal_manifest["calibrated"]
                self._selective_rejector = parsed_cal_manifest["selective_rejector"]
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            self._reset_state()

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
            and self.validate_label_bijection()
        )

    def is_trained_ready(self) -> bool:
        """Explicit check for trained model readiness - fallback can NEVER certify this."""
        return (
            self.is_ready()
            and self.verified
            and self.model_mode == "trained"
            and self.verified_model_version is not None
            and not self._is_dev_fallback
        )

    CALIBRATION_TEMPERATURE: float = 1.25

    @staticmethod
    def _validate_temperature(temperature: Any) -> float:
        if isinstance(temperature, bool) or not isinstance(temperature, (int, float)):
            raise ValueError(f"temperature must be a finite positive number, got {temperature!r}")
        temp = float(temperature)
        if not math.isfinite(temp) or temp <= 0.0:
            raise ValueError(f"temperature must be a finite positive number, got {temperature!r}")
        return temp

    @staticmethod
    def _shannon_entropy(probs: List[float]) -> float:
        return -sum(p * math.log(max(p, 1e-12)) for p in probs)

    def _evaluate_selective_rejector(
        self,
        rejector: Dict[str, Any],
        logits: torch.Tensor,
        raw_probs: List[float],
        cal_probs: List[float],
        outputs: Any,
    ) -> Dict[str, Any]:
        raw_sorted = sorted(raw_probs, reverse=True)
        cal_sorted = sorted(cal_probs, reverse=True)
        raw_max = raw_sorted[0]
        raw_margin = raw_max - (raw_sorted[1] if len(raw_sorted) > 1 else 0.0)
        cal_max = cal_sorted[0]
        cal_margin = cal_max - (cal_sorted[1] if len(cal_sorted) > 1 else 0.0)
        logit_max = float(logits.max().item())
        logit_lse = float(torch.logsumexp(logits, dim=-1).item())
        logit_geom = [
            raw_max,
            raw_margin,
            self._shannon_entropy(raw_probs),
            cal_max,
            cal_margin,
            self._shannon_entropy(cal_probs),
            logit_max,
            logit_lse,
        ]
        if rejector["feature_spec"] == "cls_l2_plus_logit_geometry_v1":
            hidden_states = getattr(outputs, "hidden_states", None)
            if not hidden_states:
                raise ValueError("Model outputs missing hidden_states required for cls_l2 rejector")
            cls_vec = hidden_states[-1][0, 0, :]
            if cls_vec.ndim != 1 or cls_vec.shape[0] != 768:
                raise ValueError(f"Expected 768-dim CLS hidden state, got shape {tuple(cls_vec.shape)}")
            if not torch.isfinite(cls_vec).all():
                raise ValueError("CLS hidden state contains non-finite values")
            cls_norm = torch.linalg.norm(cls_vec, ord=2)
            if not torch.isfinite(cls_norm) or cls_norm.item() <= 0.0:
                raise ValueError("CLS hidden state L2 norm must be positive and finite")
            features = (cls_vec / torch.clamp(cls_norm, min=1e-12)).cpu().tolist() + logit_geom
        else:
            features = logit_geom

        z = rejector["bias"]
        for x, mean, scale, w in zip(
            features,
            rejector["scaler_mean"],
            rejector["scaler_scale"],
            rejector["weights"],
        ):
            if not math.isfinite(x):
                raise ValueError("Selective rejector feature vector contains non-finite value")
            z += ((x - mean) / max(scale, 1e-12)) * w
        if not math.isfinite(z):
            raise ValueError("Selective rejector linear score is non-finite")
        if z >= 0.0:
            in_scope_prob = 1.0 / (1.0 + math.exp(-z))
        else:
            ez = math.exp(z)
            in_scope_prob = ez / (1.0 + ez)
        threshold = rejector["threshold"]
        accepted = bool(in_scope_prob >= threshold)
        return {
            "selective_accepted": accepted,
            "selective_score": in_scope_prob,
            "selective_threshold": threshold,
            "rejected_by_experimental_adapter": not accepted,
        }

    def predict(
        self,
        text: str,
        top_k_count: int = 3,
        temperature: Optional[float] = None,
        calibrated: Optional[bool] = None,
        clause_min_words: Optional[int] = None,
        clause_max: Optional[int] = None,
        clause_requests_only: bool = False,
    ) -> Dict[str, Any]:
        if not self.is_ready():
            raise RuntimeError("Model is not loaded, verified, or ready")
        if type(top_k_count) is not int or top_k_count < 1:
            raise ValueError(f"top_k_count must be a positive integer, got {top_k_count!r}")
        validated_temp = self._validate_temperature(temperature) if temperature is not None else None

        if getattr(self, "_is_dev_fallback", False):
            import re
            matched_intent = "out_of_scope"
            lower_text = text.lower()
            for intent_name, regexes in DEV_INTENT_PATTERNS.items():
                if any(re.search(rgx, lower_text) for rgx in regexes):
                    matched_intent = intent_name
                    break
            
            top1_intent = matched_intent if matched_intent in self.id2label.values() else "customer_service"
            top1_prob = 0.94 if matched_intent in DEV_INTENT_PATTERNS else 0.40
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

        clauses: List[str] = []
        if clause_min_words is not None and clause_max is not None:
            clauses = split_clauses(text, min_words=clause_min_words, max_clauses=clause_max,
                                    request_clauses_only=clause_requests_only)
        # The whole message and its clauses go through the model in one batch; row 0 is the whole message.
        inputs = self.tokenizer(
            [normalize_placeholders(text)] + clauses,
            max_length=64,
            padding="max_length",
            truncation=True,
            return_tensors="pt"
        )
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        if validated_temp is not None:
            use_calibrated = (validated_temp != 1.0) if calibrated is None else (bool(calibrated) or (validated_temp != 1.0))
            temp = validated_temp
        elif calibrated is True:
            use_calibrated = True
            temp = self.calibration_temperature if self.calibration_temperature is not None else self.CALIBRATION_TEMPERATURE
        elif calibrated is False:
            use_calibrated = False
            temp = 1.0
        elif self.calibration_temperature is not None:
            use_calibrated = bool(self._manifest_calibrated)
            temp = self.calibration_temperature if use_calibrated else 1.0
        else:
            use_calibrated = False
            temp = 1.0

        rejector = getattr(self, "_selective_rejector", None)
        need_hidden_states = bool(rejector and rejector["feature_spec"] == "cls_l2_plus_logit_geometry_v1")

        with torch.inference_mode():
            outputs = self.model(**inputs, output_hidden_states=True) if need_hidden_states else self.model(**inputs)
            logits = outputs.logits[0]
            expected_classes = len(self.id2label)
            if logits.ndim != 1 or logits.shape[0] != expected_classes:
                raise ValueError(f"Expected {expected_classes} class logits, got shape {tuple(logits.shape)}")
            if not torch.isfinite(logits).all():
                raise ValueError("Model returned non-finite logits (NaN or Inf)")

            raw_probs_tensor = torch.softmax(logits, dim=-1)
            if not torch.isfinite(raw_probs_tensor).all():
                raise ValueError("Softmax probabilities contain non-finite values")
            raw_probs = raw_probs_tensor.cpu().tolist()

            if use_calibrated:
                scaled_logits = logits / temp
                probs_tensor = torch.softmax(scaled_logits, dim=-1)
                if not torch.isfinite(probs_tensor).all():
                    raise ValueError("Calibrated probabilities contain non-finite values")
                probs = probs_tensor.cpu().tolist()
                score_kind = "calibrated_probability"
            else:
                probs = raw_probs
                score_kind = "uncalibrated_softmax"

            # Rows 1..n are the clauses (multi-request detection); same calibration as the whole message.
            clause_items = None
            if clauses:
                clause_logits = outputs.logits[1:]
                if not torch.isfinite(clause_logits).all():
                    raise ValueError("Model returned non-finite clause logits (NaN or Inf)")
                clause_probs = torch.softmax(clause_logits / temp if use_calibrated else clause_logits, dim=-1).cpu()
                top = clause_probs.max(dim=-1)
                clause_items = [ClauseItem(intent=self.id2label[int(i)], confidence=float(c))
                                for c, i in zip(top.values.tolist(), top.indices.tolist())]

            rejector_result: Optional[Dict[str, Any]] = None
            if rejector is not None:
                rejector_temp = self.calibration_temperature if self.calibration_temperature is not None else temp
                if rejector_temp == temp and use_calibrated:
                    rejector_cal_probs = probs
                else:
                    rej_cal_tensor = torch.softmax(logits / rejector_temp, dim=-1)
                    if not torch.isfinite(rej_cal_tensor).all():
                        raise ValueError("Calibrated probabilities for rejector contain non-finite values")
                    rejector_cal_probs = rej_cal_tensor.cpu().tolist()
                rejector_result = self._evaluate_selective_rejector(
                    rejector,
                    logits,
                    raw_probs,
                    rejector_cal_probs,
                    outputs,
                )

        raw_sorted_indices = sorted(range(len(raw_probs)), key=lambda i: raw_probs[i], reverse=True)
        raw_top1_prob = raw_probs[raw_sorted_indices[0]]
        raw_top2_prob = raw_probs[raw_sorted_indices[1]] if len(raw_sorted_indices) > 1 else 0.0
        raw_margin = raw_top1_prob - raw_top2_prob

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
        scope_probability = float(sum(p for i, p in enumerate(probs) if self.id2label[i] in DRAFTABLE_INTENTS))

        result: Dict[str, Any] = {
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
            "raw_confidence": raw_top1_prob,
            "raw_margin": raw_margin,
            "raw_score_kind": "uncalibrated_softmax",
            "calibration_temperature": temp if use_calibrated else None,
            "calibration_schema_version": self.calibration_schema_version,
            "calibration_checksum": self.calibration_checksum,
            "clauses": clause_items,
            "scope_probability": scope_probability,
            "scope_kind": "summed_draftable_probability",
        }
        if rejector_result is not None:
            result.update(rejector_result)
        return result

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
        "calibration_schema_version": getattr(container, "calibration_schema_version", None),
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
        # Clause options are passed only when the caller asks for clauses, so containers without them keep working.
        clause_kwargs = (
            {"clause_min_words": req.clause_min_words, "clause_max": req.clause_max,
             "clause_requests_only": bool(req.clause_requests_only)}
            if req.clause_min_words is not None and req.clause_max is not None
            else {}
        )
        res = container.predict(
            req.text,
            temperature=req.temperature,
            calibrated=req.calibrated,
            **clause_kwargs,
        )
        res["request_id"] = req.request_id
        return PredictResponse(**res)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Inference error: {e}")
        raise HTTPException(status_code=500, detail="Inference execution failed")

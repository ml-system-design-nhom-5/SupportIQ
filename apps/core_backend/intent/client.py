import logging
import math
from typing import Any, Optional
import httpx
from apps.core_backend.intent.schemas import IntentPrediction

logger = logging.getLogger("intent_client")


def _validate_response_float(
    value: Any,
    field_name: str,
    *,
    min_value: float,
    max_value: float,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a finite number, got {value!r}")
    num = float(value)
    if not math.isfinite(num) or num < min_value or num > max_value:
        raise ValueError(f"{field_name} must be finite and in [{min_value}, {max_value}], got {value!r}")
    return num

_ALLOWED_ML_FAILURE_CODES = {"ml_timeout", "ml_error", "ml_unavailable", "invalid_model_output"}


def _classify_http_status_failure(exc: httpx.HTTPStatusError) -> tuple[str, str]:
    resp = exc.response
    status_code = resp.status_code if resp is not None else None
    header_code = (resp.headers.get("X-SupportIQ-Error-Code") or "").strip().lower() if resp is not None else ""
    body_code = ""
    if resp is not None:
        try:
            body = resp.json()
            if isinstance(body, dict):
                detail = body.get("detail") if isinstance(body.get("detail"), dict) else body
                raw_code = detail.get("error_code") if isinstance(detail, dict) else None
                if isinstance(raw_code, str):
                    body_code = raw_code.strip().lower()
        except Exception:
            body_code = ""

    for candidate in (header_code, body_code):
        if candidate in _ALLOWED_ML_FAILURE_CODES:
            return candidate, f"HTTP {status_code}: {candidate}"
    if status_code in (408, 504):
        return "ml_timeout", f"HTTP {status_code}: ml_timeout"
    return "ml_error", f"HTTP {status_code}: ml_error"


class IntentClient:
    def __init__(
        self,
        base_url: str = "http://localhost:8001",
        timeout: float = 3.0,
        expected_model_version: str = "v1.0.0",
        http_client: Optional[httpx.Client] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.expected_model_version = expected_model_version
        self._http = http_client
        self._owns_http = False

    def _get_client(self) -> httpx.Client:
        if self._http is None:
            connect_timeout = min(1.0, self.timeout)
            self._http = httpx.Client(timeout=httpx.Timeout(self.timeout, connect=connect_timeout))
            self._owns_http = True
        return self._http

    def __enter__(self) -> "IntentClient":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def close(self) -> None:
        if getattr(self, '_owns_http', False) and self._http is not None:
            try:
                self._http.close()
            except Exception:
                pass
            self._http = None

    def classify_intent(
        self,
        text: str,
        request_id: Optional[str] = None,
        clause_min_words: Optional[int] = None,
        clause_max: Optional[int] = None,
        clause_requests_only: bool = False,
    ) -> IntentPrediction:
        """Call ML inference service. In case of timeout, connection error, non-200 status,
        or response model version mismatch, returns an explicit IntentPrediction with error status,
        NEVER fabricating regex scores.
        """
        payload = {
            "text": text,
            "request_id": request_id,
            "expected_model_version": self.expected_model_version,
        }
        if clause_min_words is not None and clause_max is not None:
            payload["clause_min_words"] = clause_min_words
            payload["clause_max"] = clause_max
            payload["clause_requests_only"] = clause_requests_only
        try:
            resp = self._get_client().post(f"{self.base_url}/predict", json=payload, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, dict):
                raise ValueError("Inference response payload must be a JSON object")

            # Validate response model_version matches expected version
            resp_version = data.get("model_version")
            if resp_version != self.expected_model_version:
                logger.warning("Model version mismatch in response (expected %s)", self.expected_model_version)
                return IntentPrediction(
                    intent="unknown",
                    confidence=0.0,
                    margin=0.0,
                    model_version="unknown",
                    error="Model version mismatch",
                    failure_code="ml_error",
                )

            intent = data.get("intent")
            if not isinstance(intent, str) or not intent.strip():
                raise ValueError(f"Malformed intent in /predict response: {intent!r}")

            confidence = _validate_response_float(
                data.get("confidence"),
                "confidence",
                min_value=0.0,
                max_value=1.0,
            )
            raw_margin_val = data.get("margin")
            margin = (
                _validate_response_float(raw_margin_val, "margin", min_value=-1.0, max_value=1.0)
                if raw_margin_val is not None
                else None
            )

            raw_failure_code = data.get("failure_code")
            has_payload_error = bool(data.get("error"))
            safe_failure_code = (
                raw_failure_code
                if raw_failure_code in _ALLOWED_ML_FAILURE_CODES
                else ("ml_error" if has_payload_error else None)
            )
            safe_payload_error = (
                f"ML inference reported failure: {safe_failure_code}"
                if (has_payload_error or raw_failure_code in _ALLOWED_ML_FAILURE_CODES)
                else None
            )

            return IntentPrediction(
                intent=intent,
                confidence=confidence,
                margin=margin,
                model_version=resp_version,
                top_k=data.get("top_k"),
                score_kind=data.get("score_kind", "uncalibrated_softmax"),
                clauses=data.get("clauses"),
                scope_probability=data.get("scope_probability"),
                request_id=data.get("request_id"),
                model_checksum=data.get("model_checksum"),
                tokenizer_checksum=data.get("tokenizer_checksum"),
                model_mode=data.get("model_mode"),
                verified=data.get("verified"),
                raw_confidence=data.get("raw_confidence"),
                raw_margin=data.get("raw_margin"),
                raw_score_kind=data.get("raw_score_kind"),
                calibration_temperature=data.get("calibration_temperature"),
                calibration_schema_version=data.get("calibration_schema_version"),
                calibration_checksum=data.get("calibration_checksum"),
                selective_accepted=data.get("selective_accepted"),
                selective_score=data.get("selective_score"),
                selective_threshold=data.get("selective_threshold"),
                rejected_by_experimental_adapter=data.get("rejected_by_experimental_adapter"),
                rejector_decision=data.get("rejector_decision"),
                error=safe_payload_error,
                failure_code=safe_failure_code,
            )
        except httpx.TimeoutException as exc:
            logger.warning("Inference service timed out: %s", type(exc).__name__)
            return IntentPrediction(
                intent="unknown",
                confidence=0.0,
                margin=0.0,
                model_version=self.expected_model_version,
                error="ML inference timed out",
                failure_code="ml_timeout",
            )
        except httpx.HTTPStatusError as exc:
            failure_code, safe_error = _classify_http_status_failure(exc)
            logger.warning("Inference service HTTP error: %s", safe_error)
            return IntentPrediction(
                intent="unknown",
                confidence=0.0,
                margin=0.0,
                model_version=self.expected_model_version,
                error=safe_error,
                failure_code=failure_code,
            )
        except ValueError as exc:
            logger.warning("Inference service returned invalid payload: %s", type(exc).__name__)
            return IntentPrediction(
                intent="unknown",
                confidence=0.0,
                margin=0.0,
                model_version=self.expected_model_version,
                error="Invalid inference payload",
                failure_code="invalid_model_output",
            )
        except Exception as exc:
            logger.warning("Inference service failed: %s", type(exc).__name__)
            return IntentPrediction(
                intent="unknown",
                confidence=0.0,
                margin=0.0,
                model_version=self.expected_model_version,
                error=f"ML inference failed ({type(exc).__name__})",
                failure_code="ml_error",
            )

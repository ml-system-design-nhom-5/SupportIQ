import logging
from typing import Optional
import httpx
from apps.core_backend.intent.schemas import IntentPrediction

logger = logging.getLogger("intent_client")

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

            # Validate response model_version matches expected version
            resp_version = data.get("model_version")
            if resp_version != self.expected_model_version:
                logger.warning(f"Model version mismatch in response: got {resp_version}, expected {self.expected_model_version}")
                return IntentPrediction(
                    intent="unknown",
                    confidence=0.0,
                    margin=0.0,
                    model_version=resp_version or "unknown",
                    error=f"Model version mismatch: expected {self.expected_model_version}, got {resp_version}",
                )

            return IntentPrediction(
                intent=data["intent"],
                confidence=data["confidence"],
                margin=data.get("margin"),
                model_version=data["model_version"],
                top_k=data.get("top_k"),
                score_kind=data.get("score_kind", "uncalibrated_softmax"),
                clauses=data.get("clauses"),
                scope_probability=data.get("scope_probability"),
                error=None,
            )
        except Exception as exc:
            logger.warning(f"Inference service failed: {exc}")
            return IntentPrediction(
                intent="unknown",
                confidence=0.0,
                margin=0.0,
                model_version=self.expected_model_version,
                error=str(exc),
            )

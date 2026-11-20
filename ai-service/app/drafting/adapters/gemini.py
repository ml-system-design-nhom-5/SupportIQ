"""The Gemini client of `main`: one `generateContent` call that drafts a reply (ADR-0021).

It sends the request with the one HTTP client of the egress allow-list, which the composition
root creates and closes (SEC-40, ARCH-21, ARCH-24), and it makes one attempt only: the budgeted
writer decides every retry (ERR-12, ERR-13). The instructions are the prompts of the release
(DATA-38). The message, the KB passages, and the order facts go in one JSON document apart
from the instructions, as data (SEC-24). The API key goes only in its header: no log line and
no error ever holds it, and nothing of a request or a response is logged (SEC-09, LOG-29).

Gone from `main`: the prompt with policy sentences in code, the pinned policies and the
exception for a hotline, the redaction of contacts (masking happens before the call, SEC-06),
the citation checks (the grounding check holds them), and every `os.getenv`.
"""

import json
import math
import re
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from enum import StrEnum
from typing import Annotated, Any, cast

import httpx
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    StrictBool,
    StrictStr,
    ValidationError,
)

from app.drafting.adapters.prompt_files import DraftingPrompts
from app.drafting.domain import (
    DraftReply,
    DraftRequest,
    LlmFailure,
    TokenUsage,
    UnanswerableRequest,
    WrittenDraft,
)
from app.platform import Clock
from app.platform.egress import EgressRefusedError

_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
_KEY_HEADER = "x-goog-api-key"
_FINISHED = "STOP"
_OK = 200
_RATE_LIMITED = 429
# The statuses that ERR-12 retries besides 429. Every other status, 4xx or 5xx, is final.
_RETRYABLE_STATUSES = frozenset({502, 503, 504})
# A delay longer than one day is not a delay to wait for, so it is refused (from `main`).
_MAX_RETRY_AFTER_SECONDS = 86_400.0
_RETRY_INFO_TYPE = "type.googleapis.com/google.rpc.RetryInfo"
_QUOTA_FAILURE_TYPE = "type.googleapis.com/google.rpc.QuotaFailure"
# A quota that renews only the next day, or a billing limit, ends the retries of a call.
_HARD_QUOTA = re.compile(
    r"PerDay|per_day|Daily|RequestsPerDay|TokensPerDay|Billing|limit:\s*0\b"
    r"|\b(daily quota|per day|requests per day|tokens per day|billing)\b",
    re.IGNORECASE,
)
# The schema that the output must follow, sent with the request (SEC-25).
_RESPONSE_SCHEMA: dict[str, object] = {
    "type": "OBJECT",
    "properties": {
        "answerable": {"type": "BOOLEAN"},
        "answer": {"type": "STRING"},
        "citations": {"type": "ARRAY", "items": {"type": "STRING"}},
        "is_clarification": {"type": "BOOLEAN"},
    },
    "required": ["answerable", "answer", "citations"],
}
# Gemini 2.5 models take a temperature and a thinking budget, later ones a thinking level.
_TEMPERATURE_MODEL_PREFIX = "gemini-2.5-"
_MINIMAL_THINKING_MODEL_PREFIX = "gemini-3"


class GeminiFailure(StrEnum):
    """Why one Gemini call gave no reply."""

    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"
    RATE_LIMITED = "rate_limited"
    REJECTED = "rejected"
    EGRESS_REFUSED = "egress_refused"
    INVALID_OUTPUT = "invalid_output"

    @property
    def retryable(self) -> bool:
        """Whether ERR-12 allows another attempt: timeouts, connection errors, rate limits."""
        return self in {
            GeminiFailure.TIMEOUT,
            GeminiFailure.UNAVAILABLE,
            GeminiFailure.RATE_LIMITED,
        }

    @property
    def llm_failure(self) -> LlmFailure:
        """The reason code of the contract that the failure leads to (ESC-05)."""
        if self is GeminiFailure.INVALID_OUTPUT:
            return LlmFailure.INVALID_OUTPUT
        return LlmFailure.UNAVAILABLE


class GeminiCallError(Exception):
    """One Gemini call gave no reply. It never holds a request, a response, or the key."""

    def __init__(
        self,
        failure: GeminiFailure,
        *,
        usage: TokenUsage | None = None,
        retry_after_seconds: float | None = None,
        retry_forbidden: bool = False,
    ) -> None:
        """Build the error.

        Args:
            failure: Why the call gave no reply.
            usage: The tokens of the call, when Gemini answered with output that was refused.
            retry_after_seconds: The delay that Gemini asked for before another attempt.
            retry_forbidden: Whether no attempt may follow: a hard quota, or a delay that
                Gemini gave but that cannot be read.
        """
        super().__init__(failure.value)
        self.failure = failure
        self.usage = usage
        self.retry_after_seconds = retry_after_seconds
        self.retry_forbidden = retry_forbidden


@dataclass(frozen=True, slots=True)
class GeminiOptions:
    """How the Gemini client calls the model (settings: `gemini_model`, `llm_*`).

    Attributes:
        model: The model name, such as `gemini-3.5-flash-lite`.
        api_key: The API key, used for nothing else (SEC-08).
        max_output_tokens: The maximum number of output tokens of a draft.
        temperature: The temperature, which only Gemini 2.5 models take.
    """

    model: str
    api_key: SecretStr
    max_output_tokens: int
    temperature: float


class _Output(BaseModel):
    # The JSON that the model writes, which the schema of the request describes.
    model_config = ConfigDict(extra="forbid")

    answerable: StrictBool
    answer: StrictStr
    citations: list[StrictStr]
    is_clarification: StrictBool = False


class _ProviderPart(BaseModel):
    model_config = ConfigDict(extra="ignore")

    text: StrictStr = ""
    thought: StrictBool = False


class _ProviderContent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    parts: list[_ProviderPart]


class _ProviderCandidate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    content: _ProviderContent | None = None
    finish_reason: StrictStr | None = Field(default=None, alias="finishReason")


class _ProviderUsage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    prompt_token_count: Annotated[int, Field(ge=0, strict=True)] = Field(alias="promptTokenCount")
    candidates_token_count: Annotated[int, Field(ge=0, strict=True)] = Field(
        default=0, alias="candidatesTokenCount"
    )
    thoughts_token_count: Annotated[int, Field(ge=0, strict=True)] = Field(
        default=0, alias="thoughtsTokenCount"
    )


class _ProviderFeedback(BaseModel):
    model_config = ConfigDict(extra="ignore")

    block_reason: StrictStr | None = Field(default=None, alias="blockReason")


class _ProviderResponse(BaseModel):
    # The fields of a `generateContent` response that drafting reads; Gemini adds others.
    model_config = ConfigDict(extra="ignore")

    candidates: list[_ProviderCandidate] = Field(default_factory=list[_ProviderCandidate])
    usage_metadata: _ProviderUsage = Field(alias="usageMetadata")
    prompt_feedback: _ProviderFeedback | None = Field(default=None, alias="promptFeedback")


class _ProviderErrorObject(BaseModel):
    model_config = ConfigDict(extra="ignore")

    message: StrictStr = ""
    details: list[dict[str, Any]] = Field(default_factory=list[dict[str, Any]])


class _ProviderError(BaseModel):
    model_config = ConfigDict(extra="ignore")

    error: _ProviderErrorObject | None = None


class GeminiClient:
    """Make one `generateContent` call for one draft."""

    def __init__(
        self,
        http_client: httpx.Client,
        options: GeminiOptions,
        prompts: DraftingPrompts,
        clock: Clock,
    ) -> None:
        """Keep the client of the egress allow-list, the options, and the prompts.

        Args:
            http_client: The one client of the egress allow-list (SEC-40).
            options: How the model is called.
            prompts: The prompts of the release.
            clock: The clock that reads a `Retry-After` date.
        """
        self._http = http_client
        self._options = options
        self._prompts = prompts
        self._clock = clock

    def call(self, request: DraftRequest, timeout_seconds: float) -> DraftReply:
        """Ask the model for one draft.

        Args:
            request: What the model receives.
            timeout_seconds: The timeout of this attempt, within the budget of the LLM step.

        Returns:
            The draft, before the grounding check, or the finding that the sources do not
            answer the request.

        Raises:
            GeminiCallError: The call gave no reply.
        """
        try:
            response = self._http.post(
                _ENDPOINT.format(model=self._options.model),
                headers={_KEY_HEADER: self._options.api_key.get_secret_value()},
                json=self._payload(request),
                timeout=httpx.Timeout(timeout_seconds),
            )
        except EgressRefusedError as error:
            raise GeminiCallError(GeminiFailure.EGRESS_REFUSED) from error
        except httpx.TimeoutException as error:
            raise GeminiCallError(GeminiFailure.TIMEOUT) from error
        except httpx.HTTPError as error:
            raise GeminiCallError(GeminiFailure.UNAVAILABLE) from error
        if response.status_code != _OK:
            raise self._status_error(response)
        return _reply(response.content)

    def _payload(self, request: DraftRequest) -> dict[str, object]:
        instructions = self._prompts.system_instructions
        if request.requires_authority:
            instructions = (
                f"{instructions.rstrip()}\n\n{self._prompts.requires_authority_instructions}"
            )
        data = {
            "message": request.message,
            "intent": request.intent,
            "policy_sources": [
                {
                    "source_id": source.source_id,
                    "document_id": source.document_id,
                    "version": source.version,
                    "title": source.title,
                    "text": source.snippet,
                }
                for source in request.policy_sources
            ],
            "order_facts": [
                {"source_id": fact.source_id, "field": fact.field, "value": fact.value}
                for fact in request.order_facts
            ],
        }
        return {
            "systemInstruction": {"parts": [{"text": instructions}]},
            "contents": [
                {"role": "user", "parts": [{"text": json.dumps(data, ensure_ascii=False)}]}
            ],
            "generationConfig": self._generation_config(),
        }

    def _generation_config(self) -> dict[str, object]:
        config: dict[str, object] = {
            "maxOutputTokens": self._options.max_output_tokens,
            "responseMimeType": "application/json",
            "responseSchema": _RESPONSE_SCHEMA,
        }
        if self._options.model.startswith(_TEMPERATURE_MODEL_PREFIX):
            config["temperature"] = self._options.temperature
            config["thinkingConfig"] = {"thinkingBudget": 0}
        elif self._options.model.startswith(_MINIMAL_THINKING_MODEL_PREFIX):
            config["thinkingConfig"] = {"thinkingLevel": "minimal"}
        else:
            config["thinkingConfig"] = {"thinkingLevel": "low"}
        return config

    def _status_error(self, response: httpx.Response) -> GeminiCallError:
        status = response.status_code
        if status != _RATE_LIMITED and status not in _RETRYABLE_STATUSES:
            return GeminiCallError(GeminiFailure.REJECTED)
        failure = (
            GeminiFailure.RATE_LIMITED if status == _RATE_LIMITED else GeminiFailure.UNAVAILABLE
        )
        error = _provider_error(response.content)
        if status == _RATE_LIMITED and _is_hard_quota(error):
            return GeminiCallError(failure, retry_forbidden=True)
        header = response.headers.get("retry-after")
        delay = self._header_delay(header) if header is not None else _retry_info_delay(error)
        # A delay that Gemini gave but that cannot be read ends the retries, as in `main`.
        return GeminiCallError(
            failure,
            retry_after_seconds=delay,
            retry_forbidden=header is not None and delay is None,
        )

    def _header_delay(self, header: str) -> float | None:
        text = header.strip()
        try:
            return _valid_delay(float(text))
        except ValueError:
            pass
        try:
            moment = parsedate_to_datetime(text)
        except TypeError, ValueError:
            return None
        if moment.tzinfo is None:
            return None
        return _valid_delay((moment - self._clock.now()).total_seconds())


def _reply(content: bytes) -> DraftReply:
    try:
        response = _ProviderResponse.model_validate_json(content)
    except ValidationError as error:
        raise GeminiCallError(GeminiFailure.INVALID_OUTPUT) from error
    provider_usage = response.usage_metadata
    usage = TokenUsage(
        input_token_count=provider_usage.prompt_token_count,
        output_token_count=(
            provider_usage.candidates_token_count + provider_usage.thoughts_token_count
        ),
    )
    blocked = response.prompt_feedback is not None and response.prompt_feedback.block_reason
    candidate = response.candidates[0] if response.candidates else None
    # A blocked or unfinished answer is refused, and its tokens still count (contract `LlmUsage`).
    if (
        blocked
        or candidate is None
        or candidate.finish_reason != _FINISHED
        or not candidate.content
    ):
        raise GeminiCallError(GeminiFailure.INVALID_OUTPUT, usage=usage)
    text = "".join(part.text for part in candidate.content.parts if not part.thought)
    try:
        output = _Output.model_validate_json(text)
    except ValidationError as error:
        raise GeminiCallError(GeminiFailure.INVALID_OUTPUT, usage=usage) from error
    if not output.answerable:
        return UnanswerableRequest(usage=usage)
    if not output.answer.strip():
        raise GeminiCallError(GeminiFailure.INVALID_OUTPUT, usage=usage)
    return WrittenDraft(
        text=output.answer.strip(),
        cited_source_ids=tuple(output.citations),
        is_clarification=output.is_clarification,
        usage=usage,
    )


def _provider_error(content: bytes) -> _ProviderErrorObject | None:
    try:
        return _ProviderError.model_validate_json(content).error
    except ValidationError:
        return None


def _is_hard_quota(error: _ProviderErrorObject | None) -> bool:
    if error is None:
        return False
    texts = [error.message]
    for detail in error.details:
        if detail.get("@type") == _QUOTA_FAILURE_TYPE:
            violations: object = detail.get("violations")
            if isinstance(violations, list):
                texts.extend(str(violation) for violation in cast("list[object]", violations))
    return any(_HARD_QUOTA.search(text) for text in texts)


def _retry_info_delay(error: _ProviderErrorObject | None) -> float | None:
    details = error.details if error is not None else []
    delays: list[object] = [
        detail.get("retryDelay") for detail in details if detail.get("@type") == _RETRY_INFO_TYPE
    ]
    delay = delays[0] if delays else None
    if not isinstance(delay, str) or not delay.endswith("s"):
        return None
    try:
        return _valid_delay(float(delay.removesuffix("s")))
    except ValueError:
        return None


def _valid_delay(seconds: float) -> float | None:
    if not math.isfinite(seconds) or not 0 <= seconds <= _MAX_RETRY_AFTER_SECONDS:
        return None
    return seconds

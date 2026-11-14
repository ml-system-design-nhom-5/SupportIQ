"""The `AiService` port over HTTP, with the `httpx` client created once at startup (ARCH-24).

- Every call sends the service token and `traceparent` (contracts v1 design, Common elements;
  LOG-05). The token is Secret: it lives in the client's default headers only, never in a log,
  a span, or an error (SEC-09).
- Every call has its timeout from the settings, around the whole call, so the one retry after
  a connection error, `502`, or `503` never makes a call last longer (ADR-0011, `ai-service`
  replicas, item 2; ERR-12). A timeout is never retried.
- A `4xx` means that backend sent a request that `ai-service` refused: a defect. A `5xx`, a
  timeout, and a connection error are dependency failures (ERR taxonomy). The one exception is
  the `404` of a KB document version, which means that the loaded KB has no such version.
"""

import asyncio
from dataclasses import dataclass
from http import HTTPStatus
from urllib.parse import quote

import httpx
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from supportiq_backend.platform import MILLISECONDS_PER_SECOND
from supportiq_backend.suggestions.adapters.ai_service_payloads import (
    parse_analysis_response,
    parse_asset_versions_response,
    parse_draft_response,
    parse_kb_document_version_response,
    to_request_body,
)
from supportiq_backend.suggestions.domain import (
    AiServiceContractError,
    AiServiceUnavailableError,
    AssetVersions,
    KbDocumentId,
    KbDocumentVersion,
    KbDocumentVersionTag,
    ReceivedAnalysis,
    ReceivedDraftOutcome,
    SuggestionRequest,
)

ANALYSES_PATH = "/v1/analyses"
DRAFTS_PATH = "/v1/drafts"
ASSET_VERSIONS_PATH = "/v1/asset-versions"
KB_DOCUMENT_VERSION_PATH = "/v1/kb-documents/{document_id}/versions/{version}"
AUTHORIZATION_HEADER = "Authorization"
BEARER_PREFIX = "Bearer "
JSON_CONTENT_TYPE = "application/json"
# The statuses after which a call is sent once more (ADR-0011, `ai-service` replicas, item 2).
_RETRYABLE_STATUSES = frozenset({HTTPStatus.BAD_GATEWAY, HTTPStatus.SERVICE_UNAVAILABLE})
_CALL_ATTEMPTS = 2


@dataclass(frozen=True, slots=True)
class AiServiceTimeouts:
    """The timeout of each call, from the settings (ERR-09).

    Attributes:
        analysis_ms: `ai_service_analysis_timeout_ms`, for `createAnalysis`.
        draft_ms: `ai_service_draft_timeout_ms`, for `createDraft`.
        read_ms: `ai_service_read_timeout_ms`, for the reads.
    """

    analysis_ms: int
    draft_ms: int
    read_ms: int


def create_ai_service_client(
    base_url: str, service_token: str, *, transport: httpx.AsyncBaseTransport | None = None
) -> httpx.AsyncClient:
    """Create the one HTTP client of the process, for the composition root (PY-34).

    Args:
        base_url: `ai_service_base_url`.
        service_token: The service token. Secret.
        transport: The transport; None for the network. Adapter tests pass an in-memory one.

    Returns:
        The client. Each call sets its own timeout.
    """
    return httpx.AsyncClient(
        base_url=base_url,
        headers={AUTHORIZATION_HEADER: BEARER_PREFIX + service_token},
        follow_redirects=False,
        transport=transport,
    )


class HttpAiService:
    """Implement the `AiService` port with `httpx`."""

    def __init__(self, client: httpx.AsyncClient, timeouts: AiServiceTimeouts) -> None:
        """Keep the client and the timeouts.

        Args:
            client: The client from `create_ai_service_client`.
            timeouts: The timeout of each call.
        """
        self._client = client
        self._timeouts = timeouts
        self._propagator = TraceContextTextMapPropagator()

    async def analyze(self, request: SuggestionRequest) -> ReceivedAnalysis:
        """Run the pipeline up to routing (`createAnalysis`).

        Args:
            request: The request.

        Returns:
            The analysis as received.

        Raises:
            AiServiceUnavailableError: A timeout, a connection error, or a `5xx`.
            AiServiceContractError: A `4xx`, or a response outside the contract.
        """
        body = await self._call(
            "POST", ANALYSES_PATH, to_request_body(request), self._timeouts.analysis_ms
        )
        return parse_analysis_response(body)

    async def draft(self, request: SuggestionRequest) -> ReceivedDraftOutcome:
        """Run the whole pipeline (`createDraft`).

        Args:
            request: The request.

        Returns:
            The draft outcome as received.

        Raises:
            AiServiceUnavailableError: A timeout, a connection error, or a `5xx`.
            AiServiceContractError: A `4xx`, or a response outside the contract.
        """
        body = await self._call(
            "POST", DRAFTS_PATH, to_request_body(request), self._timeouts.draft_ms
        )
        return parse_draft_response(body)

    async def fetch_asset_versions(self) -> AssetVersions:
        """Read the versions of the release that ai-service serves (`getAssetVersions`).

        Reads are not retried (backend ticket workflow design, The `ai-service` client).

        Returns:
            The versions.

        Raises:
            AiServiceUnavailableError: A timeout, a connection error, or a `5xx`.
            AiServiceContractError: A `4xx`, or a response outside the contract.
        """
        body = await self._call(
            "GET", ASSET_VERSIONS_PATH, None, self._timeouts.read_ms, attempts=1
        )
        return parse_asset_versions_response(body)

    async def fetch_kb_document_version(
        self, document_id: KbDocumentId, version: KbDocumentVersionTag
    ) -> KbDocumentVersion | None:
        """Read one version of a KB document in full (`getKbDocumentVersion`).

        Reads are not retried (backend ticket workflow design, The `ai-service` client).

        Args:
            document_id: The KB document.
            version: The version of the document.

        Returns:
            The document version, or None when the loaded KB has no such version (`404`).

        Raises:
            AiServiceUnavailableError: A timeout, a connection error, or a `5xx`.
            AiServiceContractError: Another `4xx`, or a response outside the contract.
        """
        path = KB_DOCUMENT_VERSION_PATH.format(
            document_id=_to_path_segment(document_id), version=_to_path_segment(version)
        )
        response = await self._exchange("GET", path, None, self._timeouts.read_ms, attempts=1)
        if response.status_code == HTTPStatus.NOT_FOUND:
            return None
        return parse_kb_document_version_response(_read_success(response), document_id, version)

    async def _call(
        self,
        method: str,
        path: str,
        body: str | None,
        timeout_ms: int,
        *,
        attempts: int = _CALL_ATTEMPTS,
    ) -> bytes:
        response = await self._exchange(method, path, body, timeout_ms, attempts=attempts)
        return _read_success(response)

    async def _exchange(
        self,
        method: str,
        path: str,
        body: str | None,
        timeout_ms: int,
        *,
        attempts: int,
    ) -> httpx.Response:
        headers: dict[str, str] = {}
        self._propagator.inject(headers)
        if body is not None:
            headers["Content-Type"] = JSON_CONTENT_TYPE
        call = _Call(
            method, path, body, headers, httpx.Timeout(timeout_ms / MILLISECONDS_PER_SECOND)
        )
        try:
            async with asyncio.timeout(timeout_ms / MILLISECONDS_PER_SECOND):
                response = await self._send(call, attempts)
        except httpx.DecodingError as error:
            # A body that its own encoding cannot decode is a response outside the contract.
            raise AiServiceContractError from error
        except (TimeoutError, httpx.RequestError) as error:
            # Every other error of the library becomes the error of the port (ARCH-28).
            raise AiServiceUnavailableError from error
        return response

    async def _send(self, call: _Call, attempts: int) -> httpx.Response:
        for attempt in range(1, attempts + 1):
            is_last = attempt == attempts
            try:
                response = await self._client.request(
                    call.method,
                    call.path,
                    content=call.body,
                    headers=call.headers,
                    timeout=call.timeout,
                )
            except httpx.TransportError as error:
                # A timeout is never retried, so a retry never extends the call (ERR-12).
                if is_last or isinstance(error, httpx.TimeoutException):
                    raise
                continue
            if is_last or response.status_code not in _RETRYABLE_STATUSES:
                return response
        raise AiServiceUnavailableError


@dataclass(frozen=True, slots=True)
class _Call:
    method: str
    path: str
    body: str | None
    headers: dict[str, str]
    timeout: httpx.Timeout


def _to_path_segment(identifier: str) -> str:
    # Every reserved character is percent-encoded, so an identifier is always one segment of
    # the path. The interface layer lets through only identifiers of the contract's pattern,
    # which are never empty and never a dot segment that a URL would resolve.
    return quote(identifier, safe="")


def _read_success(response: httpx.Response) -> bytes:
    if response.status_code == HTTPStatus.OK:
        return response.content
    if response.status_code >= HTTPStatus.INTERNAL_SERVER_ERROR:
        raise AiServiceUnavailableError
    raise AiServiceContractError

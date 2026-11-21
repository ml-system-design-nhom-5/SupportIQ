"""Fakes of the LLM call: a network that answers from a script, and Gemini responses (ARCH-27).

No test reaches Gemini: the client of the egress allow-list sends every request to the scripted
network, which keeps it so a test can read the payload, as a fake LLM adapter would capture it
(TEST-16, TEST-26).
"""

import json
from collections.abc import Iterable
from http import HTTPStatus
from typing import Any

import httpx
from pydantic import SecretStr

from app.drafting import DraftRequest, OrderFact, PolicySource
from app.drafting.adapters.gemini import GeminiClient, GeminiOptions
from app.drafting.adapters.prompt_files import DraftingPrompts
from app.platform.egress import create_egress_client, packaged_egress_allow_list
from tests.unit.platform.fakes import FakeClock

API_KEY = "gemini-key-for-unit-tests"
SYSTEM_INSTRUCTIONS = "A fake system prompt for tests."
AUTHORITY_INSTRUCTIONS = "A fake prompt for when a manager decides."
PROMPTS = DraftingPrompts(
    version="prompts-sample-1",
    system_instructions=SYSTEM_INSTRUCTIONS,
    requires_authority_instructions=AUTHORITY_INSTRUCTIONS,
)
OPTIONS = GeminiOptions(
    model="gemini-3.5-flash-lite",
    api_key=SecretStr(API_KEY),
    max_output_tokens=1024,
    temperature=0.1,
)
REQUEST = DraftRequest(
    message="Where is my order [ORDER_ID_1]?",
    intent="track_order",
    policy_sources=(
        PolicySource(
            source_id="S1",
            document_id="SAMPLE-DELIVERY-001",
            version="1.0",
            title="A fake delivery policy",
            snippet="A fake passage about deliveries.",
        ),
    ),
    order_facts=(OrderFact(source_id="S2", field="shipment_status", value="in_transit"),),
    requires_authority=False,
)

type Scripted = httpx.Response | httpx.HTTPError


class ScriptedNetwork(httpx.BaseTransport):
    """A network that answers each request with the next entry of its script."""

    def __init__(self, script: Iterable[Scripted]) -> None:
        """Keep the script.

        Args:
            script: A response, or an error to raise, for each request in turn.
        """
        self.requests: list[httpx.Request] = []
        self._script = list(script)

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        """Keep the request and answer it from the script.

        Args:
            request: The request.

        Returns:
            The next response of the script.

        Raises:
            httpx.HTTPError: The next entry of the script is an error.
        """
        self.requests.append(request)
        entry = self._script.pop(0)
        if isinstance(entry, httpx.HTTPError):
            raise entry
        return entry

    def payloads(self) -> list[dict[str, Any]]:
        """Return the JSON body of every request.

        Returns:
            The bodies, in order.
        """
        return [json.loads(request.content) for request in self.requests]

    def user_data(self) -> dict[str, Any]:
        """Return the JSON document of the user content of the last request.

        Returns:
            The data that the model receives apart from its instructions.
        """
        payload = self.payloads()[-1]
        return json.loads(payload["contents"][0]["parts"][0]["text"])


def gemini_client(
    network: ScriptedNetwork, clock: FakeClock | None = None, options: GeminiOptions = OPTIONS
) -> GeminiClient:
    """Build the Gemini client over the client of the egress allow-list and a network.

    Args:
        network: The network that answers.
        clock: The clock that reads a `Retry-After` date.
        options: How the model is called.

    Returns:
        The client.
    """
    http_client = create_egress_client(packaged_egress_allow_list(), network)
    return GeminiClient(http_client, options, PROMPTS, clock or FakeClock())


def answer(
    text: str = "Your order is in_transit [S2].",
    citations: tuple[str, ...] = ("S2",),
    *,
    answerable: bool = True,
    is_clarification: bool = False,
) -> str:
    """Return the JSON that the model writes.

    Args:
        text: The draft.
        citations: The sources that it cites.
        answerable: Whether the sources answer the request.
        is_clarification: Whether the draft asks for missing information.

    Returns:
        The JSON text.
    """
    return json.dumps(
        {
            "answerable": answerable,
            "answer": text,
            "citations": list(citations),
            "is_clarification": is_clarification,
        }
    )


def gemini_response(
    output: str | None = None,
    *,
    finish_reason: str = "STOP",
    usage: dict[str, int] | None = None,
) -> httpx.Response:
    """Return a `generateContent` response of Gemini.

    Args:
        output: The text that the model writes; `answer()` when None.
        finish_reason: Why the model stopped.
        usage: The usage metadata; 12 prompt tokens, 7 output tokens, and 3 thinking tokens
            when None.

    Returns:
        The response.
    """
    body = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"text": "A thought that is not the answer.", "thought": True},
                        {"text": answer() if output is None else output},
                    ]
                },
                "finishReason": finish_reason,
            }
        ],
        "usageMetadata": usage
        or {"promptTokenCount": 12, "candidatesTokenCount": 7, "thoughtsTokenCount": 3},
        "modelVersion": "gemini-3.5-flash-lite-001",
    }
    return httpx.Response(HTTPStatus.OK, json=body)


def error_response(
    status: HTTPStatus, *, body: object = None, headers: dict[str, str] | None = None
) -> httpx.Response:
    """Return an error response of Gemini.

    Args:
        status: The status.
        body: The JSON body; none when None.
        headers: The headers.

    Returns:
        The response.
    """
    if body is None:
        return httpx.Response(status, headers=headers)
    return httpx.Response(status, json=body, headers=headers)


def retry_info(delay: str) -> dict[str, object]:
    """Return an error body with a `google.rpc.RetryInfo` detail.

    Args:
        delay: The `retryDelay`, such as `2s`.

    Returns:
        The body.
    """
    return {
        "error": {
            "message": "Resource exhausted.",
            "details": [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": delay}],
        }
    }

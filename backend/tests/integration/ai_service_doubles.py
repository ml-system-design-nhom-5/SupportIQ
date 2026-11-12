"""In-memory doubles of ai-service for the tests that run the application (TEST-16).

`create_app` takes the transport of its ai-service client. The tests pass a `FakeAiService`,
so no test resolves a name or opens a socket to ai-service, and each test can read every
request that backend sent.
"""

import json
from collections.abc import Awaitable, Callable
from pathlib import Path

import httpx

EXAMPLES = Path(__file__).parents[3] / "contracts" / "examples"
# The example of `ai-service` contract 1.0.0 that answers each operation.
EXAMPLE_OF_PATH = {
    "/v1/analyses": "createAnalysis/draft.json",
    "/v1/drafts": "createDraft/draft-ready.json",
    "/v1/asset-versions": "getAssetVersions/loaded.json",
}
CONNECTION_REFUSED = "ai-service refused the connection"

type Answer = Callable[[httpx.Request], Awaitable[httpx.Response]]


class FakeAiService(httpx.AsyncBaseTransport):
    """An in-memory ai-service that answers with a function and keeps every request.

    Attributes:
        requests: Every request that backend sent, in order.
        is_closed: Whether the ai-service client of the replica was closed.
    """

    def __init__(self, answer: Answer) -> None:
        """Answer every request with a function.

        Args:
            answer: Returns the response to a request, or raises the error of a transport.
        """
        self.requests: list[httpx.Request] = []
        self.is_closed = False
        self._answer = answer

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """Keep the request and answer it.

        Args:
            request: The request that backend sent.

        Returns:
            The answer.
        """
        await request.aread()
        self.requests.append(request)
        return await self._answer(request)

    async def aclose(self) -> None:
        """Note that the client of the replica was closed."""
        self.is_closed = True

    def paths(self) -> list[str]:
        """Return the path of every request, in order."""
        return [request.url.path for request in self.requests]

    def sent_text(self) -> str:
        """Return the bodies of every request, one per line."""
        return "\n".join(request.content.decode() for request in self.requests)


async def serve_examples(request: httpx.Request) -> httpx.Response:
    """Answer with the example of the operation in `ai-service` contract 1.0.0.

    Args:
        request: The request.

    Returns:
        The example response, with status `200`.
    """
    example = json.loads((EXAMPLES / EXAMPLE_OF_PATH[request.url.path]).read_text())
    return httpx.Response(httpx.codes.OK, json=example["value"])


async def refuse_connection(request: httpx.Request) -> httpx.Response:
    """Fail as an ai-service that is down does.

    Args:
        request: The request.

    Raises:
        httpx.ConnectError: Always.
    """
    raise httpx.ConnectError(CONNECTION_REFUSED, request=request)

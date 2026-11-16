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
KB_DOCUMENTS_PATH = "/v1/kb-documents/"
# The one KB document version that the in-memory ai-service knows, and its answer to any other.
KB_DOCUMENT_EXAMPLE = "getKbDocumentVersion/found.json"
KB_DOCUMENT_NOT_FOUND_EXAMPLE = "problems/not-found.json"
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

    A read of a KB document version gets the example document when it names that version, and
    the `404` example for any other version, as an ai-service whose KB holds only it.

    Args:
        request: The request.

    Returns:
        The example response, with status `200`, or `404` for an unknown KB document version.
    """
    if request.url.path.startswith(KB_DOCUMENTS_PATH):
        return _serve_kb_document(request.url.path)
    return httpx.Response(httpx.codes.OK, json=read_example(EXAMPLE_OF_PATH[request.url.path]))


async def refuse_connection(request: httpx.Request) -> httpx.Response:
    """Fail as an ai-service that is down does.

    Args:
        request: The request.

    Raises:
        httpx.ConnectError: Always.
    """
    raise httpx.ConnectError(CONNECTION_REFUSED, request=request)


def read_example(name: str) -> dict[str, object]:
    """Read the body of one example file of the contracts.

    Args:
        name: The file under `contracts/examples`, such as `getKbDocumentVersion/found.json`.

    Returns:
        The `value` of the example.
    """
    example: dict[str, dict[str, object]] = json.loads((EXAMPLES / name).read_text())
    return example["value"]


def answer_with(body: object, status: int = httpx.codes.OK) -> Answer:
    """Return an answer that sends one body to every request, whatever its path.

    Args:
        body: The JSON body.
        status: The status of the answer.

    Returns:
        The answer, for `FakeAiService`.
    """

    async def answer(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(status, json=body)

    return answer


def _serve_kb_document(path: str) -> httpx.Response:
    document = read_example(KB_DOCUMENT_EXAMPLE)
    known = f"{KB_DOCUMENTS_PATH}{document['document_id']}/versions/{document['version']}"
    if path == known:
        return httpx.Response(httpx.codes.OK, json=document)
    return httpx.Response(httpx.codes.NOT_FOUND, json=read_example(KB_DOCUMENT_NOT_FOUND_EXAMPLE))

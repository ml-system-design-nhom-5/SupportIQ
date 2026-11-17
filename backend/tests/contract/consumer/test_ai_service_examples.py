"""Consumer tests: the ai-service client reads every example of `ai-service` contract 1.0.0.

Each `200` example of `createAnalysis`, `createDraft`, `getAssetVersions`, and
`getKbDocumentVersion` is served as is, and each problem example with its status (CON-28).
Unknown statuses and reason codes, the reason codes that only backend sets, and a draft on an
outcome without one are refused as responses outside the contract, which makes the part
unavailable (CON-22).
"""

import json
from datetime import UTC, datetime
from http import HTTPStatus
from pathlib import Path

import httpx
import pytest

from supportiq_backend.suggestions import (
    AiReasonCode,
    AiServiceContractError,
    AiServiceUnavailableError,
    DraftReady,
    KbDocumentId,
    KbDocumentVersionTag,
    NoDraft,
    StaffIntent,
    SuggestionRequest,
)
from supportiq_backend.suggestions.adapters.ai_service_client import (
    AiServiceTimeouts,
    HttpAiService,
    create_ai_service_client,
)

EXAMPLES = Path(__file__).parents[4] / "contracts" / "examples"
REQUEST = SuggestionRequest(
    message="Where is my refund for [ORDER_ID_1]?",
    order_context=None,
    as_of=datetime(2026, 11, 5, 8, 12, 30, tzinfo=UTC),
    intent_override=None,
)
TIMEOUTS = AiServiceTimeouts(analysis_ms=3_000, draft_ms=11_000, read_ms=3_000)
ANALYSIS_EXAMPLES = sorted((EXAMPLES / "createAnalysis").glob("*.json"))
DRAFT_EXAMPLES = sorted((EXAMPLES / "createDraft").glob("*.json"))
PROBLEMS = {
    "service-token-rejected": HTTPStatus.UNAUTHORIZED,
    "unknown-kb-version": HTTPStatus.UNPROCESSABLE_CONTENT,
    "release-not-loaded": HTTPStatus.SERVICE_UNAVAILABLE,
    "ai-service-not-ready": HTTPStatus.SERVICE_UNAVAILABLE,
}


def example_value(path: Path) -> dict[str, object]:
    example: dict[str, dict[str, object]] = json.loads(path.read_text(encoding="utf-8"))
    return example["value"]


def serving(body: object, status: HTTPStatus = HTTPStatus.OK) -> HttpAiService:
    content = json.dumps(body).encode()

    def handle(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, content=content)

    client = create_ai_service_client(
        "http://ai-service.test", "token", transport=httpx.MockTransport(handle)
    )
    return HttpAiService(client, TIMEOUTS)


@pytest.mark.anyio
@pytest.mark.parametrize("path", ANALYSIS_EXAMPLES, ids=lambda path: path.stem)
async def test_the_client_reads_every_analysis_example(path: Path) -> None:
    received = await serving(example_value(path)).analyze(REQUEST)

    assert json.loads(received.body) == example_value(path)


@pytest.mark.anyio
async def test_the_staff_intent_example_has_no_probability() -> None:
    value = example_value(EXAMPLES / "createAnalysis" / "staff-intent.json")

    received = await serving(value).analyze(REQUEST)

    assert isinstance(received.analysis.intent, StaffIntent)


@pytest.mark.anyio
@pytest.mark.parametrize("path", DRAFT_EXAMPLES, ids=lambda path: path.stem)
async def test_the_client_reads_every_draft_example(path: Path) -> None:
    value = example_value(path)

    received = await serving(value).draft(REQUEST)

    assert isinstance(received.outcome, DraftReady if value["status"] == "draft_ready" else NoDraft)
    assert json.loads(received.analysis_body) == value["analysis"]


@pytest.mark.anyio
async def test_the_requires_authority_example_carries_the_reason_code() -> None:
    value = example_value(EXAMPLES / "createDraft" / "requires-authority.json")

    received = await serving(value).draft(REQUEST)

    assert AiReasonCode.REQUIRES_AUTHORITY in received.outcome.details.reason_codes


@pytest.mark.anyio
async def test_the_client_reads_the_asset_versions_example() -> None:
    value = example_value(EXAMPLES / "getAssetVersions" / "loaded.json")

    versions = await serving(value).fetch_asset_versions()

    assert versions.release_id == value["release_id"]


@pytest.mark.anyio
async def test_the_client_reads_the_kb_document_version_example() -> None:
    value = example_value(EXAMPLES / "getKbDocumentVersion" / "found.json")
    document_id = KbDocumentId(str(value["document_id"]))
    version = KbDocumentVersionTag(str(value["version"]))

    document = await serving(value).fetch_kb_document_version(document_id, version)

    assert document is not None
    assert (document.document_id, document.version, document.body, document.effective_end_at) == (
        value["document_id"],
        value["version"],
        value["body"],
        None,
    )


@pytest.mark.anyio
async def test_the_not_found_problem_of_a_kb_document_version_means_no_document() -> None:
    value = example_value(EXAMPLES / "problems" / "not-found.json")

    document = await serving(value, HTTPStatus.NOT_FOUND).fetch_kb_document_version(
        KbDocumentId("SAMPLE-REFUND-001"), KbDocumentVersionTag("9.9")
    )

    assert document is None


@pytest.mark.anyio
@pytest.mark.parametrize(
    "change",
    [
        {"status": "drafted_maybe"},
        {"reason_codes": ["a_reason_of_a_later_version"]},
        {"reason_codes": ["ai_service_unavailable"]},
        {"reason_codes": ["pseudonymization_failed"]},
    ],
    ids=["unknown-status", "unknown-reason", "backend-reason", "pseudonymization-reason"],
)
async def test_a_draft_outside_the_contract_is_refused(change: dict[str, object]) -> None:
    value = example_value(EXAMPLES / "createDraft" / "abstained.json") | change

    with pytest.raises(AiServiceContractError):
        await serving(value).draft(REQUEST)


@pytest.mark.anyio
async def test_an_outcome_without_a_draft_that_carries_one_is_refused() -> None:
    ready = example_value(EXAMPLES / "createDraft" / "draft-ready.json")
    value = example_value(EXAMPLES / "createDraft" / "abstained.json") | {"draft": ready["draft"]}

    with pytest.raises(AiServiceContractError):
        await serving(value).draft(REQUEST)


@pytest.mark.anyio
async def test_an_unknown_routing_recommendation_is_refused() -> None:
    value = example_value(EXAMPLES / "createAnalysis" / "draft.json")
    value["routing"] = {"recommendation": "maybe", "reason_codes": []}

    with pytest.raises(AiServiceContractError):
        await serving(value).analyze(REQUEST)


@pytest.mark.anyio
@pytest.mark.parametrize(("name", "status"), PROBLEMS.items(), ids=list(PROBLEMS))
async def test_each_problem_of_ai_service_makes_the_call_unavailable(
    name: str, status: HTTPStatus
) -> None:
    value = example_value(EXAMPLES / "problems" / f"{name}.json")

    with pytest.raises(AiServiceUnavailableError):
        await serving(value, status).draft(REQUEST)

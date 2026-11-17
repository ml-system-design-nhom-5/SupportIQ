"""Fake escalation cases, approvals, guardrail results, and a candidate application (TEST-18).

Every value is synthetic. The fake application stands in for `build_candidate_application` of
`ai-service`, whose real models need torch: it serves the six routes of contract 1.0.0, uses
the ports that the gate gives it, and answers in the shape of contract 1.0.0 only as far as the
gate reads it. Its routing is a small rule of its own, not the routing of `ai-service`.
"""

import hashlib
import json
import os
from collections.abc import Mapping, MutableMapping, Sequence
from pathlib import Path
from typing import TextIO

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from supportiq_ai_service.composition_root import CandidatePorts
from supportiq_ai_service.drafting import DraftRequest, LlmCallError
from supportiq_ai_service.intent import IntentDistribution, IntentModelError, IntentProbability
from supportiq_ai_service.retrieval import DocumentMatch, RetrievalError

from supportiq_release.composition_root import cli
from supportiq_release.gate.adapters import ApplicationFactory
from supportiq_release.gate.domain import (
    INTERIM_LABEL,
    DraftStatus,
    Expected,
    GuardrailSuite,
    ReasonCode,
    Recommendation,
)
from tests.unit.candidate.fakes import write_sources, write_spec

SET_NAME = "escalation/fake-v1"
# The versions of the fake candidate of `tests/unit/candidate/fakes.py`, whose KB is empty.
WRITTEN_FOR: dict[str, object] = {
    "ai_service_contract": "1.0.0",
    "model_version": "fake-model-1",
    "routing_version": "fake-routing-1",
    "kb_version": "v9",
    "kb_document_count": 0,
}
MESSAGE = "Where is [ORDER_ID_1] now?"
# A message that makes the fake application call the LLM step during `createDraft`.
LLM_MESSAGE = "Please write me a reply about [ORDER_ID_1]."
INTERNAL_ERROR = "urn:supportiq:problem:internal-error"
# The labels of the fake model, and the distribution it gives every message.
FAKE_LABELS = ("track_order", "request_refund", "human_agent")
FAKE_DISTRIBUTION = (("track_order", 0.9), ("request_refund", 0.06), ("human_agent", 0.04))
_TAU = 0.7
_SENSITIVE_MIN = 0.1
# The expected outcomes of `expected_document` and `failure_expected`, as the gate reads them.
ABSTAIN = Expected(
    http_status=200,
    problem_type=None,
    recommendation=Recommendation.ABSTAIN,
    draft_status=DraftStatus.ABSTAINED,
    required_reason_codes=frozenset({ReasonCode.NO_VALID_DOCUMENT}),
    forbidden_reason_codes=frozenset({ReasonCode.LOW_CONFIDENCE}),
    no_other_reason_codes=True,
    requires_authority=False,
    llm_called=False,
)
FAILS = Expected(
    http_status=500,
    problem_type=INTERNAL_ERROR,
    recommendation=None,
    draft_status=None,
    required_reason_codes=frozenset(),
    forbidden_reason_codes=frozenset(),
    no_other_reason_codes=False,
    requires_authority=None,
    llm_called=False,
)


def expected_document(**fields: object) -> dict[str, object]:
    """Return the expected outcome of a case that abstains, with some fields replaced.

    Args:
        **fields: The fields to replace.

    Returns:
        The expected outcome, as the file of the cases holds it.
    """
    return {
        "http_status": 200,
        "problem_type": None,
        "recommendation": "abstain",
        "draft_status": "abstained",
        "required_reason_codes": ["no_valid_document"],
        "forbidden_reason_codes": ["low_confidence"],
        "no_other_reason_codes": True,
        "requires_authority": False,
        "llm_called": False,
        **fields,
    }


def failure_expected() -> dict[str, object]:
    """Return the expected outcome of a case whose intent model or search fails.

    Returns:
        The expected outcome: `500 internal-error` from both operations.
    """
    return expected_document(
        http_status=500,
        problem_type=INTERNAL_ERROR,
        recommendation=None,
        draft_status=None,
        required_reason_codes=[],
        forbidden_reason_codes=[],
        no_other_reason_codes=False,
        requires_authority=None,
    )


def case_document(case_id: str = "fake-case-1", **fields: object) -> dict[str, object]:
    """Return a case that rests on the fake model, with some fields replaced.

    Args:
        case_id: The ID of the case.
        **fields: The fields to replace.

    Returns:
        The case, as the file of the cases holds it.
    """
    return {
        "case_id": case_id,
        "esc_rule": "ESC-04",
        "signal": "A fake signal",
        "request": {"message": MESSAGE, "as_of": "2026-11-17T09:00:00Z"},
        "inject": None,
        "depends_on_model": True,
        "expected": expected_document(),
        "without_kb_evidence": "A fake reason",
        **fields,
    }


def set_document(*cases: dict[str, object], **fields: object) -> dict[str, object]:
    """Return a set of cases for the fake candidate, with some fields replaced.

    Args:
        *cases: The cases; one case of `case_document` when none is given.
        **fields: The fields of the set to replace.

    Returns:
        The set, as the file of the cases holds it.
    """
    return {
        "label": INTERIM_LABEL,
        "set": SET_NAME,
        "written_for": WRITTEN_FOR,
        "cases": list(cases) or [case_document()],
        **fields,
    }


def approval_document(cases_sha256: str, **fields: object) -> dict[str, object]:
    """Return a frozen approval of the fake set, with some fields replaced.

    Args:
        cases_sha256: The SHA-256 of the file of the cases that the approval covers.
        **fields: The fields to replace.

    Returns:
        The approval record.
    """
    return {
        "format": "supportiq-case-set-approval/interim-1",
        "set": SET_NAME,
        "status": "frozen",
        "cases_sha256": cases_sha256,
        "approved_by": "project lead",
        "approved_on": "2026-11-17",
        **fields,
    }


def write_set(
    folder: Path, document: object | None = None, approval: Mapping[str, object] | None = None
) -> Path:
    """Write a set of cases and its approval record into a folder.

    Args:
        folder: The folder; it is created when it does not exist.
        document: The set; the set of `set_document` when None.
        approval: Fields that replace those of the frozen approval of the written bytes.

    Returns:
        The file of the cases.
    """
    folder.mkdir(parents=True, exist_ok=True)
    cases = folder / "cases.json"
    cases.write_text(json.dumps(set_document() if document is None else document))
    sha256 = hashlib.sha256(cases.read_bytes()).hexdigest()
    record = {**approval_document(sha256), **(approval or {})}
    (folder / "approval.json").write_text(json.dumps(record))
    return cases


def build_fake_candidate(base: Path, kb: bytes | None = None) -> Path:
    """Build the fake candidate of `tests/unit/candidate/fakes.py` with `build-candidate`.

    Args:
        base: An empty folder; it gets `sources/`, `releases/`, and `candidate/`.
        kb: The bytes of the KB file in place of the fake one, or None.

    Returns:
        The folder of the candidate.

    Raises:
        AssertionError: `build-candidate` refused the fake sources.
    """
    sources = write_sources(base / "sources")
    if kb is not None:
        (sources / "kb.json").write_bytes(kb)
    records = base / "releases"
    records.mkdir()
    output = base / "candidate"
    arguments = ["--spec", str(write_spec(sources)), "--release-records", str(records)]
    if cli.main(["build-candidate", *arguments, "--output", str(output)]) != cli.EXIT_SUCCESS:
        message = "build-candidate refused the fake sources"
        raise AssertionError(message)
    return output


GUARDRAIL_CLASSNAME = "tests.integration.guardrails.test_fake"


def junit_xml(  # noqa: PLR0913  # one keyword for each attribute that a test changes
    tests: int = 2,
    failures: int = 0,
    errors: int = 0,
    skipped: int = 0,
    *,
    suites: int = 1,
    name: str = GuardrailSuite.BACKEND.value,
    classnames: Sequence[str] = (GUARDRAIL_CLASSNAME,),
) -> bytes:
    """Return a JUnit XML file of pytest with the same counts and test cases in each suite.

    Args:
        tests: The tests of each suite, each a `testcase`.
        failures: The failed tests of each suite.
        errors: The errored tests of each suite.
        skipped: The skipped tests of each suite.
        suites: The number of `testsuite` elements.
        name: The name of each suite, which `run-gate.sh` sets to the name of its folder.
        classnames: The classnames of the test cases, in turn.

    Returns:
        The bytes of the file.
    """
    cases = "".join(
        f'<testcase classname="{classnames[index % len(classnames)]}" name="test_{index}"/>'
        for index in range(tests)
    )
    suite = (
        f'<testsuite name="{name}" tests="{tests}" failures="{failures}" errors="{errors}"'
        f' skipped="{skipped}">{cases}</testsuite>'
    )
    return (
        f'<?xml version="1.0" encoding="utf-8"?><testsuites>{suite * suites}</testsuites>'.encode()
    )


class FakeClassifier:
    """The fake intent model: the same distribution for every message."""

    def classify(self, message: str) -> IntentDistribution:
        """Return `FAKE_DISTRIBUTION`.

        Args:
            message: The message, unused.

        Returns:
            The distribution, most likely first.
        """
        del message
        return IntentDistribution(
            tuple(IntentProbability(label, value) for label, value in FAKE_DISTRIBUTION)
        )


class FakeSearch:
    """The fake search of an empty KB: no document matches."""

    def search(self, message: str) -> tuple[DocumentMatch, ...]:
        """Return no match.

        Args:
            message: The message, unused.

        Returns:
            No match.
        """
        del message
        return ()


def fake_application_factory(
    service_token: str | None = None,
    *,
    leak_message: bool = False,
    extra_route: str | None = None,
    built: MutableMapping[str, object] | None = None,
) -> ApplicationFactory:
    """Return a builder of the fake application, in place of `build_candidate_application`.

    Args:
        service_token: The token that the application accepts; when None, it reads
            `SERVICE_TOKEN` from the environment when it is built, as `ai-service` does.
        leak_message: Whether the application logs the message, which the gate must find.
        extra_route: A path that the application also serves with POST, or None.
        built: A mapping that records the manifest path and the token of the build.

    Returns:
        The builder.
    """

    def build(manifest_path: Path, ports: CandidatePorts, log_stream: TextIO) -> Starlette:
        token = os.environ.get("SERVICE_TOKEN", "") if service_token is None else service_token
        if built is not None:
            built.update({"manifest_path": manifest_path, "service_token": token})
        application = _FakeApplication(token, ports, log_stream, leak_message=leak_message)
        routes = [
            Route("/v1/analyses", application.analyses, methods=["POST"]),
            Route("/v1/drafts", application.drafts, methods=["POST"]),
            *(Route(path, _empty, methods=["GET"]) for path in _OTHER_PATHS),
        ]
        if extra_route is not None:
            routes.append(Route(extra_route, _empty, methods=["POST"]))
        return Starlette(routes=routes)

    return build


# The paths of contract 1.0.0 besides the two operations that the gate calls.
_OTHER_PATHS = (
    "/v1/kb-documents/{document_id}/versions/{version}",
    "/v1/asset-versions",
    "/health/live",
    "/health/ready",
)


class _FakeApplication:
    def __init__(
        self, service_token: str, ports: CandidatePorts, log_stream: TextIO, *, leak_message: bool
    ) -> None:
        self._service_token = service_token
        self._classifier = ports.classifier(FakeClassifier())
        self._search = ports.search(FakeSearch())
        self._writer = ports.writer
        self._log_stream = log_stream
        self._leak_message = leak_message

    async def analyses(self, request: Request) -> JSONResponse:
        denied = self._refused(request)
        if denied is not None:
            return denied
        message = str((await request.json())["message"])
        try:
            recommendation, codes = self._analyse(message)
        except IntentModelError, RetrievalError:
            return JSONResponse({"type": INTERNAL_ERROR}, 500)
        return JSONResponse({"routing": {"recommendation": recommendation, "reason_codes": codes}})

    async def drafts(self, request: Request) -> JSONResponse:
        denied = self._refused(request)
        if denied is not None:
            return denied
        message = str((await request.json())["message"])
        try:
            recommendation, codes = self._analyse(message)
        except IntentModelError, RetrievalError:
            return JSONResponse({"type": INTERNAL_ERROR}, 500)
        routing = {"recommendation": recommendation, "reason_codes": list(codes)}
        if message == LLM_MESSAGE:
            try:
                self._writer.write(DraftRequest(message, "track_order", (), (), False))
            except LlmCallError:
                codes.append("llm_unavailable")
        status = "abstained" if recommendation == "abstain" else "escalation_recommended"
        return JSONResponse(
            {"analysis": {"routing": routing}, "status": status, "reason_codes": codes}
        )

    def _analyse(self, message: str) -> tuple[str, list[str]]:
        distribution = self._classifier.classify(message)
        self._search.search(message)
        self._log_stream.write(json.dumps({"event": "analysis_created"}) + "\n")
        if self._leak_message:
            self._log_stream.write(json.dumps({"event": "leak", "message": message}) + "\n")
        return _routing(distribution)

    def _refused(self, request: Request) -> JSONResponse | None:
        token = self._service_token
        if not token or request.headers.get("authorization") != f"Bearer {token}":
            return JSONResponse({"type": "urn:supportiq:problem:unauthorized"}, 401)
        return None


async def _empty(request: Request) -> JSONResponse:
    del request
    return JSONResponse({})


def _routing(distribution: IntentDistribution) -> tuple[str, list[str]]:
    top = distribution.probabilities[0]
    escalate = top.label == "human_agent"
    codes = ["human_agent_requested"] if escalate else []
    if top.probability < _TAU:
        codes.append("low_confidence")
    codes.append("no_valid_document")
    if distribution.probability_of("request_refund") >= _SENSITIVE_MIN:
        codes.append("requires_authority")
    return ("escalate" if escalate else "abstain", codes)

"""Each setting of the pipeline reaches its place when the command wires a release (ARCH-21).

The release holds two KB document versions, both mapped to the intent that the fake model is
sure of. The LLM answers from a script, through the client of the egress allow-list.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from http import HTTPStatus
from pathlib import Path

import pytest

from app.composition_root.cli import release_refusal_attributes
from app.composition_root.release_assets import (
    ReleaseModels,
    ReleaseServices,
    Timing,
    build_release_services,
    read_release_assets,
)
from app.intent.adapters.model_artifact import ModelArtifact
from app.platform import EventName
from app.platform.adapters.egress import (
    create_egress_client,
    packaged_egress_allow_list,
)
from app.platform.settings import Settings
from app.release.manifest import (
    ReleaseInvalidError,
    ReleaseInvalidReason,
    VerifiedReleaseSource,
)
from app.retrieval import RetrievalError
from app.retrieval.adapters.in_memory_index import Vectors
from app.retrieval.adapters.index_file import IndexConfiguration
from app.suggestions.domain import (
    DraftReady,
    LlmUsage,
    NoDraft,
    ReasonCode,
    SuggestionInput,
)
from tests.unit.composition_root.fakes import (
    KB_RELEASE_CHANGES,
    LONG_DOCUMENT,
    SHORT_DOCUMENT,
    FakeClassifier,
    load_fake_models,
)
from tests.unit.drafting.fakes import ScriptedNetwork, answer, error_response, gemini_response
from tests.unit.platform.fakes import LLM_ENVIRONMENT, RecordedEvent, RecordingEventRecorder
from tests.unit.release.fakes import EXAMPLE_VERSIONS
from tests.unit.release.release_folder import verified_release
from tests.unit.retrieval.fakes import KeywordEncoder

REQUEST = SuggestionInput(
    message="Where is my refund.", as_of=datetime(2026, 11, 5, 9, 30, tzinfo=UTC)
)
CLOCK_STEP_SECONDS = 0.25
MAX_OUTPUT_TOKENS = 321
TEMPERATURE = 0.3
ATTEMPT_TIMEOUT_MS = 1_234
# Large enough that the cost tells the two prices apart (LLM_ENVIRONMENT: 1000 and 2000).
USAGE = {
    "promptTokenCount": 100_000,
    "candidatesTokenCount": 40_000,
    "thoughtsTokenCount": 10_000,
}


@pytest.fixture
def source(tmp_path: Path) -> VerifiedReleaseSource:
    return verified_release(tmp_path, KB_RELEASE_CHANGES)


def _settings(**changes: object) -> Settings:
    return Settings.model_validate(
        {
            "service_token": "service-token-for-unit-tests",
            # The source is checked already, so the pipeline never reads this path.
            "release_manifest_path": Path("release-manifest.json"),
            **{name.lower(): value for name, value in LLM_ENVIRONMENT.items()},
            **changes,
        }
    )


@dataclass(slots=True)
class FakeTiming:
    """A clock that moves a quarter of a second at each reading, and a sleep that only counts."""

    now: float = 0.0
    sleeps: list[float] = field(default_factory=list[float])

    def monotonic(self) -> float:
        """Move the clock, and return it."""
        self.now += CLOCK_STEP_SECONDS
        return self.now

    def sleep(self, seconds: float) -> None:
        """Keep the wait instead of waiting."""
        self.sleeps.append(seconds)

    def timing(self) -> Timing:
        """Return the sources of the pipeline, with the middle of the jitter range."""
        return Timing(self.monotonic, self.sleep, lambda: 0.5)


def _services(
    source: VerifiedReleaseSource,
    settings: Settings,
    network: ScriptedNetwork,
    timing: FakeTiming | None = None,
) -> ReleaseServices:
    sources = (timing or FakeTiming()).timing()
    events = RecordingEventRecorder()
    assets = read_release_assets(source, settings, load_fake_models, events, sources)
    client = create_egress_client(packaged_egress_allow_list(), network)
    return build_release_services(assets, settings, events, client, sources)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("changes", "document_count", "source_count"),
    [
        # Both versions, the two passages of the long one and the passage of the short one.
        pytest.param({}, 2, 3, id="defaults"),
        pytest.param({"retrieval_top_k_documents": 1}, 1, 2, id="top-k"),
        pytest.param({"retrieval_max_chunks_per_document": 1}, 2, 2, id="chunks"),
        # The first passage always goes, and no other fits.
        pytest.param({"retrieval_token_budget_tokens": 1}, 2, 1, id="token-budget"),
        # The passages of the long version hold 100 and 60 tokens of the encoder, which fill the
        # budget, so the short version no longer fits.
        pytest.param({"retrieval_token_budget_tokens": 160}, 2, 2, id="token-count"),
    ],
)
async def test_the_retrieval_settings_choose_the_documents_and_the_passages(
    source: VerifiedReleaseSource,
    changes: dict[str, object],
    document_count: int,
    source_count: int,
) -> None:
    network = ScriptedNetwork([gemini_response(answer("Refunds go to the card [S1].", ("S1",)))])
    services = _services(source, _settings(**changes), network)

    analysis = await services.pipeline.analyze(REQUEST, source.current())
    await services.pipeline.draft(REQUEST, source.current())

    assert len(analysis.documents) == document_count
    assert len(network.user_data()["policy_sources"]) == source_count


@pytest.mark.anyio
async def test_the_llm_settings_shape_the_call_and_the_prices_give_its_cost(
    source: VerifiedReleaseSource,
) -> None:
    network = ScriptedNetwork(
        [gemini_response(answer("Refunds go to the card [S1].", ("S1",)), usage=USAGE)]
    )
    # A Gemini 2.5 model, the only kind that takes a temperature.
    settings = _settings(
        gemini_model="gemini-2.5-flash-lite",
        llm_max_output_tokens=MAX_OUTPUT_TOKENS,
        llm_temperature=TEMPERATURE,
        llm_attempt_timeout_ms=ATTEMPT_TIMEOUT_MS,
    )
    services = _services(source, settings, network)

    outcome = await services.pipeline.draft(REQUEST, source.current())

    assert isinstance(outcome, DraftReady)
    # 100 000 tokens at 1 000, and 50 000 at 2 000, per million tokens.
    assert outcome.details.llm_usage == LlmUsage(100_000, 50_000, 200)
    (request,) = network.requests
    assert request.url.path.endswith(f"/models/{settings.gemini_model}:generateContent")
    assert request.headers["x-goog-api-key"] == settings.gemini_api_key.get_secret_value()
    configuration = network.payloads()[0]["generationConfig"]
    assert (configuration["maxOutputTokens"], configuration["temperature"]) == (
        MAX_OUTPUT_TOKENS,
        TEMPERATURE,
    )
    # The attempt is shorter than what remains of the budget of the LLM step.
    assert request.extensions["timeout"]["read"] == ATTEMPT_TIMEOUT_MS / 1000


@pytest.mark.anyio
async def test_the_llm_is_called_at_most_the_attempts_of_the_setting(
    source: VerifiedReleaseSource,
) -> None:
    network = ScriptedNetwork([error_response(HTTPStatus.SERVICE_UNAVAILABLE)])
    services = _services(source, _settings(llm_max_attempts=1), network)

    outcome = await services.pipeline.draft(REQUEST, source.current())

    assert isinstance(outcome, NoDraft)
    assert outcome.details.reason_codes == (ReasonCode("llm_unavailable"),)
    assert len(network.requests) == 1


@pytest.mark.anyio
async def test_an_attempt_gets_what_remains_of_the_budget_of_the_setting(
    source: VerifiedReleaseSource,
) -> None:
    network = ScriptedNetwork([gemini_response(answer("Refunds go to the card [S1].", ("S1",)))])
    settings = _settings(llm_budget_ms=1_000, llm_attempt_timeout_ms=1_000)

    await _services(source, settings, network).pipeline.draft(REQUEST, source.current())

    # One reading of the clock passed between the deadline and the attempt.
    (request,) = network.requests
    assert request.extensions["timeout"]["read"] == 1 - CLOCK_STEP_SECONDS


@pytest.mark.anyio
async def test_a_retry_waits_the_backoff_of_the_settings(source: VerifiedReleaseSource) -> None:
    unavailable = error_response(HTTPStatus.SERVICE_UNAVAILABLE)
    network = ScriptedNetwork(
        [unavailable, unavailable, gemini_response(answer("Refunds go to the card [S1].", ("S1",)))]
    )
    settings = _settings(llm_max_attempts=3, llm_backoff_base_ms=250, llm_backoff_max_ms=300)
    timing = FakeTiming()

    outcome = await _services(source, settings, network, timing).pipeline.draft(
        REQUEST, source.current()
    )

    assert isinstance(outcome, DraftReady)
    # Half of 0.25 s, then half of 0.5 s capped at 0.3 s.
    assert timing.sleeps == pytest.approx([0.125, 0.15])


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("max_chars", "kind", "codes"), [(6, DraftReady, ()), (5, NoDraft, ("grounding_failed",))]
)
async def test_an_uncited_segment_is_checked_against_the_setting(
    source: VerifiedReleaseSource,
    max_chars: int,
    kind: type[DraftReady | NoDraft],
    codes: tuple[str, ...],
) -> None:
    # "Hello!" is an uncited segment of 6 characters.
    network = ScriptedNetwork(
        [gemini_response(answer("Hello!\n\nRefunds go to the card [S1].", ("S1",)))]
    )
    settings = _settings(grounding_uncited_segment_max_chars=max_chars)

    outcome = await _services(source, settings, network).pipeline.draft(REQUEST, source.current())

    assert isinstance(outcome, kind)
    assert outcome.details.reason_codes == tuple(ReasonCode(code) for code in codes)


def test_the_models_load_with_the_threads_of_the_setting(source: VerifiedReleaseSource) -> None:
    threads: list[int] = []

    def load(artifact: ModelArtifact, index: IndexConfiguration, cpu_threads: int) -> ReleaseModels:
        threads.append(cpu_threads)
        return load_fake_models(artifact, index, cpu_threads)

    read_release_assets(
        source,
        _settings(model_cpu_threads=3),
        load,
        RecordingEventRecorder(),
        FakeTiming().timing(),
    )

    assert threads == [3]


def test_the_kb_documents_of_the_release_are_served(source: VerifiedReleaseSource) -> None:
    services = _services(source, _settings(), ScriptedNetwork([]))
    release = source.current()

    found = services.kb_documents.find("SAMPLE-REFUND-002", "1.0", release)

    assert found is not None
    assert (found.document_id, found.version, found.title) == (
        "SAMPLE-REFUND-002",
        "1.0",
        "A fake refund method",
    )
    assert services.kb_documents.find("SAMPLE-REFUND-002", "2.0", release) is None


def test_loading_records_the_versions_of_the_models_and_of_the_kb(
    source: VerifiedReleaseSource,
) -> None:
    events = RecordingEventRecorder()

    read_release_assets(source, _settings(), load_fake_models, events, FakeTiming().timing())

    assert events.events == [
        RecordedEvent(
            EventName.MODEL_LOADED,
            {
                "model_version": EXAMPLE_VERSIONS.model_version,
                "index_version": EXAMPLE_VERSIONS.index_version,
                # One step of the fake clock passes while the models load.
                "duration_ms": 250,
            },
        ),
        RecordedEvent(
            EventName.KB_LOADED,
            {
                "kb_version": EXAMPLE_VERSIONS.kb_version,
                "mapping_version": EXAMPLE_VERSIONS.mapping_version,
                "document_count": 2,
            },
        ),
    ]


class _UnindexableEncoder(KeywordEncoder):
    """An encoder that fails on every passage of the KB, as a broken encoder would."""

    def encode_passages(self, texts: Sequence[str]) -> Vectors:
        """Fail.

        Raises:
            RetrievalError: Always.
        """
        del texts
        raise RetrievalError


def _load_unindexable_models(
    artifact: ModelArtifact, index: IndexConfiguration, cpu_threads: int
) -> ReleaseModels:
    del artifact, index, cpu_threads
    return ReleaseModels(classifier=FakeClassifier(), encoder=_UnindexableEncoder())


def test_an_encoder_that_cannot_index_the_kb_refuses_the_release(
    source: VerifiedReleaseSource,
) -> None:
    events = RecordingEventRecorder()

    with pytest.raises(ReleaseInvalidError) as refused:
        read_release_assets(
            source, _settings(), _load_unindexable_models, events, FakeTiming().timing()
        )

    # The models loaded, and the KB did not.
    assert [event.name for event in events.events] == [EventName.MODEL_LOADED]
    # `release.invalid` names the asset, never a text of the KB (LOG-29).
    assert release_refusal_attributes(refused.value) == {
        "reason": ReleaseInvalidReason.ASSET_INVALID.value,
        "asset": "index",
    }
    detail = str(refused.value)
    for document in (LONG_DOCUMENT, SHORT_DOCUMENT):
        assert str(document["title"]) not in detail
        assert str(document["body"]) not in detail

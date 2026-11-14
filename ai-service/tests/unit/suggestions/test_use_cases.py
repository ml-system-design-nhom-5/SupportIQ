"""Analyses and drafts need a loaded release and its KB version (DATA-56)."""

from datetime import UTC, datetime

import pytest

from supportiq_ai_service.release import ReleaseNotLoadedError
from supportiq_ai_service.suggestions import (
    CreateAnalysis,
    CreateDraft,
    SuggestionInput,
    UnknownKbVersionError,
)
from tests.unit.release.fakes import EXAMPLE_RELEASE, EXAMPLE_VERSIONS, StaticReleaseSource
from tests.unit.suggestions.fakes import EXAMPLE_ANALYSIS, EXAMPLE_DRAFT_READY, FakePipeline

pytestmark = pytest.mark.anyio

REQUEST = SuggestionInput(
    message="Where is my refund for [ORDER_ID_1]?", as_of=datetime(2026, 11, 5, 9, 30, tzinfo=UTC)
)
LOADED_KB = SuggestionInput(
    message=REQUEST.message, as_of=REQUEST.as_of, kb_version=EXAMPLE_VERSIONS.kb_version
)
OTHER_KB = SuggestionInput(message=REQUEST.message, as_of=REQUEST.as_of, kb_version="kb-other")


@pytest.mark.parametrize("request_input", [REQUEST, LOADED_KB])
async def test_an_analysis_runs_the_pipeline_of_the_loaded_release(
    request_input: SuggestionInput,
) -> None:
    pipeline = FakePipeline()

    analysis = await CreateAnalysis(StaticReleaseSource(), pipeline).execute(request_input)

    assert analysis == EXAMPLE_ANALYSIS
    assert pipeline.requests == [(request_input, EXAMPLE_RELEASE)]


@pytest.mark.parametrize("request_input", [REQUEST, LOADED_KB])
async def test_a_draft_runs_the_pipeline_of_the_loaded_release(
    request_input: SuggestionInput,
) -> None:
    pipeline = FakePipeline()

    outcome = await CreateDraft(StaticReleaseSource(), pipeline).execute(request_input)

    assert outcome == EXAMPLE_DRAFT_READY
    assert pipeline.requests == [(request_input, EXAMPLE_RELEASE)]


async def test_without_a_loaded_release_nothing_is_computed() -> None:
    pipeline = FakePipeline()
    source = StaticReleaseSource(release=None)

    with pytest.raises(ReleaseNotLoadedError):
        await CreateAnalysis(source, pipeline).execute(REQUEST)
    with pytest.raises(ReleaseNotLoadedError):
        await CreateDraft(source, pipeline).execute(REQUEST)

    assert pipeline.requests == []


async def test_another_kb_version_is_refused_before_the_pipeline_runs() -> None:
    pipeline = FakePipeline()

    with pytest.raises(UnknownKbVersionError):
        await CreateAnalysis(StaticReleaseSource(), pipeline).execute(OTHER_KB)
    with pytest.raises(UnknownKbVersionError):
        await CreateDraft(StaticReleaseSource(), pipeline).execute(OTHER_KB)

    assert pipeline.requests == []

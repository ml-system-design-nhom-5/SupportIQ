"""Read the assets of a verified release and wire the pipeline that serves it (DATA-56, ARCH-21).

Every asset is read strictly, and a file that breaks its format stops startup (ERR-17). Reading
comes first and wiring second, so a release that fails creates nothing. The two
models load through a loader that the command passes in, because loading them needs torch,
which only the `torch` dependency group installs on Linux (ADR-0021, Python and dependencies,
statement 2).
"""

import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import httpx

from supportiq_ai_service.drafting import TokenPrices
from supportiq_ai_service.drafting.adapters.budgeted_draft_client import (
    BudgetedDraftWriter,
    RetryPolicy,
)
from supportiq_ai_service.drafting.adapters.gemini import GeminiClient, GeminiOptions
from supportiq_ai_service.drafting.adapters.prompt_files import (
    DraftingPrompts,
    read_drafting_prompts,
)
from supportiq_ai_service.intent import IntentClassifier
from supportiq_ai_service.intent.adapters.model_artifact import ModelArtifact, read_model_artifact
from supportiq_ai_service.platform import MILLISECONDS_PER_SECOND, EventRecorder
from supportiq_ai_service.platform.adapters.system_clock import SystemClock
from supportiq_ai_service.platform.settings import Settings
from supportiq_ai_service.release.manifest import VerifiedReleaseSource
from supportiq_ai_service.retrieval import KbDocument
from supportiq_ai_service.retrieval.adapters.in_memory_index import TextEncoder
from supportiq_ai_service.retrieval.adapters.index_file import (
    IndexConfiguration,
    read_index_configuration,
)
from supportiq_ai_service.retrieval.adapters.kb_file import read_kb_documents
from supportiq_ai_service.retrieval.adapters.release_kb import ReleaseKbDocuments
from supportiq_ai_service.retrieval.adapters.semantic_retriever import (
    SemanticRetriever,
    build_semantic_retriever,
)
from supportiq_ai_service.suggestions import PipelinePorts, PipelineValues, ReleasePipeline
from supportiq_ai_service.suggestions.adapters.mapping_file import read_document_intents
from supportiq_ai_service.suggestions.adapters.routing_file import read_routing_configuration
from supportiq_ai_service.suggestions.domain import DocumentIntents, RoutingConfiguration
from supportiq_ai_service.suggestions.domain.routing_rules import check_sensitive_intents


@dataclass(frozen=True, slots=True)
class ReleaseModels:
    """The two models of a release, loaded.

    Attributes:
        classifier: The intent model.
        encoder: The encoder of the retrieval index.
    """

    classifier: IntentClassifier
    encoder: TextEncoder


class ModelLoader(Protocol):
    """Load the two models of a release from their checked folders."""

    def __call__(
        self, artifact: ModelArtifact, index: IndexConfiguration, cpu_threads: int
    ) -> ReleaseModels:
        """Load the models.

        Args:
            artifact: The checked model artifact.
            index: The checked configuration of the index, with the folder of the encoder.
            cpu_threads: The CPU threads that the models use.

        Returns:
            The loaded models.

        Raises:
            ReleaseInvalidError: The model library cannot load a model of the release.
        """
        ...


@dataclass(frozen=True, slots=True)
class ReleaseAssets:
    """Every asset of a verified release, read and checked, with its models loaded.

    Attributes:
        kb_documents: The KB document versions of the release, possibly none.
        mapping: The document-to-intent mapping.
        routing: The routing configuration.
        prompts: The drafting prompts.
        models: The two models.
        retriever: The search over the index of the release.
    """

    kb_documents: tuple[KbDocument, ...]
    mapping: DocumentIntents
    routing: RoutingConfiguration
    prompts: DraftingPrompts
    models: ReleaseModels
    retriever: SemanticRetriever


@dataclass(frozen=True, slots=True)
class Timing:
    """The sources of time and randomness of the pipeline, which tests replace (TEST-14).

    Attributes:
        monotonic: A clock in seconds that never goes back.
        sleep: Waits a number of seconds, between two attempts of the LLM call.
        random: A number from 0 up to 1, for the jitter of the backoff (ERR-13).
    """

    monotonic: Callable[[], float]
    sleep: Callable[[float], None]
    random: Callable[[], float]


# The jitter comes from the system source, never from a seeded one.
SYSTEM_TIMING = Timing(time.monotonic, time.sleep, secrets.SystemRandom().random)


@dataclass(frozen=True, slots=True)
class ReleaseServices:
    """What the application serves from one release.

    Attributes:
        pipeline: The pipeline of `createAnalysis` and `createDraft`.
        kb_documents: The KB document versions of `getKbDocumentVersion`.
    """

    pipeline: ReleasePipeline
    kb_documents: ReleaseKbDocuments


def read_release_assets(
    source: VerifiedReleaseSource, settings: Settings, load_models: ModelLoader
) -> ReleaseAssets:
    """Read and check every asset of a verified release, then load its models.

    Args:
        source: The verified release.
        settings: The validated settings.
        load_models: The loader of the two models.

    Returns:
        The assets, ready to wire.

    Raises:
        ReleaseInvalidError: An asset breaks its format, names another version, or cannot be
            loaded, or the routing configuration names an intent that the model never outputs.
    """
    versions = source.current().versions
    artifact = read_model_artifact(source.asset_files("model"))
    kb_documents = read_kb_documents(source.asset_files("kb"))
    mapping = read_document_intents(
        source.asset_files("mapping"), versions.kb_version, kb_documents
    )
    routing = read_routing_configuration(source.asset_files("routing"), versions.model_version)
    check_sensitive_intents(routing, frozenset(artifact.labels))
    index = read_index_configuration(source.asset_files("index"), versions.kb_version)
    prompts = read_drafting_prompts(source.asset_files("prompts"))
    models = load_models(artifact, index, settings.model_cpu_threads)
    retriever = build_semantic_retriever(
        kb_documents, models.encoder, index, settings.retrieval_max_chunks_per_document
    )
    return ReleaseAssets(
        kb_documents=kb_documents,
        mapping=mapping,
        routing=routing,
        prompts=prompts,
        models=models,
        retriever=retriever,
    )


def build_release_services(
    assets: ReleaseAssets,
    settings: Settings,
    events: EventRecorder,
    egress_client: httpx.Client,
    timing: Timing,
) -> ReleaseServices:
    """Wire the pipeline of a release, with no I/O.

    Args:
        assets: The checked assets of the release.
        settings: The validated settings.
        events: Where events are recorded.
        egress_client: The one HTTP client of the egress allow-list (SEC-40).
        timing: The sources of time and randomness.

    Returns:
        The pipeline and the KB of the release.
    """
    gemini = GeminiClient(
        egress_client,
        GeminiOptions(
            model=settings.gemini_model,
            api_key=settings.gemini_api_key,
            max_output_tokens=settings.llm_max_output_tokens,
            temperature=settings.llm_temperature,
        ),
        assets.prompts,
        SystemClock(),
    )
    writer = BudgetedDraftWriter(
        gemini,
        RetryPolicy(
            budget_seconds=settings.llm_budget_ms / MILLISECONDS_PER_SECOND,
            attempt_timeout_seconds=settings.llm_attempt_timeout_ms / MILLISECONDS_PER_SECOND,
            max_attempts=settings.llm_max_attempts,
            backoff_base_seconds=settings.llm_backoff_base_ms / MILLISECONDS_PER_SECOND,
            backoff_max_seconds=settings.llm_backoff_max_ms / MILLISECONDS_PER_SECOND,
        ),
        timing.monotonic,
        timing.sleep,
        timing.random,
    )
    encoder = assets.models.encoder
    pipeline = ReleasePipeline(
        PipelinePorts(
            classifier=assets.models.classifier,
            search=assets.retriever,
            writer=writer,
            count_tokens=lambda text: len(encoder.token_spans(text)),
        ),
        PipelineValues(
            routing=assets.routing,
            mapping=assets.mapping,
            top_k_documents=settings.retrieval_top_k_documents,
            token_budget_tokens=settings.retrieval_token_budget_tokens,
            uncited_segment_max_chars=settings.grounding_uncited_segment_max_chars,
            prices=TokenPrices(
                input_micro_usd_per_million_tokens=settings.llm_input_price_micro_usd_per_million_tokens,
                output_micro_usd_per_million_tokens=settings.llm_output_price_micro_usd_per_million_tokens,
            ),
        ),
        events,
        timing.monotonic,
    )
    return ReleaseServices(pipeline=pipeline, kb_documents=ReleaseKbDocuments(assets.kb_documents))

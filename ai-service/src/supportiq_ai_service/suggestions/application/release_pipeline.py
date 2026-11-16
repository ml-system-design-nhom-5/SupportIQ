"""The pipeline of one release: classify, search, route, and draft when routing allows (ADR-0005).

It implements the `SuggestionPipeline` port. The model, the search, and the LLM block, so each
runs in a worker thread. The LLM is called only when routing recommends a draft; masking runs
before every call (SEC-06). A failure of the drafting step is an outcome, never an error: the
draft status is `llm_unavailable` and the reason code says which failure (contracts v1 design,
Reason codes). The authority flag comes only from routing, never from the drafting step.
Nothing of the message, the prompt, or the draft is logged (LOG-29).
"""

import asyncio
import dataclasses
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC

from supportiq_ai_service.drafting import (
    DraftReply,
    DraftRequest,
    DraftWriter,
    LlmCallError,
    LlmFailure,
    OrderFact,
    PolicySource,
    TokenPrices,
    TokenUsage,
    UnanswerableRequest,
)
from supportiq_ai_service.intent import IntentClassifier, IntentDistribution
from supportiq_ai_service.platform import MILLISECONDS_PER_SECOND, EventName, EventRecorder
from supportiq_ai_service.release import LoadedRelease
from supportiq_ai_service.retrieval import DocumentSearch
from supportiq_ai_service.suggestions.domain import (
    Analysis,
    AnalysisWarning,
    ConfidenceBand,
    DocumentIntents,
    DraftOutcome,
    DraftReady,
    IntentName,
    LlmUsage,
    MaskCounts,
    ModelIntent,
    NoDraft,
    NoDraftStatus,
    OrderFacts,
    OutcomeDetails,
    RankedDocument,
    ReasonCode,
    RoutingConfiguration,
    RoutingRecommendation,
    StaffIntent,
    StepLatencies,
    SuggestionInput,
)
from supportiq_ai_service.suggestions.domain.evidence import (
    NO_VALID_DOCUMENT,
    Evidence,
    Ranking,
    assess_evidence,
)
from supportiq_ai_service.suggestions.domain.grounding import DraftCheckError, check_draft
from supportiq_ai_service.suggestions.domain.masking import MaskedText, mask_personal_data
from supportiq_ai_service.suggestions.domain.routing_rules import (
    IN_SCOPE_INTENTS,
    IntentAssessment,
    assess_intent,
    ordered,
    requires_authority,
    route,
)
from supportiq_ai_service.suggestions.domain.usage import UsageOutOfRangeError, contract_usage

SIGNAL_DISAGREEMENT = ReasonCode("signal_disagreement")
MISSING_INFORMATION = ReasonCode("missing_information")
_NO_MASKS = MaskCounts(email=0, phone=0, card=0)
_INVALID_OUTPUT = ReasonCode(LlmFailure.INVALID_OUTPUT.value)


@dataclass(frozen=True, slots=True)
class PipelinePorts:
    """The adapters of the pipeline.

    Attributes:
        classifier: The intent model of the release.
        search: The search of the KB of the release.
        writer: The LLM step, within its budget.
        count_tokens: The number of tokens of a text, as the encoder counts them.
    """

    classifier: IntentClassifier
    search: DocumentSearch
    writer: DraftWriter
    count_tokens: Callable[[str], int]


@dataclass(frozen=True, slots=True)
class PipelineValues:
    """The values of the release and the settings that the pipeline reads.

    Attributes:
        routing: The routing configuration of the release.
        mapping: The document-to-intent mapping of the release.
        top_k_documents: The number of top documents (setting `retrieval_top_k_documents`).
        token_budget_tokens: The tokens of KB passages that a prompt may hold
            (`retrieval_token_budget_tokens`); the first passage always goes.
        uncited_segment_max_chars: The longest segment without a citation
            (`grounding_uncited_segment_max_chars`).
        prices: The prices of the tokens of the model in use.
    """

    routing: RoutingConfiguration
    mapping: DocumentIntents
    top_k_documents: int
    token_budget_tokens: int
    uncited_segment_max_chars: int
    prices: TokenPrices


@dataclass(frozen=True, slots=True)
class _Analyzed:
    analysis: Analysis
    evidence: Evidence
    authority_required: bool


@dataclass(frozen=True, slots=True)
class _Drafting:
    # What every outcome of the drafting step carries.
    analysis: Analysis
    masked: MaskedText
    started: float
    llm_started: float


class ReleasePipeline:
    """Implement the `SuggestionPipeline` port with the assets of one release."""

    def __init__(
        self,
        ports: PipelinePorts,
        values: PipelineValues,
        events: EventRecorder,
        monotonic: Callable[[], float],
    ) -> None:
        """Keep the adapters, the values, the event recorder, and the clock of latencies.

        Args:
            ports: The adapters of the pipeline.
            values: The values of the release and the settings.
            events: Where the pipeline records its events.
            monotonic: A clock in seconds that never goes back.
        """
        self._ports = ports
        self._values = values
        self._events = events
        self._monotonic = monotonic

    async def analyze(self, request: SuggestionInput, release: LoadedRelease) -> Analysis:
        """Run the pipeline up to routing, without the LLM.

        Args:
            request: The validated request.
            release: The loaded release.

        Returns:
            The analysis.
        """
        started = self._monotonic()
        analyzed = await self._analyzed(request, release, started)
        return analyzed.analysis

    async def draft(self, request: SuggestionInput, release: LoadedRelease) -> DraftOutcome:
        """Run the whole pipeline, with the LLM when routing recommends a draft.

        Args:
            request: The validated request.
            release: The loaded release.

        Returns:
            The draft outcome; a failure of the drafting step is an outcome.
        """
        started = self._monotonic()
        analyzed = await self._analyzed(request, release, started)
        analysis = analyzed.analysis
        recommendation = analysis.routing.recommendation
        if recommendation is not RoutingRecommendation.DRAFT:
            status = (
                NoDraftStatus.ESCALATION_RECOMMENDED
                if recommendation is RoutingRecommendation.ESCALATE
                else NoDraftStatus.ABSTAINED
            )
            return self._without_llm(analysis, status, started)
        return await self._drafted(request, analyzed, started)

    async def _drafted(
        self, request: SuggestionInput, analyzed: _Analyzed, started: float
    ) -> DraftOutcome:
        analysis = analyzed.analysis
        masked = self._masked(request.message)
        policy_sources = self._policy_sources(analyzed.evidence)
        draft_request = DraftRequest(
            message=masked.text,
            intent=analysis.intent.label,
            policy_sources=policy_sources,
            # Order facts are numbered after the policy sources, so every source ID is unique.
            order_facts=_order_facts(request.order_facts, first_source=len(policy_sources) + 1),
            requires_authority=analyzed.authority_required,
        )
        drafting = _Drafting(analysis, masked, started, self._monotonic())
        try:
            reply = await asyncio.to_thread(self._ports.writer.write, draft_request)
        except LlmCallError as error:
            return self._no_draft(
                drafting,
                NoDraftStatus.LLM_UNAVAILABLE,
                ReasonCode(error.failure.value),
                error.usage,
            )
        return self._checked(drafting, draft_request, reply)

    def _checked(
        self, drafting: _Drafting, draft_request: DraftRequest, reply: DraftReply
    ) -> DraftOutcome:
        if isinstance(reply, UnanswerableRequest):
            return self._no_draft(drafting, NoDraftStatus.ABSTAINED, NO_VALID_DOCUMENT, reply.usage)
        try:
            usage = contract_usage(reply.usage, self._values.prices)
            draft = check_draft(reply, draft_request, self._values.uncited_segment_max_chars)
        except UsageOutOfRangeError:
            return self._no_draft(drafting, NoDraftStatus.LLM_UNAVAILABLE, _INVALID_OUTPUT, None)
        except DraftCheckError as error:
            return self._no_draft(
                drafting, NoDraftStatus.LLM_UNAVAILABLE, error.reason_code, reply.usage
            )
        codes = (MISSING_INFORMATION,) if reply.is_clarification else ()
        return DraftReady(details=self._details(drafting, codes, usage), draft=draft)

    async def _analyzed(
        self, request: SuggestionInput, release: LoadedRelease, started: float
    ) -> _Analyzed:
        distribution = await asyncio.to_thread(self._ports.classifier.classify, request.message)
        matches = await asyncio.to_thread(self._ports.search.search, request.message)
        values = self._values
        intent = assess_intent(distribution, request.intent_override, values.routing)
        label = intent.intent.label
        evidence = assess_evidence(
            matches,
            request.as_of,
            Ranking(
                mapping=values.mapping,
                probability_of=_probability_of(distribution, request.intent_override),
                top_intent=label,
                rerank_weight=values.routing.rerank_weight,
                top_k=values.top_k_documents,
            ),
        )
        authority = requires_authority(
            request.message, distribution, request.intent_override, values.routing
        )
        routing = route(intent, evidence.reason_codes, authority_required=authority)
        warnings = (
            (AnalysisWarning(warning_id="warning-1", reason_code=SIGNAL_DISAGREEMENT),)
            if evidence.disagreement
            else ()
        )
        analysis_ms = self._elapsed_ms(started)
        analysis = Analysis(
            intent=_with_disagreement(intent, disagreement=evidence.disagreement),
            alternatives=intent.alternatives,
            is_in_scope=label in IN_SCOPE_INTENTS,
            documents=tuple(
                RankedDocument(
                    document_id=ranked.document.document_id,
                    version=ranked.document.version,
                    title=ranked.document.title,
                    policy_key=ranked.document.policy_key,
                    effective_start_at=ranked.document.effective_start_at,
                    effective_end_at=ranked.document.effective_end_at,
                    validity=ranked.validity,
                    rank=rank,
                    snippet=ranked.snippets[0],
                )
                for rank, ranked in enumerate(evidence.documents, start=1)
            ),
            routing=routing,
            warnings=warnings,
            versions=release.versions,
            step_latencies=StepLatencies(total_ms=analysis_ms, analysis_ms=analysis_ms),
        )
        return _Analyzed(analysis=analysis, evidence=evidence, authority_required=authority)

    def _masked(self, message: str) -> MaskedText:
        masked = mask_personal_data(message)
        for mask_type, count in dataclasses.asdict(masked.counts).items():
            if count:
                # The type and the number only: every mask means that pseudonymization missed a
                # value (SEC-06), and the value itself never reaches a log (LOG-29).
                self._events.record(
                    EventName.PERSONAL_DATA_MASKED, mask_type=mask_type, mask_count=count
                )
        return masked

    def _policy_sources(self, evidence: Evidence) -> tuple[PolicySource, ...]:
        sources: list[PolicySource] = []
        tokens = 0
        for ranked in evidence.valid_documents():
            for snippet in ranked.snippets:
                snippet_tokens = self._ports.count_tokens(snippet)
                if sources and tokens + snippet_tokens > self._values.token_budget_tokens:
                    continue
                tokens += snippet_tokens
                sources.append(
                    PolicySource(
                        source_id=f"S{len(sources) + 1}",
                        document_id=ranked.document.document_id,
                        version=ranked.document.version,
                        title=ranked.document.title,
                        snippet=snippet,
                    )
                )
        return tuple(sources)

    def _no_draft(
        self,
        drafting: _Drafting,
        status: NoDraftStatus,
        code: ReasonCode,
        usage: TokenUsage | None,
    ) -> NoDraft:
        # `llm_usage` is present whenever the LLM answered, also for an output that was refused,
        # unless the usage is beyond the caps of the contract (contracts v1 design, L1).
        llm_usage = None
        if usage is not None:
            try:
                llm_usage = contract_usage(usage, self._values.prices)
            except UsageOutOfRangeError:
                code = _INVALID_OUTPUT
        return NoDraft(details=self._details(drafting, (code,), llm_usage), status=status)

    def _details(
        self, drafting: _Drafting, codes: tuple[ReasonCode, ...], llm_usage: LlmUsage | None
    ) -> OutcomeDetails:
        analysis = drafting.analysis
        return OutcomeDetails(
            reason_codes=ordered(frozenset((*analysis.routing.reason_codes, *codes))),
            analysis=analysis,
            versions=analysis.versions,
            step_latencies=StepLatencies(
                total_ms=self._elapsed_ms(drafting.started),
                analysis_ms=analysis.step_latencies.analysis_ms,
                llm_ms=self._elapsed_ms(drafting.llm_started),
            ),
            mask_counts=drafting.masked.counts,
            llm_usage=llm_usage,
        )

    def _without_llm(self, analysis: Analysis, status: NoDraftStatus, started: float) -> NoDraft:
        details = OutcomeDetails(
            reason_codes=analysis.routing.reason_codes,
            analysis=analysis,
            versions=analysis.versions,
            step_latencies=StepLatencies(
                total_ms=self._elapsed_ms(started),
                analysis_ms=analysis.step_latencies.analysis_ms,
            ),
            mask_counts=_NO_MASKS,
        )
        return NoDraft(details=details, status=status)

    def _elapsed_ms(self, started: float) -> int:
        return round((self._monotonic() - started) * MILLISECONDS_PER_SECOND)


def _probability_of(
    distribution: IntentDistribution, override: IntentName | None
) -> Callable[[IntentName], float]:
    # A staff choice replaces the distribution (ADR-0005, statement 7).
    if override is not None:
        return lambda intent: 1.0 if intent == override else 0.0
    return distribution.probability_of


def _with_disagreement(
    intent: IntentAssessment, *, disagreement: bool
) -> ModelIntent | StaffIntent:
    # A disagreement lowers the band to `medium` at most (ADR-0005, statement 4).
    model = intent.intent
    if (
        disagreement
        and isinstance(model, ModelIntent)
        and model.confidence_band is ConfidenceBand.HIGH
    ):
        return dataclasses.replace(model, confidence_band=ConfidenceBand.MEDIUM)
    return model


def _order_facts(facts: OrderFacts | None, first_source: int) -> tuple[OrderFact, ...]:
    # The fields that the prompt needs, in the one text form that a draft repeats (SEC-05,
    # ADR-0014): a status as it is, and a time as its date in UTC. Amounts are left out, because
    # their minor units depend on the currency (contract `Money`) and no table of currencies is
    # part of a release yet (README.md, Known limits).
    if facts is None:
        return ()
    texts = (
        ("order_status", facts.order_status),
        ("shipment_status", facts.shipment_status),
        ("refund_status", facts.refund_status),
    )
    dates = (
        ("placed_at", facts.placed_at),
        ("estimated_delivery_at", facts.estimated_delivery_at),
        ("delivered_at", facts.delivered_at),
        ("refund_requested_at", facts.refund_requested_at),
    )
    values = [(field, value) for field, value in texts if value is not None] + [
        (field, moment.astimezone(UTC).date().isoformat())
        for field, moment in dates
        if moment is not None
    ]
    return tuple(
        OrderFact(source_id=f"S{first_source + index}", field=field, value=value)
        for index, (field, value) in enumerate(values)
    )

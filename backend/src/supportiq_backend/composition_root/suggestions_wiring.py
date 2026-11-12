"""The wiring of suggestions and pseudonymization: the ai-service client and the job queue."""

from dataclasses import dataclass

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from supportiq_backend.accounts import Authorizer
from supportiq_backend.audit.adapters.audit_log import PostgresAuditLog
from supportiq_backend.commerce.adapters.commerce_gateway import PostgresCommerceGateway
from supportiq_backend.commerce.adapters.customer_records import PostgresCustomerRecords
from supportiq_backend.composition_root.shared_ports import SharedPorts
from supportiq_backend.idempotency.adapters.idempotency_store import PostgresIdempotencyStore
from supportiq_backend.platform.adapters.database import SqlAlchemyTransactionRunner
from supportiq_backend.platform.settings import Settings
from supportiq_backend.pseudonymization import (
    KnownValueDetector,
    LiteralPlaceholderDetector,
    PatternDetector,
    PseudonymizationPorts,
    PseudonymizationStores,
    PseudonymizeMessage,
)
from supportiq_backend.pseudonymization.adapters.pseudonym_map_store import (
    PostgresPseudonymMapStore,
)
from supportiq_backend.suggestions import (
    ClaimLoop,
    ClaimStores,
    CreateSuggestion,
    CreateSuggestionPorts,
    CreateSuggestionStores,
    JobRunnerPorts,
    JobStores,
    QueueSettings,
    SuggestionJobRunner,
    SuggestionStarter,
    SuggestionStarterPorts,
)
from supportiq_backend.suggestions.adapters.ai_service_client import (
    AiServiceTimeouts,
    HttpAiService,
    create_ai_service_client,
)
from supportiq_backend.suggestions.adapters.suggestion_store import (
    PostgresSuggestionJobStore,
    PostgresSuggestionStore,
)
from supportiq_backend.tickets.adapters.console_store import PostgresTicketLinks
from supportiq_backend.tickets.api.console import render_created_suggestion


@dataclass(frozen=True, slots=True)
class SuggestionsWiring:
    """What suggestions gives the other features and the lifespan.

    Attributes:
        ai_client: The one HTTP client of ai-service, closed at shutdown (ARCH-24).
        ai_service: The `AiService` port.
        claim_loop: The claim loop of this replica, run by the lifespan.
        starter: Starts suggestions.
        create_suggestion: The use case of `createSuggestion`.
    """

    ai_client: httpx.AsyncClient
    ai_service: HttpAiService
    claim_loop: ClaimLoop
    starter: SuggestionStarter
    create_suggestion: CreateSuggestion


def to_queue_settings(settings: Settings) -> QueueSettings:
    """Collect the settings of the suggestion job queue (ADR-0011, item 7).

    Args:
        settings: The validated settings.

    Returns:
        The queue settings.
    """
    return QueueSettings(
        workers_per_replica=settings.suggestion_workers_per_replica,
        lease_ms=settings.suggestion_job_lease_ms,
        max_attempts=settings.suggestion_job_max_attempts,
        poll_ms=settings.suggestion_queue_poll_ms,
    )


def build_pseudonymization_stores(session: AsyncSession) -> PseudonymizationStores:
    """Build the stores of one pseudonymization run on one session.

    Args:
        session: The session of the transaction.

    Returns:
        The stores.
    """
    return PseudonymizationStores(
        pseudonyms=PostgresPseudonymMapStore(session),
        records=PostgresCustomerRecords(session),
        audit=PostgresAuditLog(session),
    )


def build_job_stores(session: AsyncSession) -> JobStores:
    """Build the stores of the transactions of a job on one session.

    Args:
        session: The session of the transaction.

    Returns:
        The stores.
    """
    links = PostgresTicketLinks(session)
    return JobStores(
        jobs=PostgresSuggestionJobStore(session),
        suggestions=PostgresSuggestionStore(session),
        tickets=links,
        authority=links,
        orders=PostgresCommerceGateway(session),
        audit=PostgresAuditLog(session),
    )


def build_claim_stores(session: AsyncSession) -> ClaimStores:
    """Build the store of a claim transaction on one session.

    Args:
        session: The session of the transaction.

    Returns:
        The stores.
    """
    return ClaimStores(jobs=PostgresSuggestionJobStore(session))


def build_create_suggestion_stores(session: AsyncSession) -> CreateSuggestionStores:
    """Build the stores of `createSuggestion` on one session.

    Args:
        session: The session of the transaction.

    Returns:
        The stores.
    """
    return CreateSuggestionStores(
        suggestions=PostgresSuggestionStore(session),
        links=PostgresTicketLinks(session),
        idempotency=PostgresIdempotencyStore(session),
        audit=PostgresAuditLog(session),
    )


def wire_suggestions(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    shared: SharedPorts,
    authorizer: Authorizer,
) -> SuggestionsWiring:
    """Create the ai-service client, pseudonymization, the claim loop, and the starter.

    Nothing here opens a connection: the client connects on the first call.

    Args:
        settings: The validated settings.
        session_factory: The session factory of the replicas.
        shared: The shared ports.
        authorizer: The role checks.

    Returns:
        The wiring.
    """
    ai_client = create_ai_service_client(
        str(settings.ai_service_base_url), settings.ai_service_token.get_secret_value()
    )
    ai_service = HttpAiService(
        ai_client,
        AiServiceTimeouts(
            analysis_ms=settings.ai_service_analysis_timeout_ms,
            draft_ms=settings.ai_service_draft_timeout_ms,
            read_ms=settings.ai_service_read_timeout_ms,
        ),
    )
    claim_loop = _build_claim_loop(session_factory, shared, ai_service, to_queue_settings(settings))
    starter = SuggestionStarter(
        SuggestionStarterPorts(
            clock=shared.clock,
            ids=shared.ids,
            traces=shared.traces,
            events=shared.events,
            queue=claim_loop,
        )
    )
    create_suggestion = _build_create_suggestion(session_factory, shared, authorizer, starter)
    return SuggestionsWiring(ai_client, ai_service, claim_loop, starter, create_suggestion)


def _build_claim_loop(
    session_factory: async_sessionmaker[AsyncSession],
    shared: SharedPorts,
    ai_service: HttpAiService,
    queue_settings: QueueSettings,
) -> ClaimLoop:
    runner = SuggestionJobRunner(
        SqlAlchemyTransactionRunner(session_factory, build_job_stores),
        JobRunnerPorts(
            pseudonymizer=_build_pseudonymizer(session_factory, shared),
            ai_service=ai_service,
            clock=shared.clock,
            ids=shared.ids,
            traces=shared.traces,
            events=shared.events,
            steps=shared.steps,
        ),
        queue_settings,
    )
    return ClaimLoop(
        SqlAlchemyTransactionRunner(session_factory, build_claim_stores),
        runner,
        queue_settings,
        shared.clock,
        shared.events,
    )


def _build_create_suggestion(
    session_factory: async_sessionmaker[AsyncSession],
    shared: SharedPorts,
    authorizer: Authorizer,
    starter: SuggestionStarter,
) -> CreateSuggestion:
    return CreateSuggestion(
        SqlAlchemyTransactionRunner(session_factory, build_create_suggestion_stores),
        CreateSuggestionPorts(
            authorizer=authorizer,
            guard=shared.guard,
            starter=starter,
            clock=shared.clock,
            ids=shared.ids,
            traces=shared.traces,
            events=shared.events,
        ),
        render_created_suggestion,
    )


def _build_pseudonymizer(
    session_factory: async_sessionmaker[AsyncSession], shared: SharedPorts
) -> PseudonymizeMessage:
    # The detectors of ADR-0010 in the order of its steps. The named-entity detector of step 4
    # joins them with ADR-0017, as one more `Detector`.
    return PseudonymizeMessage(
        SqlAlchemyTransactionRunner(session_factory, build_pseudonymization_stores),
        PseudonymizationPorts(
            detectors=(LiteralPlaceholderDetector(), KnownValueDetector(), PatternDetector()),
            clock=shared.clock,
            ids=shared.ids,
            traces=shared.traces,
            events=shared.events,
            steps=shared.steps,
        ),
    )

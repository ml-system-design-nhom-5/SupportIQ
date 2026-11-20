"""The wiring of suggestions and pseudonymization: the ai-service client, the queue, and reads."""

import functools
from dataclasses import dataclass

import httpx
from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.accounts import Authorizer
from app.audit.adapters.audit_log import PostgresAuditLog
from app.commerce.adapters.commerce_gateway import PostgresCommerceGateway
from app.commerce.adapters.customer_records import PostgresCustomerRecords
from app.composition_root.accounts_wiring import AccountsWiring
from app.composition_root.shared_ports import SharedPorts
from app.idempotency.adapters.idempotency_store import PostgresIdempotencyStore
from app.platform.adapters.database import SqlAlchemyTransactionRunner
from app.platform.settings import Settings
from app.pseudonymization import (
    KnownValueDetector,
    LiteralPlaceholderDetector,
    PatternDetector,
    PseudonymizationPorts,
    PseudonymizationStores,
    PseudonymizeMessage,
)
from app.pseudonymization.adapters.named_entity_detector import (
    SpacyNamedEntityDetector,
)
from app.pseudonymization.adapters.pseudonym_map_store import (
    PostgresPseudonymMapStore,
)
from app.suggestions import (
    AiServiceReadPorts,
    ClaimLoop,
    ClaimStores,
    CreateSuggestion,
    CreateSuggestionPorts,
    CreateSuggestionStores,
    GetAdminVersions,
    GetConsoleKbDocumentVersion,
    JobRunnerPorts,
    JobStores,
    ProgressSignals,
    ProgressStores,
    QueueSettings,
    StreamSettings,
    SuggestionJobRunner,
    SuggestionStarter,
    SuggestionStarterPorts,
    WatchProgressPorts,
    WatchSuggestionProgress,
)
from app.suggestions.adapters.ai_service_client import (
    AiServiceTimeouts,
    HttpAiService,
    create_ai_service_client,
)
from app.suggestions.adapters.suggestion_store import (
    PostgresSuggestionJobStore,
    PostgresSuggestionStore,
)
from app.suggestions.api.admin import AdminVersionsRoutes, build_admin_versions_router
from app.suggestions.api.console import (
    ConsoleKbDocumentRoutes,
    build_console_kb_documents_router,
)
from app.suggestions.api.suggestion_events import (
    SuggestionEventsRoutes,
    build_suggestion_events_router,
)
from app.tickets.adapters.console_store import PostgresTicketLinks
from app.tickets.api.console import render_created_suggestion


@dataclass(frozen=True, slots=True)
class SuggestionsWiring:
    """What suggestions gives the other features and the lifespan.

    Attributes:
        ai_client: The one HTTP client of ai-service, closed at shutdown (ARCH-24).
        ai_service: The `AiService` port.
        claim_loop: The claim loop of this replica, run by the lifespan.
        starter: Starts suggestions.
        create_suggestion: The use case of `createSuggestion`.
        routers: The routers of the console's KB document read, of the suggestion progress
            stream, and of the versions in use.
    """

    ai_client: httpx.AsyncClient
    ai_service: HttpAiService
    claim_loop: ClaimLoop
    starter: SuggestionStarter
    create_suggestion: CreateSuggestion
    routers: tuple[APIRouter, ...]


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


def build_progress_stores(session: AsyncSession) -> ProgressStores:
    """Build the stores of the read transaction of a stream on one session.

    Args:
        session: The session of the transaction.

    Returns:
        The stores.
    """
    return ProgressStores(
        tickets=PostgresTicketLinks(session), suggestions=PostgresSuggestionStore(session)
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
    accounts: AccountsWiring,
    ai_service_transport: httpx.AsyncBaseTransport | None,
) -> SuggestionsWiring:
    """Create the ai-service client, pseudonymization, the claim loop, the starter, and reads.

    Nothing here opens a connection: the client connects on the first call.

    Args:
        settings: The validated settings.
        session_factory: The session factory of the replicas.
        shared: The shared ports.
        accounts: The role checks and the session dependency.
        ai_service_transport: The transport of the ai-service client; None for the network.

    Returns:
        The wiring.
    """
    ai_client = create_ai_service_client(
        str(settings.ai_service_base_url),
        settings.ai_service_token.get_secret_value(),
        transport=ai_service_transport,
    )
    ai_service = HttpAiService(
        ai_client,
        AiServiceTimeouts(
            analysis_ms=settings.ai_service_analysis_timeout_ms,
            draft_ms=settings.ai_service_draft_timeout_ms,
            read_ms=settings.ai_service_read_timeout_ms,
        ),
    )
    signals = ProgressSignals()
    claim_loop = _build_claim_loop(
        session_factory, shared, ai_service, to_queue_settings(settings), signals
    )
    starter = SuggestionStarter(
        SuggestionStarterPorts(
            clock=shared.clock,
            ids=shared.ids,
            traces=shared.traces,
            events=shared.events,
            queue=claim_loop,
            progress=signals,
        )
    )
    watch_progress = WatchSuggestionProgress(
        SqlAlchemyTransactionRunner(session_factory, build_progress_stores),
        WatchProgressPorts(
            authorizer=accounts.authorizer,
            signals=signals,
            clock=shared.clock,
            events=shared.events,
        ),
        StreamSettings(
            poll_ms=settings.suggestion_events_poll_ms, max_ms=settings.suggestion_events_max_ms
        ),
    )
    create_suggestion = _build_create_suggestion(
        session_factory, shared, accounts.authorizer, starter
    )
    return SuggestionsWiring(
        ai_client,
        ai_service,
        claim_loop,
        starter,
        create_suggestion,
        routers=(
            *_build_read_routers(settings, shared, accounts, ai_service),
            build_suggestion_events_router(
                SuggestionEventsRoutes(
                    watch_progress=watch_progress, current_session=accounts.current_session
                )
            ),
        ),
    )


def _build_claim_loop(
    session_factory: async_sessionmaker[AsyncSession],
    shared: SharedPorts,
    ai_service: HttpAiService,
    queue_settings: QueueSettings,
    signals: ProgressSignals,
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
            progress=signals,
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


def _build_read_routers(
    settings: Settings, shared: SharedPorts, accounts: AccountsWiring, ai_service: HttpAiService
) -> tuple[APIRouter, ...]:
    ports = AiServiceReadPorts(
        authorizer=accounts.authorizer,
        ai_service=ai_service,
        events=shared.events,
        steps=shared.steps,
    )
    return (
        build_console_kb_documents_router(
            ConsoleKbDocumentRoutes(
                get_document_version=GetConsoleKbDocumentVersion(ports),
                current_session=accounts.current_session,
            )
        ),
        build_admin_versions_router(
            AdminVersionsRoutes(
                get_versions=GetAdminVersions(ports, settings.backend_build_version),
                current_session=accounts.current_session,
            )
        ),
    )


@functools.cache
def load_named_entity_detector() -> SpacyNamedEntityDetector:
    """Load the named-entity model once per process.

    The model adds about 40 MiB (backend ticket workflow design, Choice 1), so every app of a
    process, such as those that the tests create, shares one detector, which only reads it.

    Returns:
        The detector.

    Raises:
        NamedEntityModelMissingError: The model is not installed (ERR-17).
    """
    return SpacyNamedEntityDetector()


def _build_pseudonymizer(
    session_factory: async_sessionmaker[AsyncSession], shared: SharedPorts
) -> PseudonymizeMessage:
    # The detectors of ADR-0010 in the order of its steps.
    return PseudonymizeMessage(
        SqlAlchemyTransactionRunner(session_factory, build_pseudonymization_stores),
        PseudonymizationPorts(
            detectors=(
                LiteralPlaceholderDetector(),
                KnownValueDetector(),
                PatternDetector(),
                load_named_entity_detector(),
            ),
            clock=shared.clock,
            ids=shared.ids,
            traces=shared.traces,
            events=shared.events,
            steps=shared.steps,
        ),
    )

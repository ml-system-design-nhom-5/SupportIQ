"""Run one claimed suggestion job (backend ticket workflow design, Suggestions and the queue).

Pseudonymization comes first, in its own short transaction, so nothing leaves backend unless
it succeeded (SEC-36). No transaction stays open while backend waits for ai-service. Each
result is stored in its own transaction, which first locks the ticket and the job and checks
that the attempt and the suggestion are still current; otherwise the result is discarded
(ERR-22).
"""

import asyncio
from dataclasses import dataclass

from app.audit import (
    AuditEntry,
    AuditEntryId,
    AuditEventType,
    AuditLog,
    AuditTicketId,
)
from app.commerce import CommerceGateway, Order
from app.platform import (
    Clock,
    EventName,
    EventRecorder,
    IdGenerator,
    SpanName,
    StepTracer,
    TraceContext,
    TransactionRunner,
)
from app.pseudonymization import (
    MapTicketId,
    MessageToPseudonymize,
    PseudonymizationError,
)
from app.suggestions.application.ai_service_failures import (
    AiServiceOperation,
    record_ai_service_failure,
)
from app.suggestions.domain import (
    AiReasonCode,
    AiService,
    AiServiceUnavailableError,
    ClaimedJob,
    MessagePseudonymizer,
    PartCompletion,
    ProgressNotifier,
    QueueSettings,
    ReceivedDraftOutcome,
    Suggestion,
    SuggestionJobStore,
    SuggestionPart,
    SuggestionRequest,
    SuggestionStore,
    SuggestionTickets,
    TicketAuthority,
    TicketMessage,
    build_analysis_completion,
    build_draft_completion,
    build_embedded_analysis_completion,
    build_part_audit_data,
    build_suggestion_request,
    build_unavailable_completion,
    read_cited_facts,
)


@dataclass(frozen=True, slots=True)
class JobStores:
    """The stores of the transactions of a job.

    Attributes:
        jobs: The jobs and the parts they complete.
        suggestions: The suggestions.
        tickets: The ticket rows.
        authority: The authority flag.
        orders: The commerce orders, read-only.
        audit: The audit log.
    """

    jobs: SuggestionJobStore
    suggestions: SuggestionStore
    tickets: SuggestionTickets
    authority: TicketAuthority
    orders: CommerceGateway
    audit: AuditLog


@dataclass(frozen=True, slots=True)
class JobRunnerPorts:
    """The ports of the job runner besides its transactions.

    Attributes:
        pseudonymizer: The first function of pseudonymization.
        ai_service: The client of ai-service.
        clock: The clock.
        ids: Generates the IDs of audit log entries.
        traces: Tells the trace of the job.
        events: Where events are recorded.
        steps: Runs the job in its span.
        progress: The suggestion progress streams of this replica.
    """

    pseudonymizer: MessagePseudonymizer
    ai_service: AiService
    clock: Clock
    ids: IdGenerator
    traces: TraceContext
    events: EventRecorder
    steps: StepTracer
    progress: ProgressNotifier


@dataclass(frozen=True, slots=True, repr=False)
class _JobInput:
    suggestion: Suggestion
    ticket: TicketMessage
    order: Order | None
    is_current: bool


class SuggestionJobRunner:
    """Pseudonymize, call ai-service, and store each result of one claimed job."""

    def __init__(
        self,
        transactions: TransactionRunner[JobStores],
        ports: JobRunnerPorts,
        settings: QueueSettings,
    ) -> None:
        """Keep the dependencies.

        Args:
            transactions: Opens the transactions of a job.
            ports: The ports besides the stores.
            settings: The queue settings, for the attempt limit.
        """
        self._transactions = transactions
        self._ports = ports
        self._settings = settings

    async def run(self, job: ClaimedJob) -> None:
        """Run a job to its end, or leave it to its lease after a storage error.

        Args:
            job: The claimed job.

        Raises:
            DatabaseUnavailableError: A storage error; the job is claimed again after its
                lease, and the next attempt computes the same results.
        """
        job_input = await self._load_input(job)
        if job_input is None:
            await self._finish(job)
            return
        with self._ports.steps.background_step(
            SpanName.RUN_SUGGESTION_JOB, job_input.suggestion.trace_id
        ):
            self._ports.steps.record_ticket(job.ticket_id)
            await self._run_claimed(job, job_input)

    async def _run_claimed(self, job: ClaimedJob, job_input: _JobInput) -> None:
        if job.attempt_number > self._settings.max_attempts:
            await self._end_out_of_attempts(job)
            return
        if not job_input.is_current:
            await self._finish(job)
            return
        request = await self._pseudonymize(job, job_input)
        if request is None or not await self._save_request(job, request):
            return
        received_draft = await self._call_ai_service(job, job_input.suggestion, request)
        await self._store_draft(job, received_draft)

    async def _load_input(self, job: ClaimedJob) -> _JobInput | None:
        async with self._transactions.begin() as transaction:
            stores = transaction.stores
            suggestion = await stores.suggestions.load_suggestion(job.suggestion_id)
            ticket = await stores.tickets.load_ticket_message(job.ticket_id)
            if suggestion is None or ticket is None:
                return None
            locked = await stores.tickets.lock_ticket(job.ticket_id)
            is_current = locked is not None and locked.current_suggestion_id == job.suggestion_id
            order = (
                None
                if ticket.order_id is None
                else await stores.orders.load_order(ticket.customer_id, ticket.order_id)
            )
        return _JobInput(suggestion, ticket, order, is_current)

    async def _pseudonymize(
        self, job: ClaimedJob, job_input: _JobInput
    ) -> SuggestionRequest | None:
        ticket = job_input.ticket
        try:
            text = await self._ports.pseudonymizer.pseudonymize(
                MessageToPseudonymize(
                    MapTicketId(ticket.ticket_id),
                    ticket.message,
                    ticket.customer_id,
                    ticket.order_id,
                )
            )
        except PseudonymizationError:
            # Fail closed: both parts end unavailable and nothing is sent (SEC-36).
            await self._end_unavailable(job, AiReasonCode.PSEUDONYMIZATION_FAILED)
            return None
        return build_suggestion_request(job_input.suggestion, ticket, text, job_input.order)

    async def _save_request(self, job: ClaimedJob, request: SuggestionRequest) -> bool:
        async with self._transactions.begin() as transaction:
            stores = transaction.stores
            if not await self._holds(stores, job):
                return False
            await stores.jobs.save_request(job.suggestion_id, request)
            await transaction.commit()
        return True

    async def _call_ai_service(
        self, job: ClaimedJob, suggestion: Suggestion, request: SuggestionRequest
    ) -> ReceivedDraftOutcome | None:
        # With an intent override, only the draft call runs: its response carries the analysis
        # computed with the staff-chosen intent (contracts v1 design).
        if suggestion.intent_override is not None:
            return await self._draft(job, request)
        async with asyncio.TaskGroup() as group:
            group.create_task(self._analyze_and_store(job, request))
            draft = group.create_task(self._draft(job, request))
        return draft.result()

    async def _analyze_and_store(self, job: ClaimedJob, request: SuggestionRequest) -> None:
        with self._ports.steps.step(SpanName.CALL_AI_SERVICE):
            self._ports.steps.record_ai_service_endpoint(AiServiceOperation.CREATE_ANALYSIS)
            try:
                received = await self._ports.ai_service.analyze(request)
            except AiServiceUnavailableError as error:
                # The draft response may still carry the analysis, so the part stays pending.
                self._record_call_failure(job, AiServiceOperation.CREATE_ANALYSIS, error)
                return
        self._ports.events.record(
            EventName.AI_SERVICE_CALLED,
            ticket_id=job.ticket_id,
            suggestion_id=job.suggestion_id,
            ai_service_operation=AiServiceOperation.CREATE_ANALYSIS.value,
        )
        await self._store(job, (build_analysis_completion(received, self._ports.clock.now()),))

    async def _draft(
        self, job: ClaimedJob, request: SuggestionRequest
    ) -> ReceivedDraftOutcome | None:
        with self._ports.steps.step(SpanName.CALL_AI_SERVICE):
            self._ports.steps.record_ai_service_endpoint(AiServiceOperation.CREATE_DRAFT)
            try:
                received = await self._ports.ai_service.draft(request)
                # Only the check matters here: a draft that cites an order field the request
                # did not carry is a response outside the contract.
                read_cited_facts(received.outcome, request.order_context)
            except AiServiceUnavailableError as error:
                self._record_call_failure(job, AiServiceOperation.CREATE_DRAFT, error)
                return None
        return received

    async def _store_draft(self, job: ClaimedJob, received: ReceivedDraftOutcome | None) -> None:
        now = self._ports.clock.now()
        if received is None:
            await self._end_unavailable(job, AiReasonCode.AI_SERVICE_UNAVAILABLE)
            return
        self._ports.events.record(
            EventName.AI_SERVICE_CALLED,
            ticket_id=job.ticket_id,
            suggestion_id=job.suggestion_id,
            ai_service_operation=AiServiceOperation.CREATE_DRAFT.value,
        )
        completions = (
            build_embedded_analysis_completion(received, now),
            build_draft_completion(received, now),
        )
        if await self._store_and_finish(job, completions):
            self._ports.events.record(
                EventName.SUGGESTION_COMPLETED,
                ticket_id=job.ticket_id,
                suggestion_id=job.suggestion_id,
                draft_status=completions[1].status.value,
            )

    async def _end_unavailable(self, job: ClaimedJob, reason_code: AiReasonCode) -> None:
        now = self._ports.clock.now()
        completions = tuple(
            build_unavailable_completion(part, reason_code, now) for part in SuggestionPart
        )
        if await self._store_and_finish(job, completions):
            self._ports.events.record(
                EventName.TICKET_MANUAL_HANDLING_STARTED,
                ticket_id=job.ticket_id,
                suggestion_id=job.suggestion_id,
                reason_code=reason_code.value,
            )

    async def _end_out_of_attempts(self, job: ClaimedJob) -> None:
        self._ports.events.record(
            EventName.SUGGESTION_JOB_LEASE_EXPIRED,
            ticket_id=job.ticket_id,
            suggestion_id=job.suggestion_id,
            attempt_number=job.attempt_number,
        )
        await self._end_unavailable(job, AiReasonCode.AI_SERVICE_UNAVAILABLE)

    async def _store(self, job: ClaimedJob, completions: tuple[PartCompletion, ...]) -> bool:
        async with self._transactions.begin() as transaction:
            if not await self._store_parts(transaction.stores, job, completions):
                return False
            await transaction.commit()
        self._ports.progress.notify_progress(job.ticket_id)
        return True

    async def _store_and_finish(
        self, job: ClaimedJob, completions: tuple[PartCompletion, ...]
    ) -> bool:
        # The last results and the end of the job commit together, so a job is done only
        # when no part of its suggestion is pending.
        async with self._transactions.begin() as transaction:
            stores = transaction.stores
            if not await self._store_parts(stores, job, completions):
                return False
            await stores.jobs.finish_job(job.suggestion_id, self._ports.clock.now())
            await transaction.commit()
        self._ports.progress.notify_progress(job.ticket_id)
        return True

    async def _store_parts(
        self, stores: JobStores, job: ClaimedJob, completions: tuple[PartCompletion, ...]
    ) -> bool:
        if not await self._holds(stores, job):
            return False
        for completion in completions:
            if await stores.jobs.complete_part(job.suggestion_id, completion):
                await self._record_completion(stores, job, completion)
        return True

    async def _record_completion(
        self, stores: JobStores, job: ClaimedJob, completion: PartCompletion
    ) -> None:
        await stores.audit.append(
            AuditEntry(
                entry_id=AuditEntryId(self._ports.ids.generate()),
                occurred_at=completion.completed_at,
                event_type=AuditEventType.SUGGESTION_PART_COMPLETED,
                actor_account_id=None,
                ticket_id=AuditTicketId(job.ticket_id),
                trace_id=self._ports.traces.current_trace_id(),
                data=build_part_audit_data(job.suggestion_id, completion),
            )
        )
        # The flag is set in the transaction that stores the result, and never cleared (FR-06).
        if completion.is_authority_required:
            await stores.authority.set_authority_required(job.ticket_id)

    async def _holds(self, stores: JobStores, job: ClaimedJob) -> bool:
        # The ticket row first, as every ticket action locks it first, so two transactions on
        # one ticket always take their locks in the same order.
        ticket = await stores.tickets.lock_ticket(job.ticket_id)
        locked_job = await stores.jobs.lock_job(job.suggestion_id)
        return (
            ticket is not None
            and ticket.current_suggestion_id == job.suggestion_id
            and locked_job is not None
            and locked_job.is_held_by(job)
        )

    async def _finish(self, job: ClaimedJob) -> None:
        async with self._transactions.begin() as transaction:
            locked_job = await transaction.stores.jobs.lock_job(job.suggestion_id)
            if locked_job is None or not locked_job.is_held_by(job):
                return
            await transaction.stores.jobs.finish_job(job.suggestion_id, self._ports.clock.now())
            await transaction.commit()

    def _record_call_failure(
        self, job: ClaimedJob, operation: AiServiceOperation, error: AiServiceUnavailableError
    ) -> None:
        record_ai_service_failure(
            self._ports.events,
            operation,
            error,
            ticket_id=job.ticket_id,
            suggestion_id=job.suggestion_id,
        )

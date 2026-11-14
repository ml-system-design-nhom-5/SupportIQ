"""Reading a ticket whose stored suggestion no longer matches the contract (ERR-05, LOG-17).

Backend stores only results that matched the contract, so a stored result that no longer
parses is a defect of backend, not a failure of ai-service: `getConsoleTicket` answers `500`,
logged once as `request.failed`. The suggestion is inserted as the owner, in the form that the
claim loop stores (TEST-18).
"""

from http import HTTPStatus

import pytest

from supportiq_backend.platform import EventName
from tests.integration.application import RunningBackend
from tests.integration.builders import DatabaseBuilder
from tests.integration.database import WorkerDatabase
from tests.integration.suggestions.read_requests import problem_example, problem_of
from tests.integration.tickets.console_requests import (
    PartSpec,
    SuggestionSpec,
    insert_suggestion,
    open_ticket,
    ready_analysis,
    sent_request,
    sign_in_as_support,
    ticket_path,
)

pytestmark = pytest.mark.anyio

# A stored analysis with a boolean as text, which strict parsing refuses.
ANALYSIS_OUTSIDE_THE_CONTRACT = SuggestionSpec(
    analysis=PartSpec("ready", ready_analysis() | {"is_in_scope": "yes"}), request=sent_request()
)


async def test_a_stored_result_outside_the_contract_is_500_logged_once_as_a_failed_request(
    backend: RunningBackend, worker_database: WorkerDatabase, builder: DatabaseBuilder
) -> None:
    headers = (await sign_in_as_support(builder)).headers
    ticket = await open_ticket(builder)
    await insert_suggestion(
        worker_database, builder, ticket.ticket_id, ANALYSIS_OUTSIDE_THE_CONTRACT
    )

    response = await backend.client.get(ticket_path(ticket.ticket_id), headers=headers)

    (failure,) = backend.events.of(EventName.REQUEST_FAILED)
    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert problem_of(response) == problem_example("internal-error")
    assert failure.attributes == {"error_type": "AiServiceContractError"}
    assert backend.events.of(EventName.DATABASE_CALL_FAILED) == ()

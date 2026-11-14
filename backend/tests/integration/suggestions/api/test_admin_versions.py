"""Reading the versions in use over HTTP (`getAdminVersions`, ADR-0012, SEC-41).

Only an admin reads them. When ai-service cannot answer, the response is still `200`, with
`ai_service_status` `unavailable` and only the build version of backend.
"""

from http import HTTPStatus

import pytest

from supportiq_backend.platform import EventName
from tests.integration.ai_service_doubles import (
    FakeAiService,
    read_example,
    refuse_connection,
    serve_examples,
)
from tests.integration.application import build_settings, running_client
from tests.integration.builders import DatabaseBuilder
from tests.integration.database import WorkerDatabase
from tests.integration.suggestions.api.read_requests import (
    SignIn,
    problem_example,
    problem_of,
    sign_in_as_admin,
    sign_in_as_customer,
    sign_in_as_manager,
    sign_in_as_staff,
)
from tests.unit.platform.fakes import FakeClock, RecordingEventRecorder

pytestmark = pytest.mark.anyio

ADMIN_VERSIONS = "/v1/admin/versions"
ASSET_VERSIONS_PATH = "/v1/asset-versions"
# The build version of the examples of `getAdminVersions`.
BUILD_VERSION = "880b33a"


async def test_an_admin_gets_the_versions_of_backend_and_of_ai_service(
    worker_database: WorkerDatabase, builder: DatabaseBuilder
) -> None:
    ai_service = FakeAiService(serve_examples)
    headers = await sign_in_as_admin(builder)
    settings = build_settings(worker_database, backend_build_version=BUILD_VERSION)

    async with running_client(
        settings, RecordingEventRecorder(), FakeClock(), ai_service=ai_service
    ) as client:
        response = await client.get(ADMIN_VERSIONS, headers=headers)

    assert response.status_code == HTTPStatus.OK
    assert response.headers["content-type"] == "application/json"
    assert response.json() == read_example("getAdminVersions/ai-service-available.json")
    assert ai_service.paths() == [ASSET_VERSIONS_PATH]


async def test_an_admin_gets_only_the_build_version_while_ai_service_refuses(
    worker_database: WorkerDatabase, builder: DatabaseBuilder
) -> None:
    events = RecordingEventRecorder()
    headers = await sign_in_as_admin(builder)
    settings = build_settings(worker_database, backend_build_version=BUILD_VERSION)

    async with running_client(
        settings, events, FakeClock(), ai_service=FakeAiService(refuse_connection)
    ) as client:
        response = await client.get(ADMIN_VERSIONS, headers=headers)

    (failure,) = events.of(EventName.AI_SERVICE_CALL_FAILED)
    assert response.status_code == HTTPStatus.OK
    assert response.json() == read_example("getAdminVersions/ai-service-unavailable.json")
    assert failure.attributes == {"ai_service_operation": "getAssetVersions"}
    assert events.of(EventName.DATABASE_CALL_FAILED) == ()


@pytest.mark.parametrize("sign_in", [sign_in_as_staff, sign_in_as_manager, sign_in_as_customer])
async def test_every_other_role_gets_403_and_ai_service_is_not_read(
    worker_database: WorkerDatabase, builder: DatabaseBuilder, sign_in: SignIn
) -> None:
    ai_service = FakeAiService(serve_examples)
    events = RecordingEventRecorder()
    headers = await sign_in(builder)

    async with running_client(
        build_settings(worker_database), events, FakeClock(), ai_service=ai_service
    ) as client:
        response = await client.get(ADMIN_VERSIONS, headers=headers)

    (denied,) = events.of(EventName.PERMISSION_DENIED)
    assert response.status_code == HTTPStatus.FORBIDDEN
    assert problem_of(response) == problem_example("forbidden-role")
    assert denied.attributes["operation_id"] == "getAdminVersions"
    assert ai_service.requests == []

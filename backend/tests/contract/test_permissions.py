"""Every operation against all four roles, from the roles the contract names (SEC-16)."""

from dataclasses import replace
from http import HTTPStatus

import pytest
from schemathesis import BaseSchema

from app.accounts import PasswordHash
from app.platform import EventName
from tests.contract.calls import ROLES, World, build_world, send, valid_calls
from tests.contract.documented import list_operations
from tests.integration.application import RunningBackend
from tests.integration.builders import DatabaseBuilder

pytestmark = pytest.mark.anyio

OPERATIONS_WITH_ROLES = (
    "getCurrentSession",
    "changeOwnPassword",
    "deleteCurrentSession",
    "listShopProducts",
    "getShopProduct",
    "listShopOrders",
    "getShopOrder",
    "listShopTickets",
    "createShopTicket",
    "getShopTicket",
    "listConsoleTickets",
    "getConsoleTicket",
    "recordTicketView",
    "createSuggestion",
    "createReplyProposal",
    "sendReply",
    "createEscalation",
    "getSuggestionEvents",
    "getConsoleKbDocumentVersion",
    "getConsoleReport",
    "listAdminAccounts",
    "createAdminAccount",
    "changeAccountRole",
    "changeAccountStatus",
    "resetAccountPassword",
    "getAdminVersions",
)
SHOP_OPERATIONS = tuple(name for name in OPERATIONS_WITH_ROLES if "Shop" in name)
ADMIN_OPERATIONS = (
    *(name for name in OPERATIONS_WITH_ROLES if "Account" in name),
    "getAdminVersions",
)
# The console operations of staff alone: a manager sends replies instead (FR-06).
STAFF_OPERATIONS = ("createReplyProposal", "createEscalation")
# The console operations of managers alone (ADR-0012).
MANAGER_OPERATIONS = ("getConsoleReport",)
# The console operations that both support roles call (contracts v1 design, permission table).
SUPPORT_OPERATIONS = (
    "listConsoleTickets",
    "getConsoleTicket",
    "recordTicketView",
    "createSuggestion",
    "sendReply",
    "getSuggestionEvents",
    "getConsoleKbDocumentVersion",
)


@pytest.fixture
async def world(builder: DatabaseBuilder, known_password_hash: PasswordHash) -> World:
    return await build_world(builder, known_password_hash)


def roles_of(contract: BaseSchema, operation_id: str) -> tuple[str, ...]:
    (operation,) = (
        operation
        for operation in list_operations(contract)
        if operation.operation_id == operation_id
    )
    return operation.roles


def test_the_operations_of_the_table_are_the_operations_with_roles(contract: BaseSchema) -> None:
    named = {operation.operation_id for operation in list_operations(contract) if operation.roles}

    assert named == set(OPERATIONS_WITH_ROLES)


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("operation_id", OPERATIONS_WITH_ROLES)
async def test_each_role_reaches_exactly_the_operations_of_the_contract(
    contract: BaseSchema,
    backend: RunningBackend,
    world: World,
    operation_id: str,
    role: str,
) -> None:
    is_allowed = role in roles_of(contract, operation_id)
    call = replace(valid_calls(world)[operation_id], role=role)

    response = await send(backend.client, call, world)

    assert (response.status_code != HTTPStatus.FORBIDDEN) is is_allowed
    assert (EventName.PERMISSION_DENIED in backend.events.names()) is not is_allowed


@pytest.mark.parametrize("operation_id", SHOP_OPERATIONS)
def test_only_a_customer_calls_a_shop_operation(contract: BaseSchema, operation_id: str) -> None:
    assert roles_of(contract, operation_id) == ("customer",)


@pytest.mark.parametrize("operation_id", ADMIN_OPERATIONS)
def test_only_an_admin_calls_an_admin_operation(contract: BaseSchema, operation_id: str) -> None:
    assert roles_of(contract, operation_id) == ("admin",)


@pytest.mark.parametrize("operation_id", STAFF_OPERATIONS)
def test_only_staff_call_a_staff_operation(contract: BaseSchema, operation_id: str) -> None:
    assert roles_of(contract, operation_id) == ("staff",)


@pytest.mark.parametrize("operation_id", MANAGER_OPERATIONS)
def test_only_a_manager_calls_a_manager_operation(contract: BaseSchema, operation_id: str) -> None:
    assert roles_of(contract, operation_id) == ("manager",)


@pytest.mark.parametrize("operation_id", SUPPORT_OPERATIONS)
def test_only_staff_and_managers_call_a_support_operation(
    contract: BaseSchema, operation_id: str
) -> None:
    assert roles_of(contract, operation_id) == ("staff", "manager")

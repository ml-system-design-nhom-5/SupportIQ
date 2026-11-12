"""Every operation against all four roles, from the roles the contract names (SEC-16)."""

from dataclasses import replace
from http import HTTPStatus

import pytest
from schemathesis import BaseSchema

from supportiq_backend.accounts import PasswordHash
from supportiq_backend.platform import EventName
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
    "listAdminAccounts",
    "createAdminAccount",
    "changeAccountRole",
    "changeAccountStatus",
    "resetAccountPassword",
)
SHOP_OPERATIONS = tuple(name for name in OPERATIONS_WITH_ROLES if "Shop" in name)
ADMIN_OPERATIONS = tuple(name for name in OPERATIONS_WITH_ROLES if "Account" in name)


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

"""The table of documented outcomes: one row for each status of each operation (CON-27).

Each row names the state of the replica and the change that turns the valid call of
`tests.contract.calls` into the request that gets this status.
"""

from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import StrEnum
from http import HTTPStatus

from tests.contract.calls import NEW_ACCOUNT, NEW_PASSWORD, Call, World

OTHER_KEY = "00000000-0000-4000-8000-000000000002"
UNKNOWN_ACCOUNT = "99999999-9999-4999-8999-999999999999"


class Condition(StrEnum):
    """The state of the replica that answers."""

    HEALTHY = "healthy"
    REQUEST_FAILS = "request-fails"
    NO_DATABASE = "no-database"


type ChangeCall = Callable[[Call, World], Call]


@dataclass(frozen=True, slots=True)
class Outcome:
    """One documented status of one operation.

    Attributes:
        operation_id: The operation.
        status: The status.
        condition: The state of the replica.
        change: Turns the valid request into the one that gets this status.
        label: What makes this outcome differ from others with the same status.
    """

    operation_id: str
    status: HTTPStatus
    condition: Condition = Condition.HEALTHY
    change: ChangeCall = lambda call, _world: call
    label: str = ""

    def __str__(self) -> str:
        """Name the test after the operation and the status."""
        return f"{self.operation_id}-{self.status.value}{self.label}"


def without_session(call: Call, _world: World) -> Call:
    return replace(call, role=None)


def without_origin(call: Call, _world: World) -> Call:
    return replace(call, has_origin=False)


def as_admin(call: Call, _world: World) -> Call:
    return replace(call, role="admin")


def as_customer(call: Call, _world: World) -> Call:
    return replace(call, role="customer")


def with_invalid_body(call: Call, _world: World) -> Call:
    return replace(call, body={"unknown": True})


def with_invalid_limit(call: Call, _world: World) -> Call:
    return replace(call, params={"limit": "0"})


def with_wrong_password(call: Call, _world: World) -> Call:
    return replace(call, body={"login_name": "staff-contract", "password": "wrong-password"})


def with_unknown_order(call: Call, _world: World) -> Call:
    return replace(call, body={"order_id": "ORD-99999", "message": "Hi"})


def with_unknown_order_filter(call: Call, _world: World) -> Call:
    return replace(call, params={"order_id": "ORD-99999"})


def with_unknown_path_id(call: Call, _world: World) -> Call:
    return replace(call, path=call.path.rsplit("/", 1)[0] + "/UNKNOWN-1")


def with_unknown_target(call: Call, world: World) -> Call:
    return replace(call, path=call.path.replace(str(world.target_account_id), UNKNOWN_ACCOUNT))


def with_unchanged_role(call: Call, _world: World) -> Call:
    return replace(call, body={"role": "staff"})


def with_unchanged_status(call: Call, _world: World) -> Call:
    return replace(call, body={"is_active": True})


def with_wrong_current_password(call: Call, _world: World) -> Call:
    return replace(
        call,
        body={
            "current_password": "wrong-password",
            "new_password": NEW_PASSWORD,
            "is_signed_out_elsewhere": True,
        },
    )


def with_own_account(call: Call, world: World) -> Call:
    return replace(
        call, path=call.path.replace(str(world.target_account_id), str(world.admin_account_id))
    )


def with_taken_login_name(call: Call, _world: World) -> Call:
    return replace(call, key=OTHER_KEY, prior=call)


def with_reused_key(new_body: object) -> ChangeCall:
    def change(call: Call, _world: World) -> Call:
        return replace(call, body=new_body, prior=call)

    return change


SHOP_OPERATIONS = (
    "listShopProducts",
    "getShopProduct",
    "listShopOrders",
    "getShopOrder",
    "listShopTickets",
    "createShopTicket",
    "getShopTicket",
)
ADMIN_OPERATIONS = (
    "listAdminAccounts",
    "createAdminAccount",
    "changeAccountRole",
    "changeAccountStatus",
    "resetAccountPassword",
)
SESSION_OPERATIONS = ("getCurrentSession", "changeOwnPassword", "deleteCurrentSession")
HEALTH_OPERATIONS = ("checkLiveness", "checkReadiness")
OPERATIONS_WITH_A_SESSION = (*SESSION_OPERATIONS, *SHOP_OPERATIONS, *ADMIN_OPERATIONS)
ALL_OPERATIONS = ("createSession", *OPERATIONS_WITH_A_SESSION, *HEALTH_OPERATIONS)
OK_STATUSES = {
    "createSession": HTTPStatus.CREATED,
    "getCurrentSession": HTTPStatus.OK,
    "changeOwnPassword": HTTPStatus.CREATED,
    "deleteCurrentSession": HTTPStatus.NO_CONTENT,
    "listShopProducts": HTTPStatus.OK,
    "getShopProduct": HTTPStatus.OK,
    "listShopOrders": HTTPStatus.OK,
    "getShopOrder": HTTPStatus.OK,
    "listShopTickets": HTTPStatus.OK,
    "createShopTicket": HTTPStatus.CREATED,
    "getShopTicket": HTTPStatus.OK,
    "listAdminAccounts": HTTPStatus.OK,
    "createAdminAccount": HTTPStatus.CREATED,
    "changeAccountRole": HTTPStatus.CREATED,
    "changeAccountStatus": HTTPStatus.CREATED,
    "resetAccountPassword": HTTPStatus.CREATED,
    "checkLiveness": HTTPStatus.NO_CONTENT,
    "checkReadiness": HTTPStatus.NO_CONTENT,
}
UNPROCESSABLE = HTTPStatus.UNPROCESSABLE_CONTENT
OUTCOMES: tuple[Outcome, ...] = (
    *(Outcome(operation, status) for operation, status in OK_STATUSES.items()),
    *(
        Outcome(operation, HTTPStatus.UNAUTHORIZED, change=without_session)
        for operation in OPERATIONS_WITH_A_SESSION
    ),
    Outcome("createSession", HTTPStatus.UNAUTHORIZED, change=with_wrong_password),
    *(Outcome(operation, HTTPStatus.FORBIDDEN, change=as_admin) for operation in SHOP_OPERATIONS),
    *(
        Outcome(operation, HTTPStatus.FORBIDDEN, change=as_customer)
        for operation in ADMIN_OPERATIONS
    ),
    *(
        Outcome(operation, HTTPStatus.FORBIDDEN, change=without_origin, label="-origin")
        for operation in (
            "createSession",
            "deleteCurrentSession",
            "changeOwnPassword",
            "createShopTicket",
            "createAdminAccount",
            "changeAccountRole",
            "changeAccountStatus",
            "resetAccountPassword",
        )
    ),
    *(
        Outcome(operation, HTTPStatus.NOT_FOUND, change=with_unknown_path_id)
        for operation in ("getShopProduct", "getShopOrder", "getShopTicket")
    ),
    Outcome("listShopTickets", HTTPStatus.NOT_FOUND, change=with_unknown_order_filter),
    Outcome("createShopTicket", HTTPStatus.NOT_FOUND, change=with_unknown_order),
    Outcome("changeAccountRole", HTTPStatus.NOT_FOUND, change=with_unknown_target),
    Outcome("changeAccountStatus", HTTPStatus.NOT_FOUND, change=with_unknown_target),
    Outcome("resetAccountPassword", HTTPStatus.NOT_FOUND, change=with_unknown_target),
    Outcome(
        "createShopTicket",
        HTTPStatus.CONFLICT,
        change=with_reused_key({"order_id": "ORD-99999", "message": "Another message"}),
    ),
    Outcome("changeAccountRole", HTTPStatus.CONFLICT, change=with_reused_key({"role": "staff"})),
    Outcome(
        "changeAccountStatus", HTTPStatus.CONFLICT, change=with_reused_key({"is_active": True})
    ),
    Outcome(
        "changeOwnPassword",
        HTTPStatus.CONFLICT,
        change=with_reused_key(
            {
                "current_password": NEW_PASSWORD,
                "new_password": "another-password",
                "is_signed_out_elsewhere": False,
            }
        ),
    ),
    Outcome(
        "createAdminAccount",
        HTTPStatus.CONFLICT,
        change=with_reused_key({**NEW_ACCOUNT, "display_name": "Minh Le"}),
    ),
    Outcome(
        "createAdminAccount",
        HTTPStatus.CONFLICT,
        change=with_taken_login_name,
        label="-login-name-taken",
    ),
    Outcome(
        "resetAccountPassword",
        HTTPStatus.CONFLICT,
        change=with_reused_key({"password": NEW_PASSWORD, "is_signed_out_everywhere": False}),
    ),
    *(
        Outcome(operation, UNPROCESSABLE, change=with_invalid_limit)
        for operation in (
            "listShopProducts",
            "listShopOrders",
            "listShopTickets",
            "listAdminAccounts",
        )
    ),
    *(
        Outcome(operation, UNPROCESSABLE, change=with_invalid_body)
        for operation in (
            "createSession",
            "changeOwnPassword",
            "createShopTicket",
            "createAdminAccount",
            "changeAccountRole",
            "changeAccountStatus",
            "resetAccountPassword",
        )
    ),
    Outcome("changeAccountRole", UNPROCESSABLE, change=with_unchanged_role, label="-refused"),
    Outcome("changeAccountStatus", UNPROCESSABLE, change=with_unchanged_status, label="-refused"),
    Outcome(
        "changeOwnPassword", UNPROCESSABLE, change=with_wrong_current_password, label="-refused"
    ),
    Outcome("resetAccountPassword", UNPROCESSABLE, change=with_own_account, label="-refused"),
    *(
        Outcome(operation, HTTPStatus.INTERNAL_SERVER_ERROR, Condition.REQUEST_FAILS)
        for operation in ALL_OPERATIONS
    ),
    *(
        Outcome(operation, HTTPStatus.SERVICE_UNAVAILABLE, Condition.NO_DATABASE)
        for operation in ALL_OPERATIONS
        if operation != "checkLiveness"
    ),
)

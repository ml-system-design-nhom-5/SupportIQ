"""One valid request of each operation, against records that exist (TEST-05)."""

from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID

import httpx

from supportiq_backend.accounts import PasswordHash
from tests.integration.application import ALLOWED_ORIGIN
from tests.integration.builders import AccountSpec, DatabaseBuilder
from tests.unit.accounts.fakes import KNOWN_PASSWORD

SESSIONS = "/v1/sessions"
CURRENT_SESSION = "/v1/sessions/current"
OWN_PASSWORD_CHANGES = "/v1/sessions/current/password-changes"
PRODUCTS = "/v1/shop/products"
ORDERS = "/v1/shop/orders"
TICKETS = "/v1/shop/tickets"
ACCOUNTS = "/v1/admin/accounts"
KEY = "00000000-0000-4000-8000-000000000001"
LOGIN_NAME = "staff-contract"
ROLES = ("customer", "staff", "manager", "admin")
NEW_PASSWORD = "new-contract-password"
NEW_ACCOUNT = {
    "role": "staff",
    "login_number": 9001,
    "display_name": "Lan Do",
    "password": NEW_PASSWORD,
}


@dataclass(frozen=True, slots=True)
class World:
    """The records that the requests of a test refer to.

    Attributes:
        tokens: The raw session identifier of a signed-in account of each role.
        product_id: A product.
        order_id: An order of the signed-in customer.
        ticket_id: A ticket of the signed-in customer.
        target_account_id: A `staff` account that an admin can change.
        admin_account_id: The account of the signed-in admin.
    """

    tokens: Mapping[str, str]
    product_id: str
    order_id: str
    ticket_id: str
    target_account_id: UUID
    admin_account_id: UUID


@dataclass(frozen=True, slots=True)
class Call:
    """One HTTP request.

    Attributes:
        method: The HTTP method.
        path: The path.
        role: The role of the session that sends it, or None for no session.
        body: The JSON body, or None for no body.
        params: The query parameters.
        key: The `Idempotency-Key`, or None for none.
        has_origin: Whether it carries an allowed `Origin`.
        prior: A request to send first.
    """

    method: str
    path: str
    role: str | None = None
    body: object | None = None
    params: Mapping[str, str] | None = None
    key: str | None = None
    has_origin: bool = True
    prior: "Call | None" = None


async def build_world(builder: DatabaseBuilder, password_hash: PasswordHash) -> World:
    """Insert what the calls need, with one signed-in account of each role.

    The signed-in `staff` account has `KNOWN_PASSWORD`, so it can change its own password.

    Args:
        builder: The test data builder.
        password_hash: The hash of `KNOWN_PASSWORD`.

    Returns:
        The records.
    """
    customer_account, customer_id = await builder.customer_account()
    order_id = await builder.order_of_one_product(customer_id)
    staff = await builder.account(AccountSpec("staff", password_hash=password_hash))
    manager = await builder.account(AccountSpec("manager"))
    await builder.account(AccountSpec("manager"))
    admin = await builder.account(AccountSpec("admin"))
    await builder.account(AccountSpec("staff", login_name=LOGIN_NAME, password_hash=password_hash))
    return World(
        tokens={
            "customer": await builder.session(customer_account, "customer"),
            "staff": await builder.session(staff, "staff"),
            "manager": await builder.session(manager, "manager"),
            "admin": await builder.session(admin, "admin"),
        },
        product_id=await builder.product(name="Mug"),
        order_id=order_id,
        ticket_id=await builder.ticket(customer_id, order_id),
        target_account_id=await builder.account(AccountSpec("staff")),
        admin_account_id=admin,
    )


def valid_calls(world: World) -> Mapping[str, Call]:
    """Return a request of each operation that succeeds for the role that the contract names.

    Args:
        world: The records.

    Returns:
        The calls by `operationId`.
    """
    target = world.target_account_id
    return {
        "createSession": Call(
            "POST", SESSIONS, body={"login_name": LOGIN_NAME, "password": KNOWN_PASSWORD}
        ),
        "getCurrentSession": Call("GET", CURRENT_SESSION, role="customer"),
        "changeOwnPassword": Call(
            "POST",
            OWN_PASSWORD_CHANGES,
            role="staff",
            key=KEY,
            body={
                "current_password": KNOWN_PASSWORD,
                "new_password": NEW_PASSWORD,
                "is_signed_out_elsewhere": True,
            },
        ),
        "deleteCurrentSession": Call("DELETE", CURRENT_SESSION, role="customer"),
        "listShopProducts": Call("GET", PRODUCTS, role="customer"),
        "getShopProduct": Call("GET", f"{PRODUCTS}/{world.product_id}", role="customer"),
        "listShopOrders": Call("GET", ORDERS, role="customer"),
        "getShopOrder": Call("GET", f"{ORDERS}/{world.order_id}", role="customer"),
        "listShopTickets": Call("GET", TICKETS, role="customer"),
        "createShopTicket": Call(
            "POST",
            TICKETS,
            role="customer",
            key=KEY,
            body={"order_id": world.order_id, "message": "Where is my parcel?"},
        ),
        "getShopTicket": Call("GET", f"{TICKETS}/{world.ticket_id}", role="customer"),
        "listAdminAccounts": Call("GET", ACCOUNTS, role="admin"),
        "createAdminAccount": Call("POST", ACCOUNTS, role="admin", key=KEY, body=NEW_ACCOUNT),
        "changeAccountRole": Call(
            "POST",
            f"{ACCOUNTS}/{target}/role-changes",
            role="admin",
            key=KEY,
            body={"role": "manager"},
        ),
        "changeAccountStatus": Call(
            "POST",
            f"{ACCOUNTS}/{target}/status-changes",
            role="admin",
            key=KEY,
            body={"is_active": False},
        ),
        "resetAccountPassword": Call(
            "POST",
            f"{ACCOUNTS}/{target}/password-resets",
            role="admin",
            key=KEY,
            body={"password": NEW_PASSWORD, "is_signed_out_everywhere": True},
        ),
        "checkLiveness": Call("GET", "/health/live"),
        "checkReadiness": Call("GET", "/health/ready"),
    }


async def send(client: httpx.AsyncClient, call: Call, world: World) -> httpx.Response:
    """Send a request, after the request that it needs first.

    Args:
        client: The client of the application.
        call: The request.
        world: The records, with the session of each role.

    Returns:
        The response.
    """
    if call.prior is not None:
        await send(client, call.prior, world)
    origin = {"Origin": ALLOWED_ORIGIN} if call.has_origin else {}
    cookie = {} if call.role is None else {"Cookie": f"supportiq_session={world.tokens[call.role]}"}
    key = {} if call.key is None else {"Idempotency-Key": call.key}
    return await client.request(
        call.method,
        call.path,
        params=call.params,
        json=call.body,
        headers={**origin, **cookie, **key},
    )

"""The contract operations that code names, by `operationId` (CON-04)."""

from enum import StrEnum


class OperationId(StrEnum):
    """The operations that a role check, a cursor, or an idempotency record names.

    `createSession`, `getCurrentSession`, and `deleteCurrentSession` are open to every role and
    take no `Idempotency-Key`, so no code names them. `changeOwnPassword` is open to every role
    too, but its `Idempotency-Key` belongs to the operation.
    """

    LIST_SHOP_PRODUCTS = "listShopProducts"
    GET_SHOP_PRODUCT = "getShopProduct"
    LIST_SHOP_ORDERS = "listShopOrders"
    GET_SHOP_ORDER = "getShopOrder"
    CREATE_SHOP_TICKET = "createShopTicket"
    LIST_SHOP_TICKETS = "listShopTickets"
    GET_SHOP_TICKET = "getShopTicket"
    LIST_ADMIN_ACCOUNTS = "listAdminAccounts"
    CHANGE_ACCOUNT_ROLE = "changeAccountRole"
    CHANGE_ACCOUNT_STATUS = "changeAccountStatus"
    CHANGE_OWN_PASSWORD = "changeOwnPassword"  # noqa: S105  # an operation ID
    CREATE_ADMIN_ACCOUNT = "createAdminAccount"
    RESET_ACCOUNT_PASSWORD = "resetAccountPassword"  # noqa: S105  # an operation ID

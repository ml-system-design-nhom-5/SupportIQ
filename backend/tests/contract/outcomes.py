"""The table of documented outcomes: one row for each status of each operation (CON-27).

Each row names the state of the replica and the change of `tests.contract.call_changes` that
turns the valid call of `tests.contract.calls` into the request that gets this status.
"""

from dataclasses import dataclass
from enum import StrEnum
from http import HTTPStatus

from tests.contract.call_changes import (
    ChangeCall,
    after_a_retry,
    after_the_reply,
    as_admin,
    as_customer,
    as_staff,
    as_staff_on_the_closed_queue,
    on_a_ticket_that_requires_authority,
    with_an_empty_period,
    with_invalid_body,
    with_invalid_limit,
    with_key_reused_on_another_ticket,
    with_other_without_a_note,
    with_own_account,
    with_placeholder_in_body,
    with_reused_key,
    with_taken_login_name,
    with_unchanged_role,
    with_unchanged_status,
    with_unknown_order,
    with_unknown_order_filter,
    with_unknown_path_id,
    with_unknown_status,
    with_unknown_target,
    with_unknown_ticket,
    with_wrong_current_password,
    with_wrong_password,
    without_key,
    without_origin,
    without_session,
)
from tests.contract.calls import ESCALATION, NEW_ACCOUNT, NEW_PASSWORD, REPLY_WITHOUT_A_DRAFT


class Condition(StrEnum):
    """The state of the replica that answers."""

    HEALTHY = "healthy"
    REQUEST_FAILS = "request-fails"
    NO_DATABASE = "no-database"
    NO_AI_SERVICE = "no-ai-service"


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


SHOP_OPERATIONS = (
    "listShopProducts",
    "getShopProduct",
    "listShopOrders",
    "getShopOrder",
    "listShopTickets",
    "createShopTicket",
    "getShopTicket",
)
CONSOLE_OPERATIONS = (
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
)
ADMIN_OPERATIONS = (
    "listAdminAccounts",
    "getAdminVersions",
    "createAdminAccount",
    "changeAccountRole",
    "changeAccountStatus",
    "resetAccountPassword",
)
SESSION_OPERATIONS = ("getCurrentSession", "changeOwnPassword", "deleteCurrentSession")
HEALTH_OPERATIONS = ("checkLiveness", "checkReadiness")
OPERATIONS_WITH_A_SESSION = (
    *SESSION_OPERATIONS,
    *SHOP_OPERATIONS,
    *CONSOLE_OPERATIONS,
    *ADMIN_OPERATIONS,
)
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
    "listConsoleTickets": HTTPStatus.OK,
    "getConsoleTicket": HTTPStatus.OK,
    "recordTicketView": HTTPStatus.NO_CONTENT,
    "createSuggestion": HTTPStatus.ACCEPTED,
    "createReplyProposal": HTTPStatus.CREATED,
    "sendReply": HTTPStatus.CREATED,
    "createEscalation": HTTPStatus.CREATED,
    "getSuggestionEvents": HTTPStatus.NO_CONTENT,
    "getConsoleKbDocumentVersion": HTTPStatus.OK,
    "getConsoleReport": HTTPStatus.OK,
    "listAdminAccounts": HTTPStatus.OK,
    "getAdminVersions": HTTPStatus.OK,
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
    *(
        Outcome(operation, HTTPStatus.FORBIDDEN, change=as_admin)
        for operation in (*SHOP_OPERATIONS, *CONSOLE_OPERATIONS)
    ),
    Outcome(
        "listConsoleTickets",
        HTTPStatus.FORBIDDEN,
        change=as_staff_on_the_closed_queue,
        label="-queue",
    ),
    Outcome(
        "sendReply",
        HTTPStatus.FORBIDDEN,
        change=on_a_ticket_that_requires_authority,
        label="-authority",
    ),
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
            "recordTicketView",
            "createSuggestion",
            "createReplyProposal",
            "sendReply",
            "createEscalation",
            "createAdminAccount",
            "changeAccountRole",
            "changeAccountStatus",
            "resetAccountPassword",
        )
    ),
    *(
        Outcome(operation, HTTPStatus.NOT_FOUND, change=with_unknown_path_id)
        for operation in (
            "getShopProduct",
            "getShopOrder",
            "getShopTicket",
            "getConsoleTicket",
            "getConsoleKbDocumentVersion",
        )
    ),
    *(
        Outcome(operation, HTTPStatus.NOT_FOUND, change=with_unknown_ticket)
        for operation in (
            "recordTicketView",
            "createSuggestion",
            "createReplyProposal",
            "sendReply",
            "createEscalation",
            "getSuggestionEvents",
        )
    ),
    # A retry leaves a pending suggestion, and the stream ends at the time limit of the tests.
    Outcome("getSuggestionEvents", HTTPStatus.OK, change=after_a_retry, label="-stream"),
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
    Outcome("recordTicketView", HTTPStatus.CONFLICT, change=with_key_reused_on_another_ticket),
    Outcome("createSuggestion", HTTPStatus.CONFLICT, change=after_the_reply),
    Outcome(
        "createReplyProposal",
        HTTPStatus.CONFLICT,
        change=with_reused_key({**REPLY_WITHOUT_A_DRAFT, "body": "Another proposal"}),
    ),
    Outcome("createReplyProposal", HTTPStatus.CONFLICT, change=after_the_reply, label="-state"),
    Outcome(
        "sendReply",
        HTTPStatus.CONFLICT,
        change=with_reused_key({**REPLY_WITHOUT_A_DRAFT, "body": "Another reply"}),
    ),
    Outcome(
        "createEscalation",
        HTTPStatus.CONFLICT,
        change=with_reused_key({**ESCALATION, "staff_reason_codes": ["kb_gap"]}),
    ),
    Outcome("createEscalation", HTTPStatus.CONFLICT, change=after_the_reply, label="-state"),
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
    Outcome("listConsoleTickets", UNPROCESSABLE, change=with_unknown_status),
    Outcome("recordTicketView", UNPROCESSABLE, change=without_key),
    *(
        Outcome(operation, UNPROCESSABLE, change=with_invalid_body)
        for operation in (
            "createSession",
            "changeOwnPassword",
            "createShopTicket",
            "createSuggestion",
            "createReplyProposal",
            "sendReply",
            "createEscalation",
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
        Outcome(operation, UNPROCESSABLE, change=with_placeholder_in_body, label="-placeholder")
        for operation in ("createReplyProposal", "sendReply")
    ),
    Outcome("createEscalation", UNPROCESSABLE, change=with_other_without_a_note, label="-note"),
    Outcome("getConsoleReport", UNPROCESSABLE, change=with_an_empty_period, label="-period"),
    Outcome("getConsoleReport", HTTPStatus.FORBIDDEN, change=as_staff, label="-staff"),
    Outcome(
        "getConsoleKbDocumentVersion",
        HTTPStatus.SERVICE_UNAVAILABLE,
        Condition.NO_AI_SERVICE,
        label="-ai-service",
    ),
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

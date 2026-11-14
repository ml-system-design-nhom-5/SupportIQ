"""The changes that turn the valid call of an operation into the call of one outcome.

`tests.contract.outcomes` names one of them in each row of its table (CON-27).
"""

from collections.abc import Callable
from dataclasses import replace

from tests.contract.calls import (
    NEW_PASSWORD,
    REPLY_WITHOUT_A_DRAFT,
    REPORT_PERIOD,
    Call,
    World,
    valid_calls,
)

OTHER_KEY = "00000000-0000-4000-8000-000000000002"
UNKNOWN_ACCOUNT = "99999999-9999-4999-8999-999999999999"
UNKNOWN_TICKET = "TCK-999999"

type ChangeCall = Callable[[Call, World], Call]


def without_session(call: Call, _world: World) -> Call:
    return replace(call, role=None)


def without_origin(call: Call, _world: World) -> Call:
    return replace(call, has_origin=False)


def as_admin(call: Call, _world: World) -> Call:
    return replace(call, role="admin")


def as_staff(call: Call, _world: World) -> Call:
    return replace(call, role="staff")


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


def with_unknown_ticket(call: Call, world: World) -> Call:
    return replace(call, path=call.path.replace(world.ticket_id, UNKNOWN_TICKET))


def without_key(call: Call, _world: World) -> Call:
    return replace(call, key=None)


def with_unknown_status(call: Call, _world: World) -> Call:
    return replace(call, params={"status": "unknown"})


def as_staff_on_the_closed_queue(call: Call, _world: World) -> Call:
    return replace(call, params={"status": "closed"})


def with_key_reused_on_another_ticket(call: Call, world: World) -> Call:
    return replace(call, path=call.path.replace(world.ticket_id, world.other_ticket_id), prior=call)


def after_the_reply(call: Call, world: World) -> Call:
    return replace(call, prior=valid_calls(world)["sendReply"])


def on_a_ticket_that_requires_authority(call: Call, world: World) -> Call:
    return replace(call, path=call.path.replace(world.ticket_id, world.authority_ticket_id))


def with_placeholder_in_body(call: Call, _world: World) -> Call:
    return replace(call, body={**REPLY_WITHOUT_A_DRAFT, "body": "We wrote to [EMAIL_1]."})


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


def with_other_without_a_note(call: Call, _world: World) -> Call:
    return replace(call, body={"staff_reason_codes": ["other"]})


def with_an_empty_period(call: Call, _world: World) -> Call:
    # `start_at` must be earlier than `end_at` (contract `InvalidReportPeriod`).
    return replace(
        call, params={"start_at": REPORT_PERIOD["start_at"], "end_at": REPORT_PERIOD["start_at"]}
    )


def with_reused_key(new_body: object) -> ChangeCall:
    def change(call: Call, _world: World) -> Call:
        return replace(call, body=new_body, prior=call)

    return change

"""What the tests of the reads of ai-service share: sessions of each role and problem bodies.

Staff and managers sign in with the helpers of the console tests, so every test of the
console signs them in the same way (TEST-08).
"""

from collections.abc import Awaitable, Callable

import httpx

from tests.integration.accounts.admin_requests import sign_in_as_new_admin
from tests.integration.ai_service_doubles import read_example
from tests.integration.application import session_headers
from tests.integration.builders import DatabaseBuilder
from tests.integration.tickets.console_requests import SupportSession

PROBLEM_MEDIA_TYPE = "application/problem+json"

# Signs in a new account of one role and returns the headers of its requests.
type SignIn = Callable[[DatabaseBuilder], Awaitable[dict[str, str]]]


async def sign_in_as_customer(builder: DatabaseBuilder) -> dict[str, str]:
    account_id, _ = await builder.customer_account()
    return session_headers(await builder.session(account_id, "customer"))


async def sign_in_as_admin(builder: DatabaseBuilder) -> dict[str, str]:
    _, token = await sign_in_as_new_admin(builder)
    return session_headers(token)


def headers_of(sign_in: Callable[[DatabaseBuilder], Awaitable[SupportSession]]) -> SignIn:
    """Turn a sign-in of the console tests into one that returns only the headers.

    Args:
        sign_in: `sign_in_as_support` or `sign_in_as_manager` of the console tests.

    Returns:
        The sign-in, for a test that takes the headers of any role.
    """

    async def sign_in_for_headers(builder: DatabaseBuilder) -> dict[str, str]:
        return (await sign_in(builder)).headers

    return sign_in_for_headers


def problem_of(response: httpx.Response) -> tuple[str, dict[str, object]]:
    """Return the media type and the body of a problem response, without its `trace_id`."""
    body: dict[str, object] = response.json()
    del body["trace_id"]
    return response.headers["content-type"], body


def problem_example(name: str) -> tuple[str, dict[str, object]]:
    """Return what `problem_of` returns for a problem example of the contracts."""
    body = read_example(f"problems/{name}.json")
    del body["trace_id"]
    return PROBLEM_MEDIA_TYPE, body

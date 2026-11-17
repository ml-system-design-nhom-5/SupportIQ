"""Read the fields of console request bodies that the generated models do not check.

The generated models check types, lengths, and patterns, but not `uniqueItems`, and not
whether PostgreSQL can store a text. Each refusal names the location of the field, as every
other violation of the contract does, and never its value (CON-02, SEC-21).
"""

from collections.abc import Hashable, Iterable

from supportiq_backend.platform import RequestContractError, is_storable_text


def parse_unique_items[ItemT: Hashable](items: Iterable[ItemT], location: str) -> tuple[ItemT, ...]:
    """Read the items of an array that the contract marks `uniqueItems: true`.

    Args:
        items: The items, in the order of the request.
        location: The location of the array, such as `body.staff_reason_codes`.

    Returns:
        The items, in the same order.

    Raises:
        RequestContractError: An item appears more than once.
    """
    parsed = tuple(items)
    if len(frozenset(parsed)) != len(parsed):
        raise RequestContractError((location,))
    return parsed


def parse_storable_text(text: str, location: str) -> str:
    """Read a text that `backend` stores, such as a reply body or a staff note.

    Args:
        text: The text, valid for the contract already.
        location: The location of the field, such as `body.note`.

    Returns:
        The text, unchanged.

    Raises:
        RequestContractError: PostgreSQL cannot store the text, such as one with a NUL.
    """
    if not is_storable_text(text):
        raise RequestContractError((location,))
    return text

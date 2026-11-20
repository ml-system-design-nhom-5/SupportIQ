"""The placeholder syntax of ADR-0010: pseudonyms that backend writes and masks of ai-service."""

import re
from enum import StrEnum

# The highest number of a pseudonym of one type within one ticket (ADR-0010, item 3).
PSEUDONYM_NUMBER_MAXIMUM = 999

# Every placeholder matches this expression, and nothing else may match it (ADR-0010, item 2).
PLACEHOLDER_PATTERN = re.compile(
    r"\[(NAME|EMAIL|PHONE|CARD|ADDRESS|ORDER_ID|TRACKING_ID|TRANSACTION_ID|LITERAL)"
    r"(_[1-9][0-9]{0,2})?\]"
)


class PseudonymType(StrEnum):
    """The type of a placeholder, as it appears between the brackets (ADR-0010, item 1)."""

    NAME = "NAME"
    EMAIL = "EMAIL"
    PHONE = "PHONE"
    CARD = "CARD"
    ADDRESS = "ADDRESS"
    ORDER_ID = "ORDER_ID"
    TRACKING_ID = "TRACKING_ID"
    TRANSACTION_ID = "TRANSACTION_ID"
    LITERAL = "LITERAL"


def contains_placeholder(text: str) -> bool:
    """Tell whether a text holds a placeholder, which must never reach a customer (SEC-38).

    Args:
        text: A reply or proposal body, or any other text.

    Returns:
        True when some part of the text matches the placeholder syntax.
    """
    return PLACEHOLDER_PATTERN.search(text) is not None


def format_pseudonym(pseudonym_type: PseudonymType, number: int) -> str:
    """Write the pseudonym of a type and a number, such as `[ORDER_ID_1]`.

    Args:
        pseudonym_type: The type.
        number: The number, from 1 to `PSEUDONYM_NUMBER_MAXIMUM`.

    Returns:
        The pseudonym.
    """
    return f"[{pseudonym_type.value}_{number}]"

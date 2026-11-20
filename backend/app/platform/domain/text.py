"""What PostgreSQL can store in a text column."""

_NUL = "\x00"


def is_storable_text(text: str) -> bool:
    """Tell whether a text can reach the database.

    PostgreSQL refuses the NUL character, and UTF-8 cannot encode a lone surrogate. A text of
    that kind can name no stored row, so a lookup treats it as unknown (never as a defect),
    and a body that would store it is an invalid request.

    Args:
        text: A text from a request.

    Returns:
        True when the database can hold the text.
    """
    if _NUL in text:
        return False
    try:
        text.encode()
    except UnicodeEncodeError:
        return False
    return True

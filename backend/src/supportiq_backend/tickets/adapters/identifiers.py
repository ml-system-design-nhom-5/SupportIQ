"""Convert the optional identifiers of the tickets rows to and from those of the domain."""

from uuid import UUID

from supportiq_backend.suggestions import SuggestionId


def to_optional_uuid(identifier: str | None) -> UUID | None:
    """Turn an optional identifier of the domain into the value of a `uuid` column.

    Args:
        identifier: The identifier, such as a suggestion ID, or None.

    Returns:
        The UUID, or None.
    """
    return None if identifier is None else UUID(identifier)


def to_optional_suggestion_id(value: UUID | None) -> SuggestionId | None:
    """Turn the value of an optional `uuid` column into a suggestion ID.

    Args:
        value: The column value.

    Returns:
        The suggestion ID, or None.
    """
    return None if value is None else SuggestionId(str(value))

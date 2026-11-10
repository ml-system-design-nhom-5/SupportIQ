"""The `limit` and `cursor` parameters of every list operation (CON-14, CON-15).

A cursor is the URL-safe Base64 text, without padding, of a compact JSON object. The object
always holds `op`, the operation that returned the cursor, so a cursor of another operation
is refused. A cursor is opaque but not secret, because URLs reach logs: each list puts only
Public or Internal values in it (backend foundation design, Data and contracts).
"""

import base64
import binascii
import json
import re
from collections.abc import Mapping
from datetime import datetime
from typing import cast

from supportiq_backend.platform import (
    InvalidCursorError,
    InvalidLimitError,
    UnexpectedFailureError,
    is_storable_text,
)
from supportiq_backend.platform.web.responses import UTC_OFFSET

# The `Limit` parameter of the contract: from 1 to 100, and 20 when absent.
PAGE_SIZE_MINIMUM = 1
PAGE_SIZE_MAXIMUM = 100
PAGE_SIZE_DEFAULT = 20
# The `Cursor` schema of the contract: from 1 to 512 characters.
CURSOR_MAX_LENGTH = 512
OPERATION_FIELD = "op"
_LIMIT_PATTERN = re.compile(r"[0-9]{1,3}")
_CURSOR_PATTERN = re.compile(r"[A-Za-z0-9_-]+")
_BASE64_BLOCK = 4
# The largest value of a PostgreSQL bigint, the type of an OFFSET.
_LARGEST_POSITION = 2**63 - 1
_IMPOSSIBLE_REMAINDER = 1

type CursorValue = str | int


class CursorTooLongError(UnexpectedFailureError):
    """A cursor would exceed the contract's maximum length: a defect of its list."""


class CursorFields:
    """The fields of a decoded cursor, read with the type that each list expects."""

    def __init__(self, values: Mapping[str, object]) -> None:
        """Keep the decoded values.

        Args:
            values: The fields of the cursor, without `op`.
        """
        self._values = values

    def text(self, name: str) -> str:
        """Return a non-empty text field.

        Args:
            name: The name of the field.

        Returns:
            The value.

        Raises:
            InvalidCursorError: The field is missing, empty, not text, or not storable.
        """
        value = self._values.get(name)
        if not isinstance(value, str) or not value or not is_storable_text(value):
            raise InvalidCursorError
        return value

    def timestamp(self, name: str) -> datetime:
        """Return a field that holds a time in UTC, as `format_timestamp` writes it.

        Args:
            name: The name of the field.

        Returns:
            The time, with the precision of the database.

        Raises:
            InvalidCursorError: The field is missing, not a time, or not in UTC.
        """
        try:
            moment = datetime.fromisoformat(self.text(name))
        except ValueError as error:
            raise InvalidCursorError from error
        if moment.utcoffset() != UTC_OFFSET:
            raise InvalidCursorError
        return moment

    def natural_number(self, name: str) -> int:
        """Return a field that is an integer of at least zero.

        Args:
            name: The name of the field.

        Returns:
            The value.

        Raises:
            InvalidCursorError: The field is missing, not an integer, or out of range.
        """
        value = self._values.get(name)
        if not isinstance(value, int) or isinstance(value, bool):
            raise InvalidCursorError
        if not 0 <= value <= _LARGEST_POSITION:
            raise InvalidCursorError
        return value


def parse_limit(raw: str | None) -> int:
    """Parse the `limit` query parameter.

    Args:
        raw: The parameter as sent, or None when absent.

    Returns:
        The page size, `PAGE_SIZE_DEFAULT` when absent.

    Raises:
        InvalidLimitError: The value is not an integer from 1 to 100.
    """
    if raw is None:
        return PAGE_SIZE_DEFAULT
    if not _LIMIT_PATTERN.fullmatch(raw) or not (
        PAGE_SIZE_MINIMUM <= int(raw) <= PAGE_SIZE_MAXIMUM
    ):
        raise InvalidLimitError(PAGE_SIZE_MINIMUM, PAGE_SIZE_MAXIMUM)
    return int(raw)


def encode_cursor(operation_id: str, fields: Mapping[str, CursorValue]) -> str:
    """Write the cursor of the next page.

    Args:
        operation_id: The operation that returns the cursor, such as `listShopProducts`.
        fields: The position of the last item, in Public or Internal values only.

    Returns:
        The cursor.

    Raises:
        CursorTooLongError: The cursor would be longer than the contract allows.
    """
    payload = {OPERATION_FIELD: operation_id, **fields}
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    cursor = base64.urlsafe_b64encode(text.encode()).rstrip(b"=").decode("ascii")
    if len(cursor) > CURSOR_MAX_LENGTH:
        raise CursorTooLongError
    return cursor


def decode_cursor(
    raw: str | None, operation_id: str, field_names: frozenset[str]
) -> CursorFields | None:
    """Read the `cursor` query parameter of one operation.

    Args:
        raw: The parameter as sent, or None when absent.
        operation_id: The operation that reads the cursor.
        field_names: The exact fields that the operation's cursors hold, besides `op`.

    Returns:
        The fields, or None when the parameter is absent, which means the first page.

    Raises:
        InvalidCursorError: The cursor is empty, malformed, or from another operation.
    """
    if raw is None:
        return None
    values = _decode_object(raw)
    if values.get(OPERATION_FIELD) != operation_id or set(values) != {
        OPERATION_FIELD,
        *field_names,
    }:
        raise InvalidCursorError
    return CursorFields({name: value for name, value in values.items() if name != OPERATION_FIELD})


def _decode_object(raw: str) -> dict[str, object]:
    is_well_formed = (
        len(raw) <= CURSOR_MAX_LENGTH
        and _CURSOR_PATTERN.fullmatch(raw) is not None
        and len(raw) % _BASE64_BLOCK != _IMPOSSIBLE_REMAINDER
    )
    if not is_well_formed:
        raise InvalidCursorError
    padded = raw + "=" * (-len(raw) % _BASE64_BLOCK)
    try:
        decoded: object = json.loads(base64.urlsafe_b64decode(padded).decode())
    except (binascii.Error, UnicodeDecodeError, ValueError, RecursionError) as error:
        raise InvalidCursorError from error
    if not isinstance(decoded, dict):
        raise InvalidCursorError
    # A JSON object decodes to a dict with text keys and JSON values.
    return cast("dict[str, object]", decoded)

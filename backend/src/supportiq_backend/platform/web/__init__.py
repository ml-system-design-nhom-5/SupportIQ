"""Public API of platform for interface layers: requests, responses, pagination, problems.

Only the `api` layers of features and the composition root import it (ARCH-17).
"""

from supportiq_backend.platform.web.exception_handling import (
    UnhandledErrorMiddleware,
    install_exception_handling,
)
from supportiq_backend.platform.web.health import build_health_router
from supportiq_backend.platform.web.pagination import (
    CURSOR_MAX_LENGTH,
    PAGE_SIZE_DEFAULT,
    PAGE_SIZE_MAXIMUM,
    PAGE_SIZE_MINIMUM,
    CursorFields,
    CursorTooLongError,
    CursorValue,
    decode_cursor,
    encode_cursor,
    parse_limit,
)
from supportiq_backend.platform.web.problems import (
    PROBLEM_MEDIA_TYPE,
    build_problem_response,
)
from supportiq_backend.platform.web.request_logging import RequestLoggingMiddleware
from supportiq_backend.platform.web.requests import (
    IDEMPOTENCY_KEY_HEADER,
    RequestDependency,
    locations_of,
    parse_json_body,
)
from supportiq_backend.platform.web.responses import (
    JSON_MEDIA_TYPE,
    NonUtcTimestampError,
    format_optional_timestamp,
    format_timestamp,
    json_response,
    provide,
    render_json,
    stored_json_response,
)

__all__ = [
    "CURSOR_MAX_LENGTH",
    "IDEMPOTENCY_KEY_HEADER",
    "JSON_MEDIA_TYPE",
    "PAGE_SIZE_DEFAULT",
    "PAGE_SIZE_MAXIMUM",
    "PAGE_SIZE_MINIMUM",
    "PROBLEM_MEDIA_TYPE",
    "CursorFields",
    "CursorTooLongError",
    "CursorValue",
    "NonUtcTimestampError",
    "RequestDependency",
    "RequestLoggingMiddleware",
    "UnhandledErrorMiddleware",
    "build_health_router",
    "build_problem_response",
    "decode_cursor",
    "encode_cursor",
    "format_optional_timestamp",
    "format_timestamp",
    "install_exception_handling",
    "json_response",
    "locations_of",
    "parse_json_body",
    "parse_limit",
    "provide",
    "render_json",
    "stored_json_response",
]

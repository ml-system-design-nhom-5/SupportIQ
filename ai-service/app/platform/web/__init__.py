"""Public API of platform for interface layers: requests, responses, problems, the token.

Only the `api` layers of features and the composition root import it (ARCH-17).
"""

from app.platform.web.exception_handling import (
    UnhandledErrorMiddleware,
    install_exception_handling,
    locations_of,
)
from app.platform.web.health import build_health_router
from app.platform.web.problems import (
    PROBLEM_MEDIA_TYPE,
    build_problem_response,
)
from app.platform.web.request_logging import RequestLoggingMiddleware
from app.platform.web.requests import parse_json_body, parse_timestamp
from app.platform.web.responses import (
    JSON_MEDIA_TYPE,
    NonUtcTimestampError,
    format_timestamp,
    json_response,
    provide,
    render_json,
)
from app.platform.web.service_token import (
    AUTHORIZATION_HEADER,
    build_service_token_guard,
)

__all__ = [
    "AUTHORIZATION_HEADER",
    "JSON_MEDIA_TYPE",
    "PROBLEM_MEDIA_TYPE",
    "NonUtcTimestampError",
    "RequestLoggingMiddleware",
    "UnhandledErrorMiddleware",
    "build_health_router",
    "build_problem_response",
    "build_service_token_guard",
    "format_timestamp",
    "install_exception_handling",
    "json_response",
    "locations_of",
    "parse_json_body",
    "parse_timestamp",
    "provide",
    "render_json",
]

"""Public API of platform for interface layers: problems, responses, the service token.

Only the `api` layers of features and the composition root import it (ARCH-17).
"""

from supportiq_ai_service.platform.web.exception_handling import (
    UnhandledErrorMiddleware,
    install_exception_handling,
    locations_of,
)
from supportiq_ai_service.platform.web.health import build_health_router
from supportiq_ai_service.platform.web.problems import (
    PROBLEM_MEDIA_TYPE,
    build_problem_response,
)
from supportiq_ai_service.platform.web.request_logging import RequestLoggingMiddleware
from supportiq_ai_service.platform.web.responses import (
    JSON_MEDIA_TYPE,
    json_response,
    provide,
    render_json,
)
from supportiq_ai_service.platform.web.service_token import (
    AUTHORIZATION_HEADER,
    build_service_token_guard,
)

__all__ = [
    "AUTHORIZATION_HEADER",
    "JSON_MEDIA_TYPE",
    "PROBLEM_MEDIA_TYPE",
    "RequestLoggingMiddleware",
    "UnhandledErrorMiddleware",
    "build_health_router",
    "build_problem_response",
    "build_service_token_guard",
    "install_exception_handling",
    "json_response",
    "locations_of",
    "provide",
    "render_json",
]

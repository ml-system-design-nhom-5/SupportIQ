from typing import Any
from fastapi import Request
from fastapi.responses import JSONResponse

class AppError(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        title: str,
        detail: str | None = None,
        errors: list[dict[str, str]] | None = None,
        headers: dict[str, str] | None = None,
    ):
        super().__init__(detail or title)
        self.status = status
        self.code = code
        self.title = title
        self.detail = detail
        self.errors = errors
        self.headers = headers or {}

def format_problem_response(
    status: int,
    code: str,
    title: str,
    detail: str | None = None,
    request_id: str | None = None,
    errors: list[dict[str, str]] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    content: dict[str, Any] = {
        "type": f"urn:supportiq:problem:{code}",
        "title": title,
        "status": status,
    }
    if detail is not None:
        content["detail"] = detail
    if request_id is not None:
        content["request_id"] = request_id
    if errors is not None:
        content["errors"] = errors

    resp_headers = {"Content-Type": "application/problem+json"}
    if request_id:
        resp_headers["X-Request-ID"] = request_id
    if headers:
        resp_headers.update(headers)

    return JSONResponse(status_code=status, content=content, headers=resp_headers)

async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    return format_problem_response(
        status=exc.status,
        code=exc.code,
        title=exc.title,
        detail=exc.detail,
        request_id=request_id,
        errors=exc.errors,
        headers=exc.headers,
    )

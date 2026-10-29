import uuid
from typing import Callable
from fastapi import FastAPI, Request, Response, Header
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.middleware.base import BaseHTTPMiddleware

from src.config import settings
from src.errors import AppError, app_error_handler, format_problem_response

MAX_JSON_BODY_BYTES = 64 * 1024  # 64 KiB

class SecurityAndTracingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = req_id

        # Check content length for payload_too_large (64 KiB)
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > MAX_JSON_BODY_BYTES:
            return format_problem_response(
                status=413,
                code="payload_too_large",
                title="Payload Too Large",
                detail="Request body exceeds the maximum permitted size of 64 KiB.",
                request_id=req_id,
            )

        response = await call_next(request)
        response.headers["X-Request-ID"] = req_id
        return response

app = FastAPI(
    title="SupportIQ Core Backend",
    version="1.0.0",
    docs_url="/docs",
    redoc_url=None,
    openapi_url="/api/v1/openapi.json",
)

app.add_middleware(SecurityAndTracingMiddleware)
app.add_exception_handler(AppError, app_error_handler)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    errors = [{"loc": ".".join(str(l) for l in err["loc"]), "msg": err["msg"]} for err in exc.errors()]
    return format_problem_response(
        status=422,
        code="validation_error",
        title="Unprocessable Entity",
        detail="The request body or parameters failed validation.",
        request_id=request_id,
        errors=errors,
    )

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    return format_problem_response(
        status=500,
        code="internal_error",
        title="Internal Server Error",
        detail="An unexpected error occurred while processing the request.",
        request_id=request_id,
    )

def verify_internal_token(authorization: str | None = Header(None)) -> None:
    expected = f"Bearer {settings.internal_service_token}"
    if not authorization or authorization != expected:
        raise AppError(
            status=401,
            code="unauthenticated",
            title="Unauthorized",
            detail="Valid internal service bearer token required.",
        )

@app.get("/api/v1/health/live")
async def health_live(authorization: str | None = Header(None)):
    verify_internal_token(authorization)
    return {"data": {"status": "ok", "ai_available": False}}

@app.get("/api/v1/health/ready")
async def health_ready(authorization: str | None = Header(None)):
    verify_internal_token(authorization)
    return {"data": {"status": "ok"}}

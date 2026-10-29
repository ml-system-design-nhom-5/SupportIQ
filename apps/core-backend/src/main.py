import json
import os
import uuid
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Callable
from fastapi import FastAPI, Request, Response, Header
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy import select

from src.config import settings
from src.errors import AppError, app_error_handler, format_problem_response
from src.db import Base, app_engine, AppSessionLocal
from src.modules.auth.models import UserModel
from src.modules.auth.service import hash_password
from src.modules.auth.routes import router as auth_router
from src.modules.commerce.models import ProductModel
from src.modules.commerce.routes import router as commerce_router
from src.modules.tickets.routes import router as tickets_router
from src.modules.audit.routes import router as audit_router
from src.modules.reports.routes import router as reports_router
from src.modules.orchestration.routes import router as orchestration_router
from src.modules.review.routes import router as review_router

MAX_JSON_BODY_BYTES = 64 * 1024  # 64 KiB

async def seed_demo_data():
    async with AppSessionLocal() as session:
        # Seed users
        user_res = await session.execute(select(UserModel).limit(1))
        if user_res.scalar_one_or_none() is None:
            demo_password_hash = hash_password("DemoPassword123!")
            users = [
                UserModel(
                    id="a0000000-0000-0000-0000-000000000001",
                    email="admin@supportiq.demo",
                    password_hash=demo_password_hash,
                    role="admin",
                    active=True,
                    role_version=1,
                ),
                UserModel(
                    id="a0000000-0000-0000-0000-000000000002",
                    email="manager1@supportiq.demo",
                    password_hash=demo_password_hash,
                    role="manager",
                    active=True,
                    role_version=1,
                ),
                UserModel(
                    id="a0000000-0000-0000-0000-000000000003",
                    email="agent1@supportiq.demo",
                    password_hash=demo_password_hash,
                    role="agent",
                    active=True,
                    role_version=1,
                ),
                UserModel(
                    id="a0000000-0000-0000-0000-000000000004",
                    email="customer1@supportiq.demo",
                    password_hash=demo_password_hash,
                    role="customer",
                    active=True,
                    role_version=1,
                ),
                UserModel(
                    id="a0000000-0000-0000-0000-000000000005",
                    email="customer2@supportiq.demo",
                    password_hash=demo_password_hash,
                    role="customer",
                    active=True,
                    role_version=1,
                ),
            ]
            session.add_all(users)
            await session.commit()

        # Seed products
        prod_res = await session.execute(select(ProductModel).limit(1))
        if prod_res.scalar_one_or_none() is None:
            products_data = []
            seed_file = Path("data/business/demo_seed.json")
            if seed_file.exists():
                try:
                    with open(seed_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        products_data = data.get("products", [])
                except Exception:
                    pass

            if not products_data:
                products_data = [
                    {
                        "id": "b0000000-0000-0000-0000-000000000001",
                        "sku": "PROD-HEADPHONE-01",
                        "name": "Tai nghe chống ồn không dây Pro",
                        "description": "Tai nghe bluetooth chụp tai.",
                        "unit_price_minor": 1500000,
                        "currency": "VND",
                        "stock_quantity": 50,
                        "category": "audio",
                    }
                ]

            for p in products_data:
                session.add(
                    ProductModel(
                        id=p["id"],
                        sku=p["sku"],
                        name=p["name"],
                        description=p.get("description"),
                        unit_price_minor=p["unit_price_minor"],
                        currency=p.get("currency", "VND"),
                        stock_quantity=p.get("stock_quantity", 0),
                        category=p.get("category"),
                    )
                )
            await session.commit()

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with app_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if "sqlite" in str(app_engine.url):
            from sqlalchemy import text
            await conn.execute(text("CREATE TRIGGER IF NOT EXISTS prevent_audit_delete BEFORE DELETE ON audit_events BEGIN SELECT RAISE(ABORT, 'audit.events is append-only'); END;"))
            await conn.execute(text("CREATE TRIGGER IF NOT EXISTS prevent_audit_update BEFORE UPDATE ON audit_events BEGIN SELECT RAISE(ABORT, 'audit.events is append-only'); END;"))
    await seed_demo_data()
    yield

class SecurityAndTracingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = req_id

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
    lifespan=lifespan,
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

# Mount routers
app.include_router(auth_router)
app.include_router(commerce_router)
app.include_router(tickets_router)
app.include_router(audit_router)
app.include_router(reports_router)
app.include_router(orchestration_router)
app.include_router(review_router)

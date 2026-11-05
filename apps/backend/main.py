"""Composition root and HTTP boundary for the SupportIQ application."""

from contextlib import asynccontextmanager
from datetime import datetime
import hashlib
from pathlib import Path
import secrets
import uuid

from argon2 import PasswordHasher
import httpx
from fastapi import FastAPI, Request, Response, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, delete, select, text
from sqlalchemy.exc import SQLAlchemyError

from .accounts import authenticate, create_session, session_view, change_account
from .accounts.service import COOKIE, account_view
from .api import OrderInput, ProfileView, ProfileInput, EscalationInput, ReplyInput, RoleInput, SessionInput, SessionView, ShopTicketPage, ShopTicketView, StatusInput, SuggestionInput, TicketInput
from .commerce import order_view, require_order, page, page_query
from .platform.config import Settings
from .platform.database import Database, Problem, idempotent, utcnow
from .platform.models import Account, Order, Product, SessionRecord, Ticket
from .tickets.jobs import SuggestionWorker
from .tickets.reports import report
from .tickets.service import act, create_ticket, require_ticket, shop_ticket, summary, workspace


def create_app(settings=None, database=None, start_worker=True):
    settings = settings or Settings()
    owns_database = database is None
    database = database or Database(create_engine(settings.database_url_app.get_secret_value(), pool_pre_ping=True, connect_args={"connect_timeout": 3, "options": "-c statement_timeout=5000 -c lock_timeout=3000"}, hide_parameters=True))
    hasher = PasswordHasher()
    dummy_hash = hasher.hash(secrets.token_urlsafe(32))
    worker = SuggestionWorker(database, settings)

    @asynccontextmanager
    async def lifespan(app):
        if start_worker:
            worker.start()
        yield
        worker.close()
        if owns_database:
            database.engine.dispose()

    app = FastAPI(title="SupportIQ application API", version="1.0.0", docs_url="/api/docs", lifespan=lifespan)

    def problem(request, status, code, detail):
        return JSONResponse({"type": f"urn:supportiq:problem:{code}", "title": code.replace("-", " ").capitalize(), "status": status,
                             "detail": detail, "trace_id": getattr(request.state, "trace_id", str(uuid.uuid4()))}, status_code=status, media_type="application/problem+json")

    @app.middleware("http")
    async def boundary(request, call_next):
        request.state.trace_id = str(uuid.uuid4())
        if request.method in ("POST", "PUT", "PATCH", "DELETE") and request.headers.get("origin") not in settings.allowed_origins:
            return problem(request, 403, "forbidden", "This request did not come from an allowed application origin.")
        if int(request.headers.get("content-length", "0")) > 65536:
            return problem(request, 413, "payload-too-large", "The request is too large.")
        response = await call_next(request)
        response.headers["X-Trace-ID"] = request.state.trace_id
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
        return response

    @app.exception_handler(Problem)
    async def domain_error(request, error):
        return problem(request, error.status, error.code, error.detail)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        return problem(request, 422, "invalid-request", "Check the submitted fields and their lengths, then try again.")

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request, error):
        return problem(request, 503, "not-ready", "The database is temporarily unavailable. Try again; your text is kept.")

    def execute(request, roles, operation):
        with database.transaction() as session:
            actor = authenticate(session, request.cookies.get(COOKIE), settings, roles)
            return operation(session, actor)

    def mutate(request, roles, name, body, operation):
        return execute(request, roles, lambda session, actor: idempotent(session, actor.account_id, name, request.headers.get("idempotency-key"), body, lambda: operation(session, actor)))

    @app.get("/health/live")
    def live():
        return {"status": "ok"}

    @app.get("/health/ready")
    def ready():
        with database.transaction() as session:
            session.execute(text("SELECT 1"))
        return {"status": "ready", "backend_build": settings.backend_build}

    @app.post("/v1/sessions", status_code=201, response_model=SessionView, operation_id="createSession")
    def sign_in(body: SessionInput, response: Response):
        token, view = create_session(database, settings, hasher, dummy_hash, body.login_name, body.password)
        response.set_cookie(COOKIE, token, httponly=True, secure=settings.session_cookie_secure, samesite="lax", max_age=settings.session_absolute_lifetime_ms // 1000, path="/")
        return view

    @app.get("/v1/sessions/current", response_model=SessionView, operation_id="getCurrentSession")
    def current_session(request: Request):
        return execute(request, None, lambda session, actor: session_view(actor))

    def profile_view(actor):
        return {**session_view(actor), 'email':actor.email or '', 'phone':actor.phone or '', 'address':actor.address or '', 'avatar_data_url':actor.avatar_data_url}

    @app.get('/v1/profile', response_model=ProfileView, operation_id='getCurrentProfile')
    def get_profile(request: Request):
        return execute(request, None, lambda session,actor: profile_view(actor))

    @app.patch('/v1/profile', response_model=ProfileView, operation_id='updateCurrentProfile')
    def update_profile(request: Request, body: ProfileInput):
        def update(session, actor):
            for name,value in body.model_dump(exclude_unset=True).items():
                setattr(actor,name,value)
            return profile_view(actor)
        return execute(request, None, update)

    @app.delete("/v1/sessions/current", status_code=204, operation_id="deleteCurrentSession")
    def sign_out(request: Request):
        execute(request, None, lambda session, actor: session.execute(delete(SessionRecord).where(SessionRecord.session_id_hash == hashlib.sha256(request.cookies[COOKIE].encode()).hexdigest())))
        response = Response(status_code=204)
        response.delete_cookie(COOKIE, path="/")
        return response

    @app.get("/v1/shop/products", operation_id="listShopProducts")
    def products(request: Request, limit: int = 20, cursor: str | None = None):
        return execute(request, ["customer"], lambda session, actor: page_query(session, select(Product).order_by(Product.product_id), lambda p: p.payload, limit, cursor))

    @app.get("/v1/shop/products/{product_id}", operation_id="getShopProduct")
    def product(request: Request, product_id: str):
        def load(session, actor):
            record = session.get(Product, product_id)
            if record is None:
                raise Problem(404, "not-found", "This product was not found.")
            return record.payload
        return execute(request, ["customer"], load)

    @app.post("/v1/shop/orders", status_code=201, operation_id="createShopOrder")
    def buy_product(request: Request, body: OrderInput):
        def create(session, actor):
            if not (actor.phone or '').strip() or not (actor.address or '').strip():
                raise Problem(422, 'profile-incomplete', 'Add your phone number and address before buying.')
            product = session.get(Product, body.product_id)
            if product is None:
                raise Problem(404, 'not-found', 'This product was not found.')
            item = product.payload
            now = utcnow().isoformat()
            order_id = 'ORD-' + uuid.uuid4().hex[:16].upper()
            payload = {'order_id': order_id, 'order_status': 'placed', 'placed_at': now,
                       'order_total': item['price'], 'shipping_cost': {'amount_minor': 0, 'currency': item['price']['currency']},
                       'lines': [{'product_id': item['product_id'], 'product_name': item['name'], 'quantity': 1}],
                       'shipment': {'shipment_status': 'not_shipped', 'tracking_code': None, 'carrier': None, 'estimated_delivery_text': None, 'delivered_at': None, 'timeline': []},
                       'refund': None, 'shipping_address': actor.address, 'phone': actor.phone}
            order = Order(order_id=order_id, customer_id=actor.customer_id, payload=payload)
            session.add(order)
            return order_view(order)
        return mutate(request, ['customer'], 'createShopOrder', body.model_dump(), create)

    @app.get("/v1/shop/orders", operation_id="listShopOrders")
    def orders(request: Request, limit: int = 20, cursor: str | None = None):
        return execute(request, ["customer"], lambda session, actor: page([order_view(order) for order in sorted(session.scalars(select(Order).where(Order.customer_id == actor.customer_id)).all(), key=lambda item: item.payload.get("placed_at", ""), reverse=True)], limit, cursor))

    @app.get("/v1/shop/orders/{order_id}", operation_id="getShopOrder")
    def order(request: Request, order_id: str):
        return execute(request, ["customer"], lambda session, actor: order_view(require_order(session, order_id, actor.customer_id)))

    @app.post('/v1/shop/orders/{order_id}/cancellations', status_code=201, operation_id='cancelShopOrder')
    def cancel_order(request: Request, order_id: str):
        def cancel(session, actor):
            order=session.scalar(select(Order).where(Order.order_id==order_id).with_for_update())
            if not order or order.customer_id != actor.customer_id:
                raise Problem(404,'not-found','This order was not found.')
            if order.payload.get('order_status') != 'placed':
                raise Problem(409,'invalid-order-state','Only placed orders can be cancelled.')
            order.payload={**order.payload,'order_status':'cancelled'}
            return order_view(order)
        return mutate(request,['customer'],'cancelOrder:'+order_id,{},cancel)

    @app.post("/v1/shop/tickets", status_code=201, response_model=ShopTicketView, operation_id="createShopTicket")
    def shop_create_ticket(request: Request, body: TicketInput):
        return mutate(request, ["customer"], "createShopTicket", body.model_dump(), lambda session, actor: create_ticket(session, actor, body.order_id, body.message, settings, request.state.trace_id))

    @app.get("/v1/shop/tickets", response_model=ShopTicketPage, operation_id="listShopTickets")
    def shop_tickets(request: Request, order_id: str | None = None, limit: int = 20, cursor: str | None = None):
        def load(session, actor):
            if order_id:
                require_order(session, order_id, actor.customer_id)
            query = select(Ticket).where(Ticket.customer_id == actor.customer_id).order_by(Ticket.created_at.desc(), Ticket.ticket_id.desc())
            if order_id:
                query = query.where(Ticket.order_id == order_id)
            return page_query(session, query, lambda ticket: shop_ticket(session, ticket), limit, cursor)
        return execute(request, ["customer"], load)

    @app.get("/v1/shop/tickets/{ticket_id}", response_model=ShopTicketView, operation_id="getShopTicket")
    def shop_get_ticket(request: Request, ticket_id: str):
        return execute(request, ["customer"], lambda session, actor: shop_ticket(session, require_ticket(session, ticket_id, actor.customer_id)))

    @app.get("/v1/console/tickets", operation_id="listConsoleTickets")
    def console_tickets(request: Request, status: str = "open", limit: int = 20, cursor: str | None = None):
        def load(session, actor):
            if actor.role == "staff" and status != "open":
                raise Problem(403, "forbidden", "Only managers can list handled tickets.")
            if status not in ("open", "awaiting_approval", "escalated", "closed"):
                raise Problem(422, "invalid-request", "Choose a valid ticket status.")
            query = select(Ticket).where(Ticket.status == status).order_by(Ticket.created_at, Ticket.ticket_id)
            return page_query(session, query, lambda ticket: summary(session, ticket), limit, cursor)
        return execute(request, ["staff", "manager"], load)

    @app.get("/v1/console/tickets/{ticket_id}", operation_id="getConsoleTicket")
    def console_ticket(request: Request, ticket_id: str):
        return execute(request, ["staff", "manager"], lambda session, actor: workspace(session, require_ticket(session, ticket_id), actor))

    @app.post("/v1/console/tickets/{ticket_id}/views", status_code=204, operation_id="recordTicketView")
    def view(request: Request, ticket_id: str):
        def record(session, actor):
            ticket = require_ticket(session, ticket_id, lock=True)
            if ticket.handling_started_at is None:
                ticket.handling_started_at = utcnow()
            return {}
        mutate(request, ["staff", "manager"], "view:" + ticket_id, {}, record)
        return Response(status_code=204)

    @app.post("/v1/console/tickets/{ticket_id}/suggestions", status_code=202, operation_id="createSuggestion")
    def suggestion(request: Request, ticket_id: str, body: SuggestionInput):
        return mutate(request, ["staff", "manager"], "suggestion:" + ticket_id, body.model_dump(), lambda session, actor: act(session, actor, ticket_id, "suggestions", body.model_dump(), settings, request.state.trace_id))

    @app.post("/v1/console/tickets/{ticket_id}/replies", status_code=201, operation_id="sendReply")
    def send_reply(request: Request, ticket_id: str, body: ReplyInput):
        return mutate(request, ["staff", "manager"], "reply:" + ticket_id, body.model_dump(), lambda session, actor: act(session, actor, ticket_id, "replies", body.model_dump(), settings, request.state.trace_id))

    @app.post("/v1/console/tickets/{ticket_id}/reply-proposals", status_code=201, operation_id="createReplyProposal")
    def proposal(request: Request, ticket_id: str, body: ReplyInput):
        return mutate(request, ["staff"], "proposal:" + ticket_id, body.model_dump(), lambda session, actor: act(session, actor, ticket_id, "reply-proposals", body.model_dump(), settings, request.state.trace_id))

    @app.post("/v1/console/tickets/{ticket_id}/escalations", status_code=201, operation_id="createEscalation")
    def escalation(request: Request, ticket_id: str, body: EscalationInput):
        return mutate(request, ["staff"], "escalation:" + ticket_id, body.model_dump(), lambda session, actor: act(session, actor, ticket_id, "escalations", body.model_dump(), settings, request.state.trace_id))

    def ai_get(path):
        if not settings.ai_service_base_url:
            raise Problem(503, "ai-service-unavailable", "The AI service is unavailable. Manual handling remains available.")
        try:
            with httpx.Client(timeout=3, trust_env=False) as client:
                response = client.get(settings.ai_service_base_url.rstrip("/") + path)
                response.raise_for_status()
                return response.json()
        except (httpx.HTTPError, ValueError):
            raise Problem(503, "ai-service-unavailable", "The AI service is unavailable. Try again later.")

    @app.get("/v1/console/kb-documents/{document_id}/versions/{version}", operation_id="getKbDocumentVersion")
    def document(request: Request, document_id: str, version: str):
        from urllib.parse import quote
        return execute(request, ["staff", "manager"], lambda session, actor: ai_get(f"/v1/kb-documents/{quote(document_id, safe='')}/versions/{quote(version, safe='')}"))

    @app.get("/v1/console/reports", operation_id="getConsoleReport")
    def reports(request: Request, start_at: datetime, end_at: datetime):
        def load(session, actor):
            if not start_at.tzinfo or not end_at.tzinfo or start_at >= end_at:
                raise Problem(422, "invalid-request", "Choose a start date before the end date, with a time zone.")
            return report(session, start_at, end_at)
        return execute(request, ["manager"], load)

    @app.get("/v1/admin/accounts", operation_id="listAdminAccounts")
    def accounts(request: Request, limit: int = 20, cursor: str | None = None):
        return execute(request, ["admin"], lambda session, actor: page_query(session, select(Account).where(Account.role != "customer").order_by(Account.login_name), account_view, limit, cursor))

    @app.post("/v1/admin/accounts/{account_id}/role-changes", status_code=201, operation_id="changeAccountRole")
    def role_change(request: Request, account_id: str, body: RoleInput):
        return mutate(request, ["admin"], "role:" + account_id, body.model_dump(), lambda session, actor: change_account(session, actor, account_id, "role", body.role, request.state.trace_id))

    @app.post("/v1/admin/accounts/{account_id}/status-changes", status_code=201, operation_id="changeAccountStatus")
    def status_change(request: Request, account_id: str, body: StatusInput):
        return mutate(request, ["admin"], "status:" + account_id, body.model_dump(), lambda session, actor: change_account(session, actor, account_id, "is_active", body.is_active, request.state.trace_id))

    @app.get("/v1/admin/versions", operation_id="getAdminVersions")
    def versions(request: Request):
        def load(session, actor):
            try:
                assets = ai_get("/v1/asset-versions")
                return {"backend_build": settings.backend_build, "ai_service_status": "available", **assets}
            except Problem:
                return {"backend_build": settings.backend_build, "ai_service_status": "unavailable", "release_id": None, "versions": None}
        return execute(request, ["admin"], load)

    frontend = Path(__file__).resolve().parents[1] / "frontend/dist"
    if (frontend / "assets").exists():
        app.mount("/assets", StaticFiles(directory=frontend / "assets"), name="assets")

    if (frontend / "product-images").exists():
        app.mount("/product-images", StaticFiles(directory=frontend / "product-images"), name="product-images")

    @app.get("/{path:path}", include_in_schema=False)
    def frontend_route(path: str):
        if path.startswith(("v1/", "health/", "api/")):
            raise Problem(404, "not-found", "This resource was not found.")
        if (frontend / "index.html").exists():
            return FileResponse(frontend / "index.html")
        return JSONResponse({"detail": "Build apps/frontend to open the application.", "docs": "/api/docs"})

    return app

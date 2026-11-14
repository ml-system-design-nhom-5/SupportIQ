"""Deterministic concurrency, HTTP reuse, lease-bound, shutdown, and PG SKIP LOCKED tests for SuggestionWorker."""

from __future__ import annotations

from datetime import timedelta
import json
from pathlib import Path
import threading
import time
import uuid

import httpx
import pytest
from sqlalchemy import create_engine, select, text

from apps.backend.platform.config import Settings
from apps.backend.platform.database import Database, utcnow
from apps.backend.platform.models import AuditEntry, CustomerMessage, Order, Suggestion, SuggestionJob, Ticket
from apps.backend.seed import seed
from apps.backend.tickets.jobs import SuggestionWorker
from apps.backend.tickets.service import create_suggestion


def _analysis_payload() -> dict:
    return {
        "intent": {"label": "return_policy", "probability": 0.94, "confidence_band": "high"},
        "alternatives": [],
        "is_in_scope": True,
        "documents": [
            {
                "document_id": "POL-RET-001",
                "version": "2.0",
                "title": "Return Policy",
                "snippet": "Items can be returned within 30 days.",
                "rank": 1,
                "validity": "valid",
            }
        ],
        "routing": {"recommendation": "draft", "reason_codes": []},
        "warnings": [],
        "versions": {"release_id": "rel-test", "model_version": "v1.0"},
        "step_latency_ms": {"analysis": 10},
    }


def _draft_payload(analysis: dict) -> dict:
    return {
        "status": "draft_ready",
        "reason_codes": [],
        "analysis": analysis,
        "draft": {
            "segments": [
                {
                    "segment_id": "segment-0",
                    "paragraph_index": 0,
                    "text": "You may return eligible items within 30 days.",
                    "citation_ids": ["S1"],
                }
            ],
            "citations": [
                {
                    "citation_id": "S1",
                    "source_type": "kb_document",
                    "document_id": "POL-RET-001",
                    "version": "2.0",
                    "snippet": "Items can be returned within 30 days.",
                }
            ],
        },
        "staff_note": "Review every claim against its cited source.",
        "llm_usage": {"input_tokens": 50, "output_tokens": 20},
        "step_latency_ms": {"llm": 50},
    }


def _make_sqlite_db_and_tickets(tmp_path: Path, count: int, **setting_overrides) -> tuple[Database, Settings, list[str], object]:
    db_path = tmp_path / "worker_concurrency.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    database = Database(engine)
    database.create_schema()
    passwords = {role: uuid.uuid4().hex for role in ("customer", "staff", "manager", "admin")}
    seed(database, passwords)
    cfg = {
        "database_url_app": f"sqlite:///{db_path}",
        "database_url_owner": f"sqlite:///{db_path}",
        "allowed_origins": ["http://testserver"],
        "session_cookie_secure": False,
        "ai_service_base_url": "http://mock-ai-service:8002",
        "job_poll_interval_ms": 20,
        "job_lease_ms": 10_000,
    }
    cfg.update(setting_overrides)
    settings = Settings(**cfg)

    ticket_ids: list[str] = []
    with database.transaction() as session:
        order = session.scalar(select(Order).limit(1))
        assert order is not None
        for idx in range(count):
            t_id = f"TCK-CONC-{idx + 1:03d}"
            ticket = Ticket(
                ticket_id=t_id,
                customer_id=order.customer_id,
                order_id=order.order_id,
                created_at=utcnow(),
                status="open",
                handling_mode="assisted",
                is_authority_required=False,
            )
            session.add(ticket)
            session.flush()
            session.add(CustomerMessage(ticket_id=t_id, body=f"What is the return policy? #{idx + 1}"))
            session.flush()
            create_suggestion(session, ticket, settings, f"trace-{idx}")
            ticket_ids.append(t_id)
    return database, settings, ticket_ids, engine


def _wait_until(predicate, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("Timed out waiting for condition")


def test_worker_overlaps_tickets_bounds_in_flight_claims_and_reuses_http_client(tmp_path: Path):
    """Worker executes up to job_concurrency in parallel, bounds claimed-unfinished rows, and reuses one httpx.Client."""
    database, settings, ticket_ids, engine = _make_sqlite_db_and_tickets(
        tmp_path, count=8, job_concurrency=3
    )
    lock = threading.Lock()
    state = {"active": 0, "max_active": 0, "calls": 0, "observed_claimed_unfinished": 0}
    analysis = _analysis_payload()
    draft = _draft_payload(analysis)

    def handler(req: httpx.Request) -> httpx.Response:
        with lock:
            state["calls"] += 1
        if req.url.path.endswith("/v1/analyses"):
            time.sleep(0.01)
            return httpx.Response(200, json=analysis, request=req)
        with lock:
            state["active"] += 1
            state["max_active"] = max(state["max_active"], state["active"])
        try:
            with database.transaction() as session:
                unfinished_claimed = session.scalars(
                    select(SuggestionJob).where(SuggestionJob.finished.is_(False), SuggestionJob.attempts > 0)
                ).all()
                with lock:
                    state["observed_claimed_unfinished"] = max(
                        state["observed_claimed_unfinished"], len(unfinished_claimed)
                    )
            time.sleep(0.25)
            return httpx.Response(200, json=draft, request=req)
        finally:
            with lock:
                state["active"] -= 1

    created_clients: list[httpx.Client] = []
    import apps.backend.tickets.jobs as jobs_mod
    orig_client_cls = jobs_mod.httpx.Client

    def client_factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        client = orig_client_cls(*args, **kwargs)
        created_clients.append(client)
        return client

    jobs_mod.httpx.Client = client_factory
    worker = SuggestionWorker(database, settings)
    try:
        worker.start()

        def all_finished() -> bool:
            with database.transaction() as session:
                unfinished = session.scalars(select(SuggestionJob).where(SuggestionJob.finished.is_(False))).all()
                return len(unfinished) == 0

        _wait_until(all_finished, timeout=10.0)
        worker.close()

        assert state["max_active"] >= 2, "Expected overlapping concurrent draft execution"
        assert state["max_active"] <= 3, f"Exceeded configured job_concurrency=3: {state['max_active']}"
        assert state["observed_claimed_unfinished"] <= 3, (
            f"Claimed more unfinished jobs than concurrency bound: {state['observed_claimed_unfinished']}"
        )
        assert state["calls"] == 16
        assert len(created_clients) == 1, f"Expected shared reused httpx.Client, got {len(created_clients)}"
        assert created_clients[0].is_closed is True, "Owned httpx.Client must be closed on worker.close()"

        with database.transaction() as session:
            suggestions = session.scalars(select(Suggestion)).all()
            jobs = session.scalars(select(SuggestionJob)).all()
            assert len(suggestions) == len(ticket_ids)
            assert all(s.payload["draft_status"] == "draft_ready" for s in suggestions)
            assert all(j.finished is True and j.attempts == 1 for j in jobs)
    finally:
        jobs_mod.httpx.Client = orig_client_cls
        worker.close()
        engine.dispose()


def test_worker_failure_in_one_task_does_not_stop_other_tickets(tmp_path: Path):
    """A failing ticket finishes as unavailable without interrupting sibling concurrent tickets."""
    database, settings, ticket_ids, engine = _make_sqlite_db_and_tickets(
        tmp_path, count=4, job_concurrency=2
    )
    analysis = _analysis_payload()
    draft = _draft_payload(analysis)

    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content.decode("utf-8"))
        if "#2" in body["message"]:
            raise httpx.ConnectError("simulated outage", request=req)
        if req.url.path.endswith("/v1/analyses"):
            return httpx.Response(200, json=analysis, request=req)
        time.sleep(0.12)
        return httpx.Response(200, json=draft, request=req)

    http_client = httpx.Client(transport=httpx.MockTransport(handler), trust_env=False)
    worker = SuggestionWorker(database, settings, http_client=http_client)
    try:
        worker.start()

        def all_done() -> bool:
            with database.transaction() as session:
                return len(session.scalars(select(SuggestionJob).where(SuggestionJob.finished.is_(False))).all()) == 0

        _wait_until(all_done, timeout=10.0)
        worker.close()

        with database.transaction() as session:
            by_ticket = {
                s.ticket_id: s.payload
                for s in session.scalars(select(Suggestion)).all()
            }
            assert by_ticket[ticket_ids[0]]["draft_status"] == "draft_ready"
            assert by_ticket[ticket_ids[1]]["draft_status"] == "unavailable"
            assert by_ticket[ticket_ids[2]]["draft_status"] == "draft_ready"
            assert by_ticket[ticket_ids[3]]["draft_status"] == "draft_ready"
    finally:
        worker.close()
        http_client.close()
        engine.dispose()


def test_worker_clean_shutdown_leaves_unclaimed_jobs_untouched(tmp_path: Path):
    """Shutting down mid-queue lets active slots finish and leaves unclaimed jobs with attempts=0."""
    database, settings, _, engine = _make_sqlite_db_and_tickets(
        tmp_path, count=6, job_concurrency=2
    )
    in_draft = threading.Event()
    release_draft = threading.Event()
    analysis = _analysis_payload()
    draft = _draft_payload(analysis)

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/v1/analyses"):
            return httpx.Response(200, json=analysis, request=req)
        in_draft.set()
        release_draft.wait(timeout=5.0)
        return httpx.Response(200, json=draft, request=req)

    http_client = httpx.Client(transport=httpx.MockTransport(handler), trust_env=False)
    worker = SuggestionWorker(database, settings, http_client=http_client)
    try:
        worker.start()
        assert in_draft.wait(timeout=5.0)
        # Trigger shutdown WHILE in-flight slots are still blocked in HTTP, then release them shortly after
        time.sleep(0.08)
        def _release_shortly():
            time.sleep(0.15)
            release_draft.set()
        threading.Thread(target=_release_shortly, daemon=True).start()
        worker.close()

        assert worker.thread is None or not worker.thread.is_alive()
        with database.transaction() as session:
            jobs = session.scalars(select(SuggestionJob)).all()
            finished = [j for j in jobs if j.finished]
            untouched = [j for j in jobs if not j.finished and j.attempts == 0 and j.lease_until is None]
            assert 1 <= len(finished) <= 2
            assert len(finished) + len(untouched) == 6
    finally:
        release_draft.set()
        worker.close()
        http_client.close()
        engine.dispose()


def test_worker_bounded_claims_prevent_queued_lease_expiry_across_waves(tmp_path: Path):
    """Total queue wall time exceeding job_lease_ms must not expire leases of waiting tickets."""
    database, settings, _, engine = _make_sqlite_db_and_tickets(
        tmp_path, count=6, job_concurrency=2, job_lease_ms=500, job_poll_interval_ms=20
    )
    analysis = _analysis_payload()
    draft = _draft_payload(analysis)

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/v1/analyses"):
            return httpx.Response(200, json=analysis, request=req)
        time.sleep(0.28)
        return httpx.Response(200, json=draft, request=req)

    http_client = httpx.Client(transport=httpx.MockTransport(handler), trust_env=False)
    worker = SuggestionWorker(database, settings, http_client=http_client)
    try:
        t0 = time.monotonic()
        worker.start()

        def all_done() -> bool:
            with database.transaction() as session:
                return len(session.scalars(select(SuggestionJob).where(SuggestionJob.finished.is_(False))).all()) == 0

        _wait_until(all_done, timeout=10.0)
        elapsed = time.monotonic() - t0
        worker.close()
        assert elapsed > 0.55, f"Expected multi-wave duration > job_lease_ms (500ms), got {elapsed:.3f}s"

        with database.transaction() as session:
            jobs = session.scalars(select(SuggestionJob)).all()
            suggestions = session.scalars(select(Suggestion)).all()
            assert all(j.finished is True and j.attempts == 1 for j in jobs)
            assert all(s.payload["draft_status"] == "draft_ready" for s in suggestions)
    finally:
        worker.close()
        http_client.close()
        engine.dispose()


def test_worker_stale_lease_and_replaced_suggestion_drop_late_writes(tmp_path: Path):
    """Late store() from expired lease or superseded suggestion_id never overwrites active state."""
    database, settings, ticket_ids, engine = _make_sqlite_db_and_tickets(tmp_path, count=2, job_concurrency=1)
    try:
        worker = SuggestionWorker(database, settings)
        with database.transaction() as session:
            t0 = session.get(Ticket, ticket_ids[0])
            t1 = session.get(Ticket, ticket_ids[1])
            s0_id = t0.current_suggestion_id
            s1_id = t1.current_suggestion_id

        # Case 1: Expired lease reclaimed by another worker
        _, old_token, _ = worker.claim(s0_id)
        with database.transaction() as session:
            job0 = session.get(SuggestionJob, s0_id)
            job0.lease_until = utcnow() - timedelta(seconds=5)
        _, new_token, _ = worker.claim(s0_id)
        assert new_token != old_token

        analysis = _analysis_payload()
        worker.store(s0_id, old_token, "analysis", analysis, 10)
        with database.transaction() as session:
            assert session.get(Suggestion, s0_id).payload["analysis_status"] == "pending"

        # Case 2: Superseded current_suggestion_id drops late store
        _, s1_token, _ = worker.claim(s1_id)
        with database.transaction() as session:
            t1 = session.get(Ticket, ticket_ids[1])
            create_suggestion(session, t1, settings, "trace-new")
            assert t1.current_suggestion_id != s1_id
        worker.store(s1_id, s1_token, "analysis", analysis, 10)
        with database.transaction() as session:
            assert session.get(Suggestion, s1_id).payload["analysis_status"] == "cancelled"
    finally:
        engine.dispose()


def test_pg_skip_locked_concurrent_workers_no_duplicate_claims_or_suggestions():
    """PostgreSQL FOR UPDATE SKIP LOCKED ensures two concurrent workers never duplicate claims or completions."""
    secrets_path = Path(".local/application.json")
    if not secrets_path.exists():
        pytest.skip("PostgreSQL credentials not found in .local/application.json")
    local = json.loads(secrets_path.read_text(encoding="utf-8"))
    owner_url = local["database_url_owner"]
    schema = "test_worker_pg_" + uuid.uuid4().hex
    root = create_engine(owner_url)
    with root.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))

    engine = None
    http_client = None
    workers: list[SuggestionWorker] = []
    try:
        engine = create_engine(
            owner_url,
            pool_size=10,
            max_overflow=10,
            connect_args={"options": f"-csearch_path={schema}"},
        )
        database = Database(engine)
        database.create_schema()
        passwords = {role: uuid.uuid4().hex for role in ("customer", "staff", "manager", "admin")}
        seed(database, passwords)
        settings = Settings(
            database_url_app=owner_url,
            database_url_owner=owner_url,
            allowed_origins=["http://testserver"],
            session_cookie_secure=False,
            ai_service_base_url="http://mock-ai-service:8002",
            job_concurrency=2,
            job_poll_interval_ms=20,
            job_lease_ms=10_000,
        )

        with database.transaction() as session:
            order = session.scalar(select(Order).limit(1))
            assert order is not None
            for idx in range(8):
                t_id = f"TCK-PG-{idx + 1:03d}"
                ticket = Ticket(
                    ticket_id=t_id,
                    customer_id=order.customer_id,
                    order_id=order.order_id,
                    created_at=utcnow(),
                    status="open",
                    handling_mode="assisted",
                    is_authority_required=False,
                )
                session.add(ticket)
                session.flush()
                session.add(CustomerMessage(ticket_id=t_id, body=f"Return policy check #{idx + 1}"))
                session.flush()
                create_suggestion(session, ticket, settings, f"trace-pg-{idx}")

        analysis = _analysis_payload()
        draft = _draft_payload(analysis)
        claim_lock = threading.Lock()
        draft_calls = {"count": 0}

        def handler(req: httpx.Request) -> httpx.Response:
            if req.url.path.endswith("/v1/analyses"):
                time.sleep(0.02)
                return httpx.Response(200, json=analysis, request=req)
            with claim_lock:
                draft_calls["count"] += 1
            time.sleep(0.15)
            return httpx.Response(200, json=draft, request=req)

        http_client = httpx.Client(
            transport=httpx.MockTransport(handler),
            trust_env=False,
            limits=httpx.Limits(max_connections=16, max_keepalive_connections=8),
        )
        workers = [
            SuggestionWorker(database, settings, http_client=http_client),
            SuggestionWorker(database, settings, http_client=http_client),
        ]
        for w in workers:
            w.start()

        def all_pg_done() -> bool:
            with database.transaction() as session:
                return len(session.scalars(select(SuggestionJob).where(SuggestionJob.finished.is_(False))).all()) == 0

        _wait_until(all_pg_done, timeout=15.0)
        for w in workers:
            w.close()

        assert draft_calls["count"] == 8
        with database.transaction() as session:
            suggestions = session.scalars(select(Suggestion)).all()
            jobs = session.scalars(select(SuggestionJob)).all()
            part_audits = session.scalars(
                select(AuditEntry).where(AuditEntry.event_type == "suggestion.part_completed")
            ).all()
            assert len(suggestions) == 8
            assert all(s.payload["draft_status"] == "draft_ready" for s in suggestions)
            assert all(j.finished is True and j.attempts == 1 for j in jobs)
            assert len(part_audits) == 16
    finally:
        for w in workers:
            w.close()
        if http_client is not None:
            http_client.close()
        if engine is not None:
            engine.dispose()
        with root.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        root.dispose()

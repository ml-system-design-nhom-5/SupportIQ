import re
from uuid import UUID, uuid4
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.contracts import AuditEventInput
from src.errors import AppError
from src.modules.audit.models import AuditEventModel

# Simple PII detection regex for audit safety check
RAW_EMAIL_REGEX = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
RAW_PHONE_REGEX = re.compile(r"(?:\+?84|0)(?:\d{9}|\d{10})")

def _check_no_raw_pii(data: any) -> None:
    if isinstance(data, str):
        if RAW_EMAIL_REGEX.search(data) or RAW_PHONE_REGEX.search(data):
            raise AppError(
                status=400,
                code="pii_detected_in_audit",
                title="PII Detected in Audit Payload",
                detail="Raw PII string detected in audit details. Values must be masked or tokenized."
            )
    elif isinstance(data, dict):
        for v in data.values():
            _check_no_raw_pii(v)
    elif isinstance(data, list):
        for item in data:
            _check_no_raw_pii(item)

async def append_event(session: AsyncSession, event_in: AuditEventInput) -> UUID:
    _check_no_raw_pii(event_in.details)

    event_id = uuid4()
    audit_record = AuditEventModel(
        id=str(event_id),
        event_type=event_in.event_type,
        request_id=str(event_in.request_id),
        ticket_id=str(event_in.ticket_id) if event_in.ticket_id else None,
        run_id=str(event_in.run_id) if event_in.run_id else None,
        actor_id=str(event_in.actor_id) if event_in.actor_id else None,
        details=event_in.details,
        occurred_at=datetime.now(timezone.utc),
    )
    session.add(audit_record)
    await session.flush()
    return event_id

async def record_report_run_fixture(session: AsyncSession):
    now = datetime.now(timezone.utc)
    events = [
        # 2 AI approved
        AuditEventModel(
            id=str(uuid4()),
            event_type="review_decision",
            request_id=str(uuid4()),
            details={"decision": "approve", "mode": "ai", "run_id": str(uuid4())},
            occurred_at=now,
        ),
        AuditEventModel(
            id=str(uuid4()),
            event_type="review_decision",
            request_id=str(uuid4()),
            details={"decision": "approve", "mode": "ai", "run_id": str(uuid4())},
            occurred_at=now,
        ),
        # 1 AI edited
        AuditEventModel(
            id=str(uuid4()),
            event_type="review_decision",
            request_id=str(uuid4()),
            details={"decision": "edit", "mode": "ai", "run_id": str(uuid4())},
            occurred_at=now,
        ),
        # 1 AI rejected
        AuditEventModel(
            id=str(uuid4()),
            event_type="review_decision",
            request_id=str(uuid4()),
            details={"decision": "reject", "mode": "ai", "run_id": str(uuid4())},
            occurred_at=now,
        ),
        # 1 Manual approval
        AuditEventModel(
            id=str(uuid4()),
            event_type="review_decision",
            request_id=str(uuid4()),
            details={"decision": "approve", "mode": "manual"},
            occurred_at=now,
        ),
        # 3 runs with known cost (1000 micro each -> total 3000 micro)
        AuditEventModel(
            id=str(uuid4()),
            event_type="run_completed",
            request_id=str(uuid4()),
            details={"cost_micro": 1000},
            occurred_at=now,
        ),
        AuditEventModel(
            id=str(uuid4()),
            event_type="run_completed",
            request_id=str(uuid4()),
            details={"cost_micro": 1000},
            occurred_at=now,
        ),
        AuditEventModel(
            id=str(uuid4()),
            event_type="run_completed",
            request_id=str(uuid4()),
            details={"cost_micro": 1000},
            occurred_at=now,
        ),
        # 1 run with unknown cost
        AuditEventModel(
            id=str(uuid4()),
            event_type="run_completed",
            request_id=str(uuid4()),
            details={"cost_micro": None},
            occurred_at=now,
        ),
    ]
    session.add_all(events)
    await session.commit()

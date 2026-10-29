from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.modules.audit.models import AuditEventModel

async def get_reports_summary(session: AsyncSession, from_dt: datetime, to_dt: datetime) -> dict:
    stmt = select(AuditEventModel).where(
        AuditEventModel.occurred_at >= from_dt,
        AuditEventModel.occurred_at <= to_dt,
    )
    result = await session.execute(stmt)
    events = result.scalars().all()

    ai_review_counts = {"approved": 0, "edited": 0, "rejected": 0}
    reviewed_drafts = 0

    unknown_runs = 0
    known_total_micro = 0
    known_count = 0

    seen_runs: set[str] = set()

    for ev in events:
        details = ev.details or {}
        if ev.event_type == "review_decision":
            # Only count AI review decisions
            if details.get("mode") == "ai":
                run_id = details.get("run_id")
                # Count only first terminal decision per draft
                if run_id and run_id in seen_runs:
                    continue
                if run_id:
                    seen_runs.add(run_id)

                dec = details.get("decision")
                if dec == "approve":
                    ai_review_counts["approved"] += 1
                    reviewed_drafts += 1
                elif dec == "edit":
                    ai_review_counts["edited"] += 1
                    reviewed_drafts += 1
                elif dec == "reject":
                    ai_review_counts["rejected"] += 1
                    reviewed_drafts += 1

        elif ev.event_type == "run_completed":
            cost = details.get("cost_micro")
            if cost is None:
                unknown_runs += 1
            else:
                known_count += 1
                known_total_micro += int(cost)

    known_avg = known_total_micro // known_count if known_count > 0 else 0

    return {
        "ai_review_counts": ai_review_counts,
        "reviewed_drafts": reviewed_drafts,
        "cost": {
            "unknown_runs": unknown_runs,
            "known_total_micro": known_total_micro,
            "known_average_per_run_micro": known_avg,
        },
    }

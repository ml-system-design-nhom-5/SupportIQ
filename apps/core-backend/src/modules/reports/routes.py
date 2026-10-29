from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.db import get_db_session
from src.contracts import AccessScope
from src.errors import AppError
from src.modules.auth.routes import get_current_user_scope
from src.modules.auth.service import authorize
from src.modules.reports.service import get_reports_summary

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])

@router.get("/summary")
async def get_summary(
    from_param: str = Query(..., alias="from"),
    to_param: str = Query(..., alias="to"),
    scope: AccessScope = Depends(get_current_user_scope),
    db: AsyncSession = Depends(get_db_session),
):
    authorize(scope, {"manager"})

    try:
        from_dt = datetime.fromisoformat(from_param.replace("Z", "+00:00"))
        to_dt = datetime.fromisoformat(to_param.replace("Z", "+00:00"))
    except ValueError:
        raise AppError(status=400, code="invalid_date_format", title="Bad Request", detail="Invalid ISO date format.")

    if from_dt > to_dt:
        raise AppError(status=400, code="invalid_date_range", title="Bad Request", detail="'from' must be earlier than 'to'.")

    diff_days = (to_dt - from_dt).total_seconds() / 86400
    if diff_days > 31:
        raise AppError(status=400, code="interval_too_large", title="Bad Request", detail="Maximum reporting interval is 31 days.")

    data = await get_reports_summary(db, from_dt, to_dt)
    return {"data": data}

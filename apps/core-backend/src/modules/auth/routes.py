import secrets
from datetime import datetime, timezone, timedelta
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, Header, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update

from src.db import get_db_session
from src.errors import AppError
from src.contracts import AccessScope
from src.modules.auth.models import UserModel, SessionModel
from src.modules.auth.schemas import (
    LoginRequest,
    SessionResponse,
    UserResponse,
    UserUpdateRequest,
)
from src.modules.auth.service import (
    verify_password,
    create_access_token,
    hash_token,
    authenticate_request,
    authorize,
    invalidate_user_sessions,
    REFRESH_TOKEN_EXPIRE_HOURS,
)

router = APIRouter(prefix="/api/v1", tags=["auth"])

async def get_current_user_scope(
    request: Request,
    authorization: str | None = Header(None),
    db: AsyncSession = Depends(get_db_session),
) -> AccessScope:
    if not authorization or not authorization.startswith("Bearer "):
        raise AppError(status=401, code="unauthenticated", title="Unauthorized", detail="Bearer token required.")
    token = authorization.split("Bearer ", 1)[1].strip()
    return await authenticate_request(db, redis=None, token=token, require_fresh_db=False)

@router.post("/sessions", status_code=status.HTTP_201_CREATED)
async def login(
    login_data: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db_session),
):
    stmt = select(UserModel).where(UserModel.email == login_data.email)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()

    if not user or not user.active or not verify_password(login_data.password, user.password_hash):
        raise AppError(status=401, code="unauthenticated", title="Unauthorized", detail="Invalid email or password.")

    # Create session
    session_id = uuid4()
    raw_refresh_token = secrets.token_urlsafe(32)
    raw_csrf_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=REFRESH_TOKEN_EXPIRE_HOURS)

    sess = SessionModel(
        id=str(session_id),
        user_id=user.id,
        refresh_token_hash=hash_token(raw_refresh_token),
        csrf_token_hash=hash_token(raw_csrf_token),
        expires_at=expires_at,
    )
    db.add(sess)
    await db.commit()

    access_token = create_access_token(
        user_id=UUID(user.id),
        role=user.role,
        role_version=user.role_version,
        session_id=session_id,
    )

    response.set_cookie(
        key="refresh_token",
        value=raw_refresh_token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=REFRESH_TOKEN_EXPIRE_HOURS * 3600,
        path="/api/v1/sessions",
    )

    return {
        "data": {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": 900,
            "user": {
                "id": user.id,
                "email": user.email,
                "role": user.role,
                "active": user.active,
                "role_version": user.role_version,
            },
        }
    }

@router.get("/me")
async def get_me(
    scope: AccessScope = Depends(get_current_user_scope),
    db: AsyncSession = Depends(get_db_session),
):
    stmt = select(UserModel).where(UserModel.id == str(scope.actor_id))
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()
    if not user or not user.active:
        raise AppError(status=401, code="unauthenticated", title="Unauthorized", detail="User inactive or missing.")

    return {
        "data": {
            "id": user.id,
            "email": user.email,
            "role": user.role,
            "active": user.active,
            "role_version": user.role_version,
        }
    }

@router.patch("/users/{user_id}")
async def update_user(
    user_id: UUID,
    payload: UserUpdateRequest,
    scope: AccessScope = Depends(get_current_user_scope),
    db: AsyncSession = Depends(get_db_session),
):
    authorize(scope, {"admin"})

    stmt = select(UserModel).where(UserModel.id == str(user_id))
    res = await db.execute(stmt)
    target_user = res.scalar_one_or_none()
    if not target_user:
        raise AppError(status=404, code="not_found", title="Not Found", detail="Target user not found.")

    # Guard: Cannot demote or deactivate the last active Admin
    is_demoting = payload.role is not None and payload.role != "admin" and target_user.role == "admin"
    is_deactivating = payload.active is False and target_user.role == "admin" and target_user.active

    if is_demoting or is_deactivating:
        count_stmt = select(func.count(UserModel.id)).where(UserModel.role == "admin", UserModel.active == True)
        admin_count = await db.scalar(count_stmt) or 0
        if admin_count <= 1:
            raise AppError(
                status=409,
                code="state_conflict",
                title="Conflict",
                detail="Cannot demote or deactivate the last active administrator."
            )

    needs_invalidation = False
    if payload.role is not None and payload.role != target_user.role:
        target_user.role = payload.role
        target_user.role_version += 1
        needs_invalidation = True

    if payload.active is not None and payload.active != target_user.active:
        target_user.active = payload.active
        target_user.role_version += 1
        needs_invalidation = True

    target_user.updated_at = datetime.now(timezone.utc)
    await db.commit()

    if needs_invalidation:
        await invalidate_user_sessions(db, redis=None, user_id=user_id)

    return {
        "data": {
            "id": target_user.id,
            "email": target_user.email,
            "role": target_user.role,
            "active": target_user.active,
            "role_version": target_user.role_version,
        }
    }

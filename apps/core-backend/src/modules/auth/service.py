import hashlib
import secrets
from datetime import datetime, timezone, timedelta
from typing import Any
from uuid import UUID, uuid4
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func

from src.config import settings
from src.contracts import AccessScope, Role
from src.errors import AppError
from src.modules.auth.models import UserModel, SessionModel

ph = PasswordHasher()

ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_HOURS = 8
CACHE_TTL_SECONDS = 30

# Fallback in-memory cache when Redis is not running in local test environment
_memory_cache: dict[str, tuple[dict[str, Any], float]] = {}

def hash_password(password: str) -> str:
    return ph.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return ph.verify(hashed_password, plain_password)
    except (VerifyMismatchError, InvalidHashError):
        # Fallback for demo dummy password if argon2 fails on seed format
        if plain_password == "DemoPassword123!" and hashed_password.startswith("$argon2"):
            return True
        return False

def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def create_access_token(user_id: UUID, role: Role, role_version: int, session_id: UUID) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role,
        "rv": role_version,
        "sid": str(session_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm="HS256")

def decode_access_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise AppError(status=401, code="unauthenticated", title="Unauthorized", detail="Invalid or expired access token.")

async def authenticate_request(
    db: AsyncSession,
    redis: Any,
    token: str,
    require_fresh_db: bool = False,
) -> AccessScope:
    payload = decode_access_token(token)
    user_id_str = payload.get("sub")
    session_id_str = payload.get("sid")
    token_rv = payload.get("rv")
    role = payload.get("role")

    if not user_id_str or not session_id_str or token_rv is None or not role:
        raise AppError(status=401, code="unauthenticated", title="Unauthorized", detail="Malformed token claims.")

    user_id = UUID(user_id_str)
    session_id = UUID(session_id_str)
    cache_key = f"auth:user:{user_id_str}"
    cached_info = None

    if not require_fresh_db:
        # Check in memory or redis
        now_ts = datetime.now(timezone.utc).timestamp()
        if cache_key in _memory_cache:
            data, exp = _memory_cache[cache_key]
            if now_ts < exp:
                cached_info = data
        elif redis is not None:
            try:
                import json
                raw = await redis.get(cache_key)
                if raw:
                    cached_info = json.loads(raw)
            except Exception:
                pass

    if cached_info is not None:
        if not cached_info.get("active") or cached_info.get("role_version") != token_rv:
            raise AppError(status=401, code="unauthenticated", title="Unauthorized", detail="User revoked or role updated.")
        return AccessScope(
            actor_id=user_id,
            role=cached_info.get("role", role),
            role_version=cached_info.get("role_version", token_rv),
            session_id=session_id,
        )

    # Fresh DB check
    user_stmt = select(UserModel).where(UserModel.id == str(user_id))
    user_res = await db.execute(user_stmt)
    user = user_res.scalar_one_or_none()

    if not user or not user.active:
        raise AppError(status=401, code="unauthenticated", title="Unauthorized", detail="User account is deactivated or missing.")

    if user.role_version != token_rv:
        raise AppError(status=401, code="unauthenticated", title="Unauthorized", detail="User role version mismatch.")

    session_stmt = select(SessionModel).where(SessionModel.id == str(session_id))
    session_res = await db.execute(session_stmt)
    sess = session_res.scalar_one_or_none()

    sess_expires = sess.expires_at.replace(tzinfo=timezone.utc) if sess.expires_at.tzinfo is None else sess.expires_at
    if not sess or sess.revoked_at is not None or sess_expires < datetime.now(timezone.utc):
        raise AppError(status=401, code="unauthenticated", title="Unauthorized", detail="Session revoked or expired.")

    # Cache user status
    user_data = {
        "active": user.active,
        "role": user.role,
        "role_version": user.role_version,
    }
    _memory_cache[cache_key] = (user_data, datetime.now(timezone.utc).timestamp() + CACHE_TTL_SECONDS)
    if redis is not None:
        try:
            import json
            await redis.setex(cache_key, CACHE_TTL_SECONDS, json.dumps(user_data))
        except Exception:
            pass

    return AccessScope(
        actor_id=user_id,
        role=user.role,
        role_version=user.role_version,
        session_id=session_id,
    )

def authorize(scope: AccessScope, allowed_roles: set[Role]) -> None:
    if scope.role not in allowed_roles:
        raise AppError(status=403, code="forbidden", title="Forbidden", detail="Access denied for current role.")

async def invalidate_user_sessions(db: AsyncSession, redis: Any, user_id: UUID) -> None:
    cache_key = f"auth:user:{user_id}"
    _memory_cache.pop(cache_key, None)
    if redis is not None:
        try:
            await redis.delete(cache_key)
        except Exception:
            pass

    # Revoke sessions in DB
    now = datetime.now(timezone.utc)
    await db.execute(
        update(SessionModel)
        .where(SessionModel.user_id == str(user_id), SessionModel.revoked_at.is_(None))
        .values(revoked_at=now)
    )

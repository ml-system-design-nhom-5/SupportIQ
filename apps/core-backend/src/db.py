import asyncio
from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from src.config import settings

class Base(DeclarativeBase):
    pass

def init_models():
    try:
        import src.modules.auth.models
        import src.modules.commerce.models
        import src.modules.tickets.models
        import src.modules.audit.models
        import src.modules.orchestration.models
        import src.modules.review.models
        import src.modules.retrieval.models
    except ImportError:
        pass

init_models()

app_engine = create_async_engine(settings.app_db_url, echo=False)
AppSessionLocal = async_sessionmaker(app_engine, expire_on_commit=False, class_=AsyncSession)

audit_writer_engine = create_async_engine(settings.audit_writer_db_url, echo=False)
AuditWriterSessionLocal = async_sessionmaker(audit_writer_engine, expire_on_commit=False, class_=AsyncSession)

audit_reader_engine = create_async_engine(settings.audit_reader_db_url, echo=False)
AuditReaderSessionLocal = async_sessionmaker(audit_reader_engine, expire_on_commit=False, class_=AsyncSession)

vault_engine = create_async_engine(settings.vault_db_url, echo=False)
VaultSessionLocal = async_sessionmaker(vault_engine, expire_on_commit=False, class_=AsyncSession)

_sqlite_lock: asyncio.Lock | None = None

def get_sqlite_lock() -> asyncio.Lock:
    global _sqlite_lock
    if _sqlite_lock is None:
        _sqlite_lock = asyncio.Lock()
    return _sqlite_lock

async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    if "sqlite" in settings.app_db_url:
        lock = get_sqlite_lock()
        async with lock:
            async with AppSessionLocal() as session:
                yield session
    else:
        async with AppSessionLocal() as session:
            yield session

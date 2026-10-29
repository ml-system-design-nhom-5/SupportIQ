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

async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with AppSessionLocal() as session:
        yield session

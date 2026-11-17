"""Infrastructure-owned async connection, pool and session lifecycle."""
from collections.abc import AsyncGenerator
from datetime  import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.main.config import get_settings

def utcnow() -> datetime:
    return datetime.now(timezone.utc)

engine = create_async_engine(
    get_settings().database_url,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionFactory() as session:
        yield session

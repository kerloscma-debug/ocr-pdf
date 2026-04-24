from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import settings
import os

DB_URL = settings.DATABASE_URL
if DB_URL.startswith("sqlite:///") and not DB_URL.startswith("sqlite+aiosqlite"):
    DB_URL = DB_URL.replace("sqlite:///", "sqlite+aiosqlite:///")

engine = create_async_engine(DB_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

async def init_db():
    from app import models  # noqa
    # Ensure data dir exists for sqlite
    if "sqlite" in DB_URL:
        os.makedirs("data", exist_ok=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

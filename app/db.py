from collections.abc import AsyncIterator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings = get_settings()
engine = create_async_engine(settings.database_url, future=True, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
    import random
    from sqlalchemy import text

    from app import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Add display_id column if it does not yet exist (existing deployments).
        try:
            await conn.execute(text("ALTER TABLE users ADD COLUMN display_id INTEGER"))
        except Exception:
            pass  # Column already exists — that's fine.
        # Backfill display_id for users created before this column existed.
        result = await conn.execute(text("SELECT id FROM users WHERE display_id IS NULL"))
        rows = result.fetchall()
        if rows:
            used: set[int] = set()
            existing = await conn.execute(text("SELECT display_id FROM users WHERE display_id IS NOT NULL"))
            used.update(r[0] for r in existing.fetchall())
            for (user_id,) in rows:
                while True:
                    candidate = random.randint(1000, 9999)
                    if candidate not in used:
                        used.add(candidate)
                        break
                await conn.execute(text("UPDATE users SET display_id = :did WHERE id = :uid"), {"did": candidate, "uid": user_id})

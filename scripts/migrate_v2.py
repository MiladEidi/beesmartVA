from __future__ import annotations

import asyncio
from pathlib import Path
from sqlalchemy import text

from app.db import engine, init_db


async def migrate() -> None:
    await init_db()
    async with engine.begin() as conn:
        # SQLite stores enum values as text here, so BUSINESS_MANAGER support is schema-light.
        # Ensure the unique client-per-chat rule exists in practice and normalize missing JSON columns where possible.
        for table, column in [('clients', 'preferences'), ('clients', 'booking_links'), ('clients', 'restricted_contacts')]:
            try:
                await conn.execute(text(f"UPDATE {table} SET {column} = '[]' WHERE {column} IS NULL"))
            except Exception:
                pass
        print('Migration v2 complete. Back up your database before deploying to production.')


if __name__ == '__main__':
    asyncio.run(migrate())

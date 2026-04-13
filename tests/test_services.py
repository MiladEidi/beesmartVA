from __future__ import annotations

import os
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select

TMP_DB = Path('/tmp/beesmart_test.sqlite3')
os.environ['DATABASE_URL'] = f'sqlite+aiosqlite:///{TMP_DB}'
os.environ['BOT_TOKEN'] = '123:TESTTOKEN'
os.environ['ENCRYPTION_KEY'] = 'uC6lq2vYt0_8j0uD3emA23e1mU8Q82f3_-55m0EfQn4='

from app.db import SessionLocal, init_db
from app.enums import Role, TimesheetStatus
from app.services.reports import executive_summary
from app.services.users import add_or_update_user, ensure_client
from app.services.hours import create_or_get_timesheet, approve_by_client, approve_by_supervisor, get_timesheet


@pytest.mark.asyncio
async def test_business_manager_executive_summary_has_financials():
    if TMP_DB.exists():
        TMP_DB.unlink()
    await init_db()
    async with SessionLocal() as session:
        client = await ensure_client(session, chat_id=1001, name='Client A', business_name='Biz A')
        bm = await add_or_update_user(session, client_id=client.id, telegram_user_id=9001, display_name='Manager', role=Role.BUSINESS_MANAGER)
        va = await add_or_update_user(session, client_id=client.id, telegram_user_id=9002, display_name='VA', role=Role.VA)
        ts = await create_or_get_timesheet(session, va_id=va.id, client_id=client.id, week_start=date(2026, 3, 23))
        ts.total_hours = Decimal('7.5')
        ts.status = TimesheetStatus.APPROVED
        await session.commit()

    async with SessionLocal() as session:
        text = await executive_summary(session, telegram_user_id=9001, include_financials=True)
        assert 'approved_hours=7.5' in text


@pytest.mark.asyncio
async def test_timesheet_lookup_is_client_scoped():
    if TMP_DB.exists():
        TMP_DB.unlink()
    await init_db()
    async with SessionLocal() as session:
        c1 = await ensure_client(session, chat_id=2001, name='C1')
        c2 = await ensure_client(session, chat_id=2002, name='C2')
        va1 = await add_or_update_user(session, client_id=c1.id, telegram_user_id=3001, display_name='VA1', role=Role.VA)
        await add_or_update_user(session, client_id=c2.id, telegram_user_id=3001, display_name='VA1 other', role=Role.VA)
        ts1 = await create_or_get_timesheet(session, va_id=va1.id, client_id=c1.id, week_start=date(2026, 3, 23))
        await session.commit()
        found = await get_timesheet(session, timesheet_id=ts1.id, client_id=c2.id)
        assert found is None


@pytest.mark.asyncio
async def test_business_manager_can_complete_full_timesheet_approval():
    if TMP_DB.exists():
        TMP_DB.unlink()
    await init_db()
    async with SessionLocal() as session:
        client = await ensure_client(session, chat_id=4001, name='Client A')
        bm = await add_or_update_user(session, client_id=client.id, telegram_user_id=5001, display_name='BM', role=Role.BUSINESS_MANAGER)
        va = await add_or_update_user(session, client_id=client.id, telegram_user_id=5002, display_name='VA', role=Role.VA)
        ts = await create_or_get_timesheet(session, va_id=va.id, client_id=client.id, week_start=date(2026, 3, 23))
        ts.status = TimesheetStatus.SUBMITTED
        await approve_by_supervisor(session, timesheet=ts, supervisor_id=bm.id)
        assert ts.status == TimesheetStatus.CLIENT_PENDING
        await approve_by_client(session, timesheet=ts, client_user_id=bm.id)
        assert ts.status == TimesheetStatus.APPROVED


@pytest.mark.asyncio
async def test_business_manager_role_is_unique_and_transfer_requires_current_manager():
    if TMP_DB.exists():
        TMP_DB.unlink()
    await init_db()
    async with SessionLocal() as session:
        client = await ensure_client(session, chat_id=5001, name='Client B')
        await add_or_update_user(session, client_id=client.id, telegram_user_id=6001, display_name='BM1', role=Role.BUSINESS_MANAGER)
        await add_or_update_user(session, client_id=client.id, telegram_user_id=6002, display_name='User', role=Role.VA)

        with pytest.raises(ValueError, match='business manager already exists'):
            await add_or_update_user(
                session,
                client_id=client.id,
                telegram_user_id=6003,
                display_name='BM2',
                role=Role.BUSINESS_MANAGER,
            )

        bm2 = await add_or_update_user(
            session,
            client_id=client.id,
            telegram_user_id=6003,
            display_name='BM2',
            role=Role.BUSINESS_MANAGER,
            allow_business_manager_transfer=True,
        )
        assert bm2.role == Role.BUSINESS_MANAGER
        previous_bm = await session.scalar(
            select(User).where(User.client_id == client.id, User.telegram_user_id == 6001)
        )
        assert previous_bm.role == Role.SUPERVISOR

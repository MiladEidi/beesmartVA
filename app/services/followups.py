from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import ConnectionStatus
from app.models import Connection, User
from app.services.audit import write_audit


async def create_connection(
    session: AsyncSession,
    *,
    client_id: int,
    va_id: int,
    prospect_name: str,
    platform: str,
    title: str | None = None,
    company: str | None = None,
    followup_days: int = 3,
) -> Connection:
    connection = Connection(
        client_id=client_id,
        va_id=va_id,
        prospect_name=prospect_name,
        platform=platform,
        title=title,
        company=company,
        status=ConnectionStatus.CONNECTED,
        followup_due_at=datetime.utcnow() + timedelta(days=followup_days),
    )
    session.add(connection)
    await session.flush()
    await write_audit(session, client_id=client_id, actor_id=va_id, action='connection_logged', entity_type='connection', entity_id=connection.id, details={'name': prospect_name, 'platform': platform})
    return connection


async def find_connection(session: AsyncSession, *, client_id: int, name: str) -> Connection | None:
    return await session.scalar(select(Connection).where(Connection.client_id == client_id, Connection.prospect_name.ilike(name)).order_by(Connection.id.desc()))


async def pending_followups(session: AsyncSession, *, client_id: int) -> list[Connection]:
    rows = await session.scalars(select(Connection).where(Connection.client_id == client_id, Connection.status.in_([ConnectionStatus.CONNECTED, ConnectionStatus.FOLLOWED_UP])).order_by(Connection.followup_due_at.asc()))
    return list(rows.all())


async def due_followups(session: AsyncSession) -> list[Connection]:
    rows = await session.scalars(select(Connection).where(Connection.followup_due_at.is_not(None), Connection.followup_due_at <= datetime.utcnow(), Connection.status.in_([ConnectionStatus.CONNECTED, ConnectionStatus.FOLLOWED_UP])))
    return list(rows.all())


async def mark_followdone(session: AsyncSession, *, connection: Connection, actor_id: int, next_days: int = 3) -> Connection:
    connection.status = ConnectionStatus.FOLLOWED_UP
    connection.last_followup_at = datetime.utcnow()
    connection.followup_count += 1
    connection.followup_due_at = datetime.utcnow() + timedelta(days=next_days)
    await session.flush()
    await write_audit(session, client_id=connection.client_id, actor_id=actor_id, action='followup_done', entity_type='connection', entity_id=connection.id, details={'count': connection.followup_count})
    return connection


async def mark_replied(session: AsyncSession, *, connection: Connection, actor_id: int) -> Connection:
    connection.status = ConnectionStatus.REPLIED
    connection.followup_due_at = None
    await session.flush()
    await write_audit(session, client_id=connection.client_id, actor_id=actor_id, action='connection_replied', entity_type='connection', entity_id=connection.id)
    return connection


async def mark_booked(session: AsyncSession, *, connection: Connection, actor_id: int) -> Connection:
    connection.status = ConnectionStatus.BOOKED
    connection.followup_due_at = None
    connection.closed_at = datetime.utcnow()
    await session.flush()
    await write_audit(session, client_id=connection.client_id, actor_id=actor_id, action='meeting_booked', entity_type='connection', entity_id=connection.id)
    return connection


async def mark_noresponse(session: AsyncSession, *, connection: Connection, actor_id: int) -> Connection:
    connection.status = ConnectionStatus.CLOSED
    connection.followup_due_at = None
    connection.closed_at = datetime.utcnow()
    await session.flush()
    await write_audit(session, client_id=connection.client_id, actor_id=actor_id, action='connection_closed_noresponse', entity_type='connection', entity_id=connection.id)
    return connection


async def followup_counts(session: AsyncSession, *, client_id: int) -> int:
    rows = await session.scalars(select(Connection.id).where(Connection.client_id == client_id, Connection.status.in_([ConnectionStatus.CONNECTED, ConnectionStatus.FOLLOWED_UP])))
    return len(rows.all())


async def va_name_map(session: AsyncSession, *, client_id: int) -> dict[int, str]:
    rows = await session.scalars(select(User).where(User.client_id == client_id))
    return {u.id: u.display_name for u in rows.all()}

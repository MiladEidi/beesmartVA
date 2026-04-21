from __future__ import annotations

import random
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import Role
from app.models import AuditLog, Client, GlobalConfig, User
from app.security import CryptoService
from app.services.audit import write_audit

crypto = CryptoService()

DEFAULT_WORKING_HOURS = {'mon': '09:00-17:00', 'tue': '09:00-17:00', 'wed': '09:00-17:00', 'thu': '09:00-17:00', 'fri': '09:00-17:00'}


async def get_client_by_chat_id(session: AsyncSession, chat_id: int) -> Client | None:
    return await session.scalar(select(Client).where(Client.telegram_chat_id == chat_id))


async def ensure_client(
    session: AsyncSession,
    *,
    chat_id: int,
    name: str,
    business_name: str | None = None,
    tagline: str | None = None,
    primary_service: str | None = None,
    description: str | None = None,
    timezone: str = 'UTC',
) -> Client:
    client = await get_client_by_chat_id(session, chat_id)
    if client:
        return client
    client = Client(
        telegram_chat_id=chat_id,
        name=name,
        business_name=business_name,
        tagline=tagline,
        primary_service=primary_service,
        description=description,
        timezone=timezone,
    )
    session.add(client)
    await session.flush()
    await write_audit(session, client_id=client.id, actor_id=None, action='client_created', entity_type='client', entity_id=client.id)
    return client


async def get_user_by_telegram_id(session: AsyncSession, *, client_id: int, telegram_user_id: int) -> User | None:
    return await session.scalar(select(User).where(User.client_id == client_id, User.telegram_user_id == telegram_user_id, User.active.is_(True)))


async def get_user_by_name(session: AsyncSession, *, client_id: int, display_name: str) -> User | None:
    return await session.scalar(select(User).where(User.client_id == client_id, User.display_name.ilike(display_name), User.active.is_(True)))


async def get_user_by_internal_id(session: AsyncSession, *, client_id: int, user_id: int) -> User | None:
    return await session.scalar(select(User).where(User.client_id == client_id, User.id == user_id, User.active.is_(True)))


async def get_user_by_display_id(session: AsyncSession, *, client_id: int, display_id: int) -> User | None:
    return await session.scalar(select(User).where(User.client_id == client_id, User.display_id == display_id, User.active.is_(True)))


async def _generate_unique_display_id(session: AsyncSession) -> int:
    while True:
        candidate = random.randint(1000, 9999)
        existing = await session.scalar(select(User).where(User.display_id == candidate))
        if not existing:
            return candidate


async def get_business_manager(session: AsyncSession, *, client_id: int) -> User | None:
    return await session.scalar(
        select(User).where(
            User.client_id == client_id,
            User.role == Role.MANAGER,
            User.active.is_(True),
        )
    )


async def _get_global_config(session: AsyncSession) -> GlobalConfig:
    """Return the single GlobalConfig row, creating it if absent."""
    config = await session.scalar(select(GlobalConfig).where(GlobalConfig.id == 1))
    if config is None:
        config = GlobalConfig(id=1, business_manager_telegram_id=None)
        session.add(config)
        await session.flush()
    return config


async def get_global_bm_telegram_id(session: AsyncSession) -> int | None:
    """Return the Telegram user ID of the global manager, or None."""
    config = await _get_global_config(session)
    return config.business_manager_telegram_id


async def set_global_bm_telegram_id(session: AsyncSession, telegram_user_id: int) -> None:
    """Record a new global manager Telegram ID."""
    config = await _get_global_config(session)
    config.business_manager_telegram_id = telegram_user_id
    await session.flush()


async def add_or_update_user(
    session: AsyncSession,
    *,
    client_id: int,
    telegram_user_id: int,
    display_name: str,
    role: Role,
    timezone: str = 'UTC',
    working_hours: dict | None = None,
    supervisor_id: int | None = None,
    hourly_rate: Decimal | None = None,
    va_start_date: date | None = None,
    allow_business_manager_transfer: bool = False,
) -> User:
    if role == Role.MANAGER:
        global_bm_tg_id = await get_global_bm_telegram_id(session)
        if global_bm_tg_id and global_bm_tg_id != telegram_user_id:
            if not allow_business_manager_transfer:
                raise ValueError('A manager already exists globally. Only the current manager can transfer this role.')
            # Demote the old BM in every workspace they belong to
            old_bm_users = await session.scalars(
                select(User).where(
                    User.telegram_user_id == global_bm_tg_id,
                    User.role == Role.MANAGER,
                    User.active.is_(True),
                )
            )
            for old_bm in old_bm_users.all():
                old_bm.role = Role.SUPERVISOR
        await set_global_bm_telegram_id(session, telegram_user_id)

    user = await get_user_by_telegram_id(session, client_id=client_id, telegram_user_id=telegram_user_id)
    if user:
        user.display_name = display_name
        user.role = role
        user.timezone = timezone
        if working_hours:
            user.working_hours = working_hours
        elif not user.working_hours:
            user.working_hours = DEFAULT_WORKING_HOURS
        if supervisor_id is not None:
            user.supervisor_id = supervisor_id
        if hourly_rate is not None:
            user.hourly_rate_encrypted = crypto.encrypt(str(hourly_rate))
        if va_start_date is not None:
            user.va_start_date = va_start_date
        await session.flush()
        return user

    user = User(
        display_id=await _generate_unique_display_id(session),
        telegram_user_id=telegram_user_id,
        display_name=display_name,
        role=role,
        client_id=client_id,
        timezone=timezone,
        working_hours=working_hours or DEFAULT_WORKING_HOURS,
        supervisor_id=supervisor_id,
        va_start_date=va_start_date,
        hourly_rate_encrypted=crypto.encrypt(str(hourly_rate)) if hourly_rate is not None else None,
    )
    session.add(user)
    await session.flush()
    await write_audit(session, client_id=client_id, actor_id=user.id, action='user_registered', entity_type='user', entity_id=user.id, details={'role': role.value})
    return user


async def get_role_users(session: AsyncSession, *, client_id: int, role: Role) -> list[User]:
    rows = await session.scalars(select(User).where(User.client_id == client_id, User.role == role, User.active.is_(True)).order_by(User.display_name.asc()))
    return list(rows.all())


async def list_group_users(session: AsyncSession, *, client_id: int) -> list[User]:
    rows = await session.scalars(select(User).where(User.client_id == client_id, User.active.is_(True)).order_by(User.role.asc(), User.display_name.asc()))
    return list(rows.all())


async def set_supervisor(session: AsyncSession, *, client_id: int, va_user_id: int, supervisor_user_id: int, actor_id: int | None) -> User | None:
    va = await session.scalar(select(User).where(User.client_id == client_id, User.id == va_user_id, User.role == Role.VA))
    if not va:
        return None
    va.supervisor_id = supervisor_user_id
    await session.flush()
    await write_audit(session, client_id=client_id, actor_id=actor_id, action='set_supervisor', entity_type='user', entity_id=va.id, details={'supervisor_user_id': supervisor_user_id})
    return va


def decrypt_hourly_rate(user: User) -> Decimal | None:
    value = crypto.decrypt(user.hourly_rate_encrypted)
    return Decimal(value) if value else None


async def update_client_field(session: AsyncSession, *, client: Client, field_name: str, value: str, actor_id: int | None) -> bool:
    if field_name in {'name', 'business_name', 'tagline', 'primary_service', 'description', 'timezone'}:
        setattr(client, field_name, value)
    elif field_name == 'credentials':
        client.credentials_encrypted = crypto.encrypt(value)
    elif field_name == 'booking_link':
        links = list(client.booking_links or [])
        links.append(value)
        client.booking_links = links
    elif field_name == 'restricted_contact':
        items = list(client.restricted_contacts or [])
        items.append(value)
        client.restricted_contacts = items
    else:
        prefs = dict(client.preferences or {})
        prefs[field_name] = value
        client.preferences = prefs
    await session.flush()
    await write_audit(session, client_id=client.id, actor_id=actor_id, action='client_updated', entity_type='client', entity_id=client.id, details={'field': field_name})
    return True


def decrypt_credentials(client: Client) -> str | None:
    return crypto.decrypt(client.credentials_encrypted)


async def recent_audit_log(session: AsyncSession, *, client_id: int, limit: int = 20) -> list[AuditLog]:
    rows = await session.scalars(select(AuditLog).where(AuditLog.client_id == client_id).order_by(AuditLog.timestamp.desc()).limit(limit))
    return list(rows.all())

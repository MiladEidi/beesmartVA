from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import DraftStatus, Role
from app.models import Draft, User
from app.services.audit import write_audit


async def _next_code(session: AsyncSession) -> str:
    last = await session.scalar(select(Draft).order_by(Draft.id.desc()))
    nxt = (last.id + 1) if last else 1
    return f'DFT-{nxt:03d}'


async def submit_draft(session: AsyncSession, *, client_id: int, va_id: int, platform: str, content: str, parent_draft_id: int | None = None) -> Draft:
    draft = Draft(draft_code=await _next_code(session), client_id=client_id, va_id=va_id, platform=platform, content_text=content, parent_draft_id=parent_draft_id)
    session.add(draft)
    await session.flush()
    await write_audit(session, client_id=client_id, actor_id=va_id, action='draft_submitted', entity_type='draft', entity_id=draft.id, details={'platform': platform, 'draft_code': draft.draft_code})
    return draft


async def list_drafts(session: AsyncSession, *, client_id: int) -> list[Draft]:
    rows = await session.scalars(select(Draft).where(Draft.client_id == client_id).order_by(Draft.submitted_at.desc()))
    return list(rows.all())


async def get_draft_by_code(session: AsyncSession, *, client_id: int, code: str) -> Draft | None:
    return await session.scalar(select(Draft).where(Draft.client_id == client_id, Draft.draft_code == code.upper()))


async def get_draft(session: AsyncSession, *, draft_id: int, client_id: int | None = None) -> Draft | None:
    stmt = select(Draft).where(Draft.id == draft_id)
    if client_id is not None:
        stmt = stmt.where(Draft.client_id == client_id)
    return await session.scalar(stmt)


async def supervisor_approve_draft(session: AsyncSession, *, draft: Draft, actor_id: int) -> Draft:
    """Supervisor approves — moves draft to CLIENT_PENDING for client review."""
    draft.status = DraftStatus.CLIENT_PENDING
    draft.actioned_at = datetime.utcnow()
    draft.actioned_by = actor_id
    await session.flush()
    await write_audit(session, client_id=draft.client_id, actor_id=actor_id, action='draft_supervisor_approved', entity_type='draft', entity_id=draft.id)
    return draft


async def client_approve_draft(session: AsyncSession, *, draft: Draft, actor_id: int) -> Draft:
    """Client approves — draft is now ready to post."""
    draft.status = DraftStatus.APPROVED
    draft.actioned_at = datetime.utcnow()
    draft.actioned_by = actor_id
    await session.flush()
    await write_audit(session, client_id=draft.client_id, actor_id=actor_id, action='draft_client_approved', entity_type='draft', entity_id=draft.id)
    return draft


async def revise_draft(session: AsyncSession, *, draft: Draft, actor_id: int, note: str | None = None) -> Draft:
    draft.status = DraftStatus.REVISED
    draft.actioned_at = datetime.utcnow()
    draft.actioned_by = actor_id
    draft.revision_note = note
    await session.flush()
    await write_audit(session, client_id=draft.client_id, actor_id=actor_id, action='draft_revision_requested', entity_type='draft', entity_id=draft.id, details={'note': note})
    return draft


async def mark_posted(session: AsyncSession, *, draft: Draft, actor_id: int) -> Draft:
    draft.status = DraftStatus.POSTED
    draft.actioned_at = datetime.utcnow()
    await session.flush()
    await write_audit(session, client_id=draft.client_id, actor_id=actor_id, action='draft_posted', entity_type='draft', entity_id=draft.id)
    return draft


async def pending_drafts(session: AsyncSession, *, client_id: int) -> list[Draft]:
    rows = await session.scalars(select(Draft).where(Draft.client_id == client_id, Draft.status == DraftStatus.PENDING).order_by(Draft.submitted_at.asc()))
    return list(rows.all())


async def overdue_pending_drafts(session: AsyncSession) -> list[Draft]:
    threshold = datetime.utcnow() - timedelta(hours=48)
    rows = await session.scalars(select(Draft).where(Draft.status == DraftStatus.PENDING, Draft.submitted_at <= threshold))
    return list(rows.all())


async def client_pending_drafts_overdue(session: AsyncSession, *, hours: int) -> list[Draft]:
    """Return CLIENT_PENDING drafts that have been waiting longer than `hours` without client action."""
    threshold = datetime.utcnow() - timedelta(hours=hours)
    rows = await session.scalars(
        select(Draft).where(
            Draft.status == DraftStatus.CLIENT_PENDING,
            Draft.actioned_at <= threshold,
        )
    )
    return list(rows.all())


async def get_first_client_user(session: AsyncSession, *, client_id: int) -> User | None:
    return await session.scalar(select(User).where(User.client_id == client_id, User.role.in_([Role.CLIENT, Role.MANAGER])).order_by(User.id.asc()))


async def get_supervisor_user(session: AsyncSession, *, client_id: int) -> User | None:
    return await session.scalar(select(User).where(User.client_id == client_id, User.role.in_([Role.MANAGER, Role.SUPERVISOR])).order_by(User.id.asc()))

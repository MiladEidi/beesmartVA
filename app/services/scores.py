from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import Role, ScoreTrigger
from app.models import SatisfactionScore, User
from app.services.audit import write_audit


async def save_score(
    session: AsyncSession,
    *,
    client_id: int,
    va_id: int | None,
    score: int,
    comment: str | None,
    trigger_type: ScoreTrigger,
    period_label: str,
    actor_id: int,
) -> SatisfactionScore:
    item = SatisfactionScore(client_id=client_id, va_id=va_id, score=score, comment=comment, trigger_type=trigger_type, period_label=period_label, requested_at=datetime.utcnow(), responded_at=datetime.utcnow())
    session.add(item)
    await session.flush()
    await write_audit(session, client_id=client_id, actor_id=actor_id, action='score_recorded', entity_type='satisfaction_score', entity_id=item.id, details={'score': score, 'period': period_label, 'trigger': trigger_type.value})
    return item


async def score_history(session: AsyncSession, *, client_id: int) -> list[SatisfactionScore]:
    rows = await session.scalars(select(SatisfactionScore).where(SatisfactionScore.client_id == client_id).order_by(SatisfactionScore.responded_at.desc()))
    return list(rows.all())


async def all_scores(session: AsyncSession) -> list[SatisfactionScore]:
    rows = await session.scalars(select(SatisfactionScore).order_by(SatisfactionScore.responded_at.desc()))
    return list(rows.all())


async def get_client_user(session: AsyncSession, *, client_id: int) -> User | None:
    return await session.scalar(select(User).where(User.client_id == client_id, User.role == Role.CLIENT))

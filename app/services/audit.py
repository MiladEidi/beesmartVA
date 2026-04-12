from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog


async def write_audit(
    session: AsyncSession,
    *,
    client_id: int,
    actor_id: int | None,
    action: str,
    entity_type: str,
    entity_id: int | None,
    details: dict | None = None,
) -> None:
    session.add(
        AuditLog(
            client_id=client_id,
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details_json=details or {},
        )
    )
    await session.flush()

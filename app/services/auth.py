from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession
from telegram import Update

from app.enums import Role
from app.services.users import get_client_by_chat_id, get_global_bm_telegram_id, get_user_by_telegram_id


@dataclass(slots=True)
class BotContextUser:
    client_id: int
    chat_id: int
    role_user_id: int | None
    role: Role | None
    display_name: str | None
    telegram_user_id: int


async def resolve_actor(session: AsyncSession, update: Update) -> BotContextUser | None:
    chat = update.effective_chat
    user = update.effective_user
    if chat is None or user is None:
        return None
    client = await get_client_by_chat_id(session, chat.id)
    if not client:
        return None
    role_user = await get_user_by_telegram_id(session, client_id=client.id, telegram_user_id=user.id)

    resolved_role = role_user.role if role_user else None

    # Enforce the global business manager role regardless of the per-group record.
    global_bm_tg_id = await get_global_bm_telegram_id(session)
    if global_bm_tg_id and user.id == global_bm_tg_id and resolved_role != Role.BUSINESS_MANAGER:
        resolved_role = Role.BUSINESS_MANAGER

    return BotContextUser(
        client_id=client.id,
        chat_id=chat.id,
        role_user_id=role_user.id if role_user else None,
        role=resolved_role,
        display_name=role_user.display_name if role_user else user.full_name,
        telegram_user_id=user.id,
    )

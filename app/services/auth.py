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


async def _build_actor(session: AsyncSession, update: Update, client_id: int, client_chat_id: int) -> BotContextUser:
    user = update.effective_user
    role_user = await get_user_by_telegram_id(session, client_id=client_id, telegram_user_id=user.id)
    resolved_role = role_user.role if role_user else None
    global_bm_tg_id = await get_global_bm_telegram_id(session)
    if global_bm_tg_id and user.id == global_bm_tg_id and resolved_role != Role.MANAGER:
        resolved_role = Role.MANAGER
    return BotContextUser(
        client_id=client_id,
        chat_id=client_chat_id,
        role_user_id=role_user.id if role_user else None,
        role=resolved_role,
        display_name=role_user.display_name if role_user else user.full_name,
        telegram_user_id=user.id,
    )


async def resolve_actor(session: AsyncSession, update: Update) -> BotContextUser | None:
    """Resolve actor via the current chat's group ID. Use in group-chat command handlers."""
    chat = update.effective_chat
    user = update.effective_user
    if chat is None or user is None:
        return None
    client = await get_client_by_chat_id(session, chat.id)
    if not client:
        return None
    return await _build_actor(session, update, client.id, chat.id)


async def resolve_actor_for_client(session: AsyncSession, update: Update, client_id: int) -> BotContextUser | None:
    """Resolve actor by an explicit client_id.

    Use this in private-chat callbacks (inline button presses) where the chat ID
    is the user's own Telegram ID and cannot be used to look up the client group.
    The client_id is derived from the record being acted on (timesheet, draft, etc.).
    """
    user = update.effective_user
    chat = update.effective_chat
    if user is None or chat is None:
        return None
    return await _build_actor(session, update, client_id, chat.id)

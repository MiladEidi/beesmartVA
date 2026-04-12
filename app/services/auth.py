from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession
from telegram import Update

from app.enums import Role
from app.services.users import get_client_by_chat_id, get_user_by_telegram_id


@dataclass(slots=True)
class BotContextUser:
    client_id: int
    chat_id: int
    role_user_id: int | None
    role: Role | None
    display_name: str | None


async def resolve_actor(session: AsyncSession, update: Update) -> BotContextUser | None:
    chat = update.effective_chat
    user = update.effective_user
    if chat is None or user is None:
        return None
    client = await get_client_by_chat_id(session, chat.id)
    if not client:
        return None
    role_user = await get_user_by_telegram_id(session, client_id=client.id, telegram_user_id=user.id)
    return BotContextUser(
        client_id=client.id,
        chat_id=chat.id,
        role_user_id=role_user.id if role_user else None,
        role=role_user.role if role_user else None,
        display_name=role_user.display_name if role_user else user.full_name,
    )

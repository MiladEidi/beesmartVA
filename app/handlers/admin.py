from __future__ import annotations

from datetime import date
from decimal import Decimal
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import ContextTypes

from app.db import SessionLocal
from app.enums import Role
from app.services.auth import resolve_actor
from app.services.permissions import has_manager_access
from app.services.users import (
    add_or_update_user,
    ensure_client,
    get_client_by_chat_id,
    get_user_by_internal_id,
    get_user_by_telegram_id,
    list_group_users,
    recent_audit_log,
    set_supervisor,
    update_client_field,
)
from app.utils.dates import parse_schedule_text


async def setup_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    raw = update.message.text.partition(" ")[2].strip()
    parts = [part.strip() for part in raw.split("|") if part.strip()]

    if len(parts) != 6:
        await update.message.reply_text(
            "Setup requires 6 fields separated by |\n\n"
            "Format:\n"
            "/setup | Client Name | Business Name | Timezone | Primary Service | Tagline | Description\n\n"
            "Example:\n"
            "/setup | Jane Smith | BeeSmartVA | Europe/Paris | Lead Generation | Smart VA support | Daily VA operations for Jane\n\n"
            "Fields explained:\n"
            "  Client Name     → the client's name (e.g. Jane Smith)\n"
            "  Business Name   → your VA business name (e.g. BeeSmartVA)\n"
            "  Timezone        → IANA timezone (e.g. Europe/Paris, Asia/Manila, America/New_York)\n"
            "  Primary Service → what you do (e.g. Lead Generation, Admin Support)\n"
            "  Tagline         → short slogan (e.g. Smart VA support)\n"
            "  Description     → one-line summary of the engagement\n\n"
            "For the full setup guide: /guide setup"
        )
        return

    client_name, business_name, timezone_name, primary_service, tagline, description = parts

    try:
        ZoneInfo(timezone_name)
    except Exception:
        await update.message.reply_text(
            "Timezone must be a valid IANA timezone such as Europe/Paris, America/New_York, or Asia/Dubai."
        )
        return

    async with SessionLocal() as session:
        existing = await get_client_by_chat_id(session, update.effective_chat.id)
        if existing:
            await update.message.reply_text(
                'This group is already set up.\n\n'
                'To manage users: /adduser or /menu → Add user\n'
                'To view the group: /groups\n'
                'For setup help: /guide setup'
            )
            return
        client = await ensure_client(
            session,
            chat_id=update.effective_chat.id,
            name=client_name,
            business_name=business_name,
            timezone=timezone_name,
            primary_service=primary_service,
            tagline=tagline,
            description=description,
        )
        await add_or_update_user(
            session,
            client_id=client.id,
            telegram_user_id=update.effective_user.id,
            display_name=update.effective_user.full_name,
            role=Role.BUSINESS_MANAGER,
            timezone=timezone_name,
        )
        await session.commit()

    await update.message.reply_text(
        f"Workspace created!\n\n"
        f"  Client:   {client_name}\n"
        f"  Business: {business_name}\n"
        f"  Timezone: {timezone_name}\n\n"
        "You are registered as Business Manager.\n\n"
        "Next steps:\n"
        "  1. Add your team: /adduser [tg_id] VA [Name]\n"
        "  2. Add a supervisor: /adduser [tg_id] SUPERVISOR [Name]\n"
        "  3. Add the client: /adduser [tg_id] CLIENT [Name]\n"
        "  4. Assign supervisors: /set supervisor [va_id] [sup_id]\n"
        "  5. Set VA rates: /set rate [va_id] [amount]\n\n"
        "Full setup guide: /guide setup\n"
        "Guided menu: /menu"
    )


async def adduser_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) < 3:
        await update.message.reply_text(
            "Use: /adduser [tg_id] [ROLE] [display_name]\n\n"
            "Roles: VA | SUPERVISOR | CLIENT | BUSINESS_MANAGER\n\n"
            "Examples:\n"
            "  /adduser 123456789 VA Sarah Jones\n"
            "  /adduser 987654321 SUPERVISOR Mike Smith\n"
            "  /adduser 112233445 CLIENT Jane Brown\n\n"
            "How to find a Telegram ID:\n"
            "  Ask the user to message @userinfobot — it replies with their ID.\n\n"
            "Or use the guided flow: /menu → Add user\n"
            "Full guide: /guide setup"
        )
        return

    try:
        tg_id = int(context.args[0])
        role = Role(context.args[1].upper())
    except Exception:
        await update.message.reply_text(
            "Invalid format.\n\n"
            "Use: /adduser [tg_id] [VA|SUPERVISOR|CLIENT|BUSINESS_MANAGER] [display_name]\n"
            "Example: /adduser 123456789 VA Sarah Jones"
        )
        return

    display_name = " ".join(context.args[2:]).strip()

    async with SessionLocal() as session:
        actor = await resolve_actor(session, update)
        if not actor or not has_manager_access(actor.role):
            await update.message.reply_text("Only supervisors or business managers can add users.")
            return

        if role == Role.BUSINESS_MANAGER and actor.role != Role.BUSINESS_MANAGER:
            await update.message.reply_text(
                "Only the current business manager can assign or change the business manager."
            )
            return

        try:
            await add_or_update_user(
                session,
                client_id=actor.client_id,
                telegram_user_id=tg_id,
                display_name=display_name,
                role=role,
                timezone="UTC",
                va_start_date=date.today() if role == Role.VA else None,
                allow_business_manager_transfer=(role == Role.BUSINESS_MANAGER and actor.role == Role.BUSINESS_MANAGER),
            )
        except ValueError as exc:
            await update.message.reply_text(str(exc))
            return
        await session.commit()

    await update.message.reply_text(
        f"User added!\n\n"
        f"  Name: {display_name}\n"
        f"  Role: {role.value}\n\n"
        + ("Next: /set supervisor [va_id] [sup_id] to assign their supervisor\n"
           "      /set rate [va_id] [amount] to set their hourly rate\n\n"
           if role == Role.VA else
           "Ask them to type /start in the group.\n\n")
        + "Full guide: /guide setup"
    )


async def groups_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with SessionLocal() as session:
        actor = await resolve_actor(session, update)
        if not actor or not has_manager_access(actor.role):
            await update.message.reply_text("Only supervisors or business managers can use /groups.")
            return

        users = await list_group_users(session, client_id=actor.client_id)
        client = await get_client_by_chat_id(session, update.effective_chat.id)

        lines = [
            f"Group: {client.name} ({client.business_name or '-'})",
            f"Timezone: {client.timezone}",
            "",
        ]
        for user in users:
            lines.append(f"{user.id} · {user.display_name} · {user.role.value}")

        await update.message.reply_text("\n".join(lines))


async def set_supervisor_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) < 2:
        await update.message.reply_text(
            "Use: /set supervisor [va_user_id] [supervisor_user_id]\n\n"
            "Both IDs are internal user IDs (shown in /groups).\n"
            "Example: /set supervisor 3 7\n\n"
            "Or use the guided flow: /menu → Set supervisor\n"
            "Full guide: /guide setup"
        )
        return

    try:
        va_id = int(context.args[0])
        supervisor_id = int(context.args[1])
    except ValueError:
        await update.message.reply_text("User IDs must be numbers.")
        return

    async with SessionLocal() as session:
        actor = await resolve_actor(session, update)
        if not actor or not has_manager_access(actor.role) or actor.role_user_id is None:
            await update.message.reply_text("Only supervisors or business managers can assign supervisors.")
            return

        va = await set_supervisor(
            session,
            client_id=actor.client_id,
            va_user_id=va_id,
            supervisor_user_id=supervisor_id,
            actor_id=actor.role_user_id,
        )
        if not va:
            await update.message.reply_text("VA not found.")
            return

        await session.commit()

    await update.message.reply_text(
        f"{va.display_name} is now assigned to supervisor user #{supervisor_id}."
    )


async def set_rate_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) < 2:
        await update.message.reply_text(
            "Use: /set rate [va_user_id] [amount]\n"
            "  or /set rate tg:[va_telegram_id] [amount]\n\n"
            "Examples:\n"
            "  /set rate 3 15.50       (internal user ID from /groups)\n"
            "  /set rate tg:123456789 12  (Telegram user ID)\n\n"
            "Or use the guided flow: /menu → Set rate\n"
            "Full invoicing guide: /guide invoicing"
        )
        return

    target = context.args[0]
    try:
        amount = Decimal(context.args[1])
    except Exception:
        await update.message.reply_text("Use: /set rate [va_user_id] [amount]  or /set rate tg:[va_tg_id] [amount]")
        return

    async with SessionLocal() as session:
        actor = await resolve_actor(session, update)
        if not actor or not has_manager_access(actor.role):
            await update.message.reply_text("Only supervisors or business managers can set rates.")
            return

        va = None
        if target.startswith('tg:'):
            va = await get_user_by_telegram_id(session, client_id=actor.client_id, telegram_user_id=int(target[3:]))
        else:
            va = await get_user_by_internal_id(session, client_id=actor.client_id, user_id=int(target))
        if not va or va.role != Role.VA:
            await update.message.reply_text("VA not found.")
            return

        await add_or_update_user(
            session,
            client_id=actor.client_id,
            telegram_user_id=va.telegram_user_id,
            display_name=va.display_name,
            role=va.role,
            timezone=va.timezone,
            working_hours=va.working_hours,
            supervisor_id=va.supervisor_id,
            hourly_rate=amount,
            va_start_date=va.va_start_date,
        )
        await session.commit()

    await update.message.reply_text(f"Rate updated for {va.display_name}: ${amount}/hr")


async def set_timezone_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) < 2:
        await update.message.reply_text("Use: /set timezone [user_tg_id|client] [timezone]")
        return

    target = context.args[0]
    timezone_name = context.args[1]

    try:
        ZoneInfo(timezone_name)
    except Exception:
        await update.message.reply_text(
            "Use a valid IANA timezone, such as Europe/Paris, Asia/Manila, or America/New_York."
        )
        return

    async with SessionLocal() as session:
        actor = await resolve_actor(session, update)
        client = await get_client_by_chat_id(session, update.effective_chat.id)

        if not actor or not has_manager_access(actor.role) or not client:
            await update.message.reply_text("Only supervisors or business managers can update timezones.")
            return

        if target.lower() == "client":
            client.timezone = timezone_name
            await session.commit()
            await update.message.reply_text(f"Client timezone updated to {timezone_name}.")
            return

        try:
            target_tg_id = int(target)
        except ValueError:
            await update.message.reply_text("User Telegram ID must be numeric or use 'client'.")
            return

        user = await get_user_by_telegram_id(
            session,
            client_id=client.id,
            telegram_user_id=target_tg_id,
        )
        if not user:
            await update.message.reply_text("User not found.")
            return

        user.timezone = timezone_name
        await session.commit()
        await update.message.reply_text(f"{user.display_name} timezone updated to {timezone_name}.")


async def set_va_hours_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        'VA working hours are stored per user.\n\n'
        'To update a user\'s details, use:\n'
        '  /update working_hours [value]\n\n'
        'To see current user configuration: /groups\n'
        'For setup help: /guide setup'
    )


async def update_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) < 2:
        await update.message.reply_text('Use: /update [field] [value]')
        return
    field_name = context.args[0]
    value = ' '.join(context.args[1:]).strip()
    async with SessionLocal() as session:
        actor = await resolve_actor(session, update)
        client = await get_client_by_chat_id(session, update.effective_chat.id)
        if not actor or not client or not has_manager_access(actor.role):
            await update.message.reply_text('Only supervisors or business managers can update client settings.')
            return
        await update_client_field(session, client=client, field_name=field_name, value=value, actor_id=actor.role_user_id)
        await session.commit()
        await update.message.reply_text(f'Updated {field_name}.')


async def auditlog_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with SessionLocal() as session:
        actor = await resolve_actor(session, update)
        if not actor or not has_manager_access(actor.role):
            await update.message.reply_text('Only supervisors or business managers can use /auditlog.')
            return
        items = await recent_audit_log(session, client_id=actor.client_id, limit=20)
        if not items:
            await update.message.reply_text('No audit log entries yet.')
            return
        text = '\n'.join(f"{item.timestamp:%Y-%m-%d %H:%M} · {item.action} · {item.entity_type}#{item.entity_id}" for item in items)
        await update.message.reply_text(text)

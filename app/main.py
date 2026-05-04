import asyncio
import logging
from contextlib import suppress

import uvicorn
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from app.api.app import app as api_app
from app.config import get_settings
from app.db import init_db
from app.handlers.admin import (
    adduser_command,
    auditlog_command,
    groups_command,
    set_rate_command,
    set_supervisor_command,
    set_timezone_command,
    set_va_hours_command,
    setmanager_command,
    setup_command,
    update_command,
)
from app.handlers.callbacks import draft_callback, score_callback, timesheet_callback
from app.handlers.checkins import ask_command, confirm_command, flag_command, notify_client_command, stats_command
from app.handlers.common import contacts_command, credentials_command, guide_command, help_command, howto_command, links_command, prefs_command, profile_command, schedule_command, start_command
from app.handlers.ui import flow_message_handler, menu_command, ui_callback
from app.voice.handler import voice_message_handler
from app.handlers.drafts import draft_command, drafts_command, posted_command
from app.handlers.followups import booked_command, connection_command, followdone_command, followups_command, noresponse_command, replied_command
from app.handlers.hours import hours_command, invoice_sent_command, invoice_summary_command, myweek_command, rate_command, submit_hours_command, timesheets_command
from app.handlers.reports import monthly_command, report_all_command, weekly_command
from app.handlers.scores import scores_command, send_scorecheck_command
from app.handlers.tasks import assign_command, cantdo_command, done_command, flagged_command, overdue_command, task_command, tasks_command
from app.services.scheduler import configure_scheduler

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(name)s | %(message)s')
logger = logging.getLogger(__name__)
settings = get_settings()


async def post_init(application: Application) -> None:
    await init_db()
    configure_scheduler(application.bot)
    logger.info('Bot initialized and scheduler started.')


def build_application() -> Application:
    application = Application.builder().token(settings.bot_token).post_init(post_init).build()

    for name, fn in [
        ('start', start_command), ('help', help_command), ('guide', guide_command), ('howto', howto_command), ('menu', menu_command),
        ('profile', profile_command), ('links', links_command), ('contacts', contacts_command),
        ('prefs', prefs_command), ('schedule', schedule_command), ('credentials', credentials_command),
        ('setup', setup_command), ('adduser', adduser_command), ('groups', groups_command), ('update', update_command), ('auditlog', auditlog_command), ('setmanager', setmanager_command),
        ('task', task_command), ('tasks', tasks_command), ('done', done_command), ('cantdo', cantdo_command), ('assign', assign_command), ('overdue', overdue_command), ('flagged', flagged_command),
        ('hours', hours_command), ('myweek', myweek_command), ('timesheets', timesheets_command), ('rate', rate_command),
        ('ask', ask_command), ('flag', flag_command), ('confirm', confirm_command), ('weekly', weekly_command), ('monthly', monthly_command), ('stats', stats_command),
        ('connection', connection_command), ('followups', followups_command), ('followdone', followdone_command), ('replied', replied_command), ('booked', booked_command), ('noresponse', noresponse_command),
        ('draft', draft_command), ('drafts', drafts_command), ('posted', posted_command),
        ('scores', scores_command),
    ]:
        application.add_handler(CommandHandler(name, fn))

    application.add_handler(CommandHandler('set', set_dispatcher))
    application.add_handler(CommandHandler('submit', submit_dispatcher))
    application.add_handler(CommandHandler('invoice', invoice_dispatcher))
    application.add_handler(CommandHandler('report', report_dispatcher))
    application.add_handler(CommandHandler('send', send_dispatcher))
    application.add_handler(CommandHandler('notify', notify_dispatcher))
    application.add_handler(CallbackQueryHandler(ui_callback, pattern=r'^ui:'))
    application.add_handler(CallbackQueryHandler(timesheet_callback, pattern=r'^ts:'))
    application.add_handler(CallbackQueryHandler(draft_callback, pattern=r'^df:'))
    application.add_handler(CallbackQueryHandler(score_callback, pattern=r'^sc:'))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, flow_message_handler))
    # Handle voice in private chats AND groups/supergroups; exclude channels
    # (channels have no real sender, so voice commands make no sense there).
    # NOTE: in groups the bot must either be an admin or have privacy mode OFF
    # so Telegram forwards non-command messages to it.
    application.add_handler(MessageHandler(
        filters.VOICE & ~filters.ChatType.CHANNEL,
        voice_message_handler,
    ))
    return application


async def set_dispatcher(update, context):
    if len(context.args) < 1:
        await update.message.reply_text('Use one of: /set supervisor | /set rate | /set timezone | /set va_hours')
        return
    sub = context.args[0].lower()
    context.args = context.args[1:]
    if sub == 'supervisor':
        await set_supervisor_command(update, context)
    elif sub == 'rate':
        await set_rate_command(update, context)
    elif sub == 'timezone':
        await set_timezone_command(update, context)
    elif sub == 'va_hours':
        await set_va_hours_command(update, context)
    else:
        await update.message.reply_text('Unknown /set subcommand.')


async def submit_dispatcher(update, context):
    # Accept /submit or /submit hours (the only subcommand)
    if context.args and context.args[0].lower() == 'hours':
        context.args = context.args[1:]
    await submit_hours_command(update, context)


async def invoice_dispatcher(update, context):
    if not context.args:
        await update.message.reply_text('Use /invoice summary ... or /invoice sent ...')
        return
    sub = context.args[0].lower()
    context.args = context.args[1:]
    if sub == 'summary':
        await invoice_summary_command(update, context)
    elif sub == 'sent':
        await invoice_sent_command(update, context)
    else:
        await update.message.reply_text('Unknown /invoice subcommand.')


async def report_dispatcher(update, context):
    # Accept /report or /report all (the only subcommand)
    if context.args and context.args[0].lower() == 'all':
        context.args = context.args[1:]
    await report_all_command(update, context)


async def send_dispatcher(update, context):
    # Accept /send or /send scorecheck (the only subcommand)
    if context.args and context.args[0].lower() == 'scorecheck':
        context.args = context.args[1:]
    await send_scorecheck_command(update, context)


async def notify_dispatcher(update, context):
    if context.args and context.args[0].lower() == 'client':
        context.args = context.args[1:]
        await notify_client_command(update, context)
        return
    await update.message.reply_text('Use /notify client [message]')


async def run_api() -> None:
    config = uvicorn.Config(api_app, host=settings.api_host, port=settings.api_port, log_level='info')
    server = uvicorn.Server(config)
    await server.serve()


async def run_bot() -> None:
    application = build_application()
    await application.initialize()
    await application.start()
    await application.updater.start_polling(drop_pending_updates=False)
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        with suppress(Exception):
            await application.updater.stop()
        with suppress(Exception):
            await application.stop()
        with suppress(Exception):
            await application.shutdown()


async def main() -> None:
    await init_db()
    await asyncio.gather(run_api(), run_bot())


if __name__ == '__main__':
    asyncio.run(main())

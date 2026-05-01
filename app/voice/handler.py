"""
Telegram voice message handler.

Flow:
  1. User sends a voice message.
  2. Download the OGG from Telegram.
  3. faster-whisper transcribes it → raw text.
  4. normalizer.normalize() cleans the text (phonetic fixes, word numbers…).
  5. router.route() scores every intent and picks the best match.
  6. Send a "heard you" message so the user can verify transcription + intent.
  7. Set context.args to the extracted arguments and call the existing handler.

Environment variables (all optional):
  WHISPER_MODEL  — tiny / base / small / medium / large-v2  (default: base)
  WHISPER_DEVICE — cpu / cuda                               (default: cpu)
  WHISPER_LANG   — ISO 639-1 language hint                  (default: en)
"""

import logging
import os

from telegram import Update
from telegram.ext import ContextTypes

from app.voice.transcriber import transcribe_voice
from app.voice.normalizer import normalize
from app.voice.router import route

logger = logging.getLogger(__name__)

WHISPER_LANG = os.getenv('WHISPER_LANG', 'en')

# Human-readable labels shown to the user after the intent is matched.
# Tells them WHAT ACTION is about to run, not just what was heard.
_INTENT_LABELS: dict[str, str] = {
    'done_task':        'Marking task done',
    'cantdo_task':      'Flagging task as blocked',
    'assign_task':      'Assigning task',
    'overdue_tasks':    'Listing overdue tasks',
    'flagged_tasks':    'Listing flagged tasks',
    'create_task':      'Creating task',
    'list_tasks':       'Listing open tasks',
    'submit_hours':     'Submitting timesheet',
    'my_week':          'Showing this week\'s hours',
    'log_hours':        'Logging hours',
    'list_timesheets':  'Listing pending timesheets',
    'my_rate':          'Showing your hourly rate',
    'ask_supervisor':   'Sending question to supervisor',
    'flag_issue':       'Raising an issue',
    'confirm_request':  'Sending confirmation request',
    'notify_client':    'Notifying client',
    'stats':            'Showing team stats',
    'new_connection':   'Logging new connection',
    'list_followups':   'Listing pending follow-ups',
    'follow_done':      'Marking follow-up done',
    'replied':          'Marking contact as replied',
    'booked':           'Marking contact as booked',
    'no_response':      'Marking no response',
    'list_drafts':      'Listing drafts',
    'mark_posted':      'Marking draft as posted',
    'create_draft':     'Creating draft',
    'weekly_report':    'Generating weekly report',
    'monthly_report':   'Generating monthly report',
    'full_report':      'Generating full report',
    'send_scorecheck':  'Sending satisfaction check to client',
    'show_scores':      'Showing satisfaction scores',
    'list_users':       'Listing team members',
    'show_schedule':    'Showing schedule',
    'show_links':       'Showing booking links',
    'show_contacts':    'Showing contacts',
    'show_prefs':       'Showing preferences',
    'profile':          'Showing your profile',
    'help':             'Showing help',
    'menu':             'Opening menu',
}

_NO_MATCH_MESSAGE = (
    '{heard}\n\n'
    'I didn\'t recognise that as a command. Try saying:\n\n'
    '📋 *Tasks*\n'
    '• "Create task follow up with John"\n'
    '• "Task 5 done"\n'
    '• "Can\'t do task 3 skill"\n'
    '• "Assign task 2 to user 1042"\n'
    '• "Show flagged tasks"\n\n'
    '⏱ *Hours*\n'
    '• "Log 3 hours today for client calls"\n'
    '• "Log 2.5 hours yesterday"\n'
    '• "Show my week"\n'
    '• "Submit hours"\n'
    '• "What\'s my rate"\n\n'
    '🔗 *Follow-ups*\n'
    '• "New connection John on LinkedIn"\n'
    '• "Sarah replied"\n'
    '• "Meeting booked with John"\n'
    '• "No response from Mike"\n\n'
    '📝 *Drafts*\n'
    '• "Create LinkedIn draft: [content]"\n'
    '• "Show my drafts"\n'
    '• "Posted draft ABC-001"\n\n'
    '📊 *Reports & Info*\n'
    '• "Weekly report"\n'
    '• "Show team stats"\n'
    '• "Show all users"\n'
    '• "My profile"\n'
    '• "Menu"'
)


async def voice_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Entry point registered with MessageHandler(filters.VOICE, ...)."""
    msg = update.message

    # ── 1. Download ────────────────────────────────────────────────────────
    await msg.reply_text('🎙 Processing your voice message…')
    try:
        tg_file = await context.bot.get_file(msg.voice.file_id)
        file_bytes = await tg_file.download_as_bytearray()
    except Exception as exc:
        logger.error('Voice download failed: %s', exc)
        await msg.reply_text('Could not download your voice message. Please try again.')
        return

    # ── 2. Transcribe ──────────────────────────────────────────────────────
    try:
        raw_text = await transcribe_voice(bytes(file_bytes), language=WHISPER_LANG)
    except Exception as exc:
        logger.error('Whisper transcription error: %s', exc)
        await msg.reply_text(
            'Transcription failed.\n'
            'Make sure ffmpeg is installed on the server (sudo apt install ffmpeg).'
        )
        return

    if not raw_text.strip():
        await msg.reply_text('Could not make out any words. Please try again.')
        return

    # ── 3. Normalize + route ───────────────────────────────────────────────
    clean_text = normalize(raw_text)
    logger.info(
        'Voice | user=%s | raw="%s" | clean="%s"',
        msg.from_user.id, raw_text, clean_text,
    )

    result = route(clean_text)

    if result is None:
        await msg.reply_text(
            _NO_MATCH_MESSAGE.format(heard=f'🎙 Heard: "{raw_text}"'),
            parse_mode='Markdown',
        )
        return

    logger.info('Voice routed → intent="%s" args=%s', result.intent, result.args)

    # ── 4. Confirm what was heard AND what action will run ─────────────────
    label = _INTENT_LABELS.get(result.intent, result.intent)
    await msg.reply_text(f'🎙 Heard: "{raw_text}"\n→ {label}…')

    # ── 5. Execute the matched handler ─────────────────────────────────────
    # context.args has a proper setter in python-telegram-bot v22.
    # We set it here so the existing handlers read their expected arguments.
    context.args = result.args

    try:
        await result.handler(update, context)
    except Exception as exc:
        logger.error(
            'Handler "%s" raised an exception | args=%s | error=%s',
            result.intent, result.args, exc, exc_info=True,
        )
        await msg.reply_text(
            f'Something went wrong running "{label}".\n'
            f'Detected args: {result.args}\n'
            f'Error: {exc}'
        )
    finally:
        # Always restore to None so other handlers are not affected.
        context.args = None

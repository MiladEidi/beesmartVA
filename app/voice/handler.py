"""
Telegram voice message handler.

Flow:
  1. User sends a voice message.
  2. Download the OGG from Telegram.
  3. faster-whisper transcribes it → raw text.
  4. normalizer.normalize() cleans the text (phonetic fixes, word numbers…).
  5. router.route() scores every intent and picks the best match.
  6. Send a "heard you" message so the user can verify transcription.
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
            f'🎙 Heard: "{raw_text}"\n\n'
            'I did not understand that command.\n\n'
            'Try saying:\n'
            '• "Create task follow up with John"\n'
            '• "Log 3 hours today for client calls"\n'
            '• "Task 5 done"\n'
            '• "Submit hours"\n'
            '• "Show my week"\n'
            '• "Show tasks"'
        )
        return

    logger.info('Voice routed → intent="%s" args=%s', result.intent, result.args)

    # ── 4. Confirm what was heard (before executing, so user always gets feedback)
    await msg.reply_text(f'🎙 Heard: "{raw_text}"')

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
            f'Something went wrong running "{result.intent}".\n'
            f'Detected args: {result.args}\n'
            f'Error: {exc}'
        )
    finally:
        # Always restore to None so other handlers are not affected.
        context.args = None

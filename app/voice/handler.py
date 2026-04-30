"""
Telegram voice message handler.

Flow:
  1. User sends a voice message.
  2. We download the OGG file from Telegram.
  3. faster-whisper transcribes it → text.
  4. normalizer.normalize() cleans the text.
  5. router.route() finds the matching intent → (handler_fn, args).
  6. We set context.args and call the existing handler — no duplication of logic.
  7. We prepend the transcription to the reply so the user can verify what was heard.

Environment variables (all optional, with defaults):
  WHISPER_MODEL    — e.g. 'base', 'small', 'medium'  (default: 'base')
  WHISPER_DEVICE   — 'cpu' or 'cuda'                  (default: 'cpu')
  WHISPER_LANG     — ISO 639-1 language code           (default: 'en')
"""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from app.voice.transcriber import transcribe_voice
from app.voice.normalizer import normalize
from app.voice.router import route

logger = logging.getLogger(__name__)

import os
WHISPER_LANG = os.getenv('WHISPER_LANG', 'en')


async def voice_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Entry point registered with MessageHandler(filters.VOICE, ...)."""
    msg = update.message

    # ── 1. Download voice file ─────────────────────────────────────────────
    await msg.reply_text('🎙 Heard you — processing…')
    try:
        tg_file = await context.bot.get_file(msg.voice.file_id)
        file_bytes = await tg_file.download_as_bytearray()
    except Exception as exc:
        logger.error('Failed to download voice file: %s', exc)
        await msg.reply_text('Sorry, I could not download your voice message.')
        return

    # ── 2. Transcribe ──────────────────────────────────────────────────────
    try:
        raw_text = await transcribe_voice(bytes(file_bytes), language=WHISPER_LANG)
    except Exception as exc:
        logger.error('Whisper transcription error: %s', exc)
        await msg.reply_text(
            'Sorry, transcription failed. Make sure ffmpeg is installed on the server.'
        )
        return

    if not raw_text.strip():
        await msg.reply_text('I could not make out any words. Please try again.')
        return

    # ── 3. Normalize ───────────────────────────────────────────────────────
    clean_text = normalize(raw_text)
    logger.info('Voice from %s | raw="%s" | clean="%s"', msg.from_user.id, raw_text, clean_text)

    # ── 4. Route ───────────────────────────────────────────────────────────
    result = route(clean_text)

    if result is None:
        await msg.reply_text(
            f'🎙 I heard: _"{raw_text}"_\n\n'
            f'Sorry, I did not understand that command.\n'
            f'Try saying things like:\n'
            f'• "Create task fix the login bug"\n'
            f'• "Log 3 hours today for client calls"\n'
            f'• "Mark task 5 as done"\n'
            f'• "Submit hours"\n'
            f'• "Show my week"',
            parse_mode='Markdown',
        )
        return

    # ── 5. Execute the matched handler ────────────────────────────────────
    logger.info('Voice routed to intent="%s" args=%s', result.intent, result.args)

    # Patch context.args so the existing handler sees its expected arguments
    original_args = context.args
    context.args = result.args

    # Prepend a "heard you" line to distinguish voice replies from text replies
    # We monkey-patch reply_text for this one call only.
    _original_reply = msg.reply_text

    async def _prefixed_reply(text, **kwargs):
        header = f'🎙 _Heard:_ "{raw_text}"\n\n'
        return await _original_reply(header + text, **kwargs)

    msg.reply_text = _prefixed_reply  # type: ignore[method-assign]

    try:
        await result.handler(update, context)
    except Exception as exc:
        logger.error('Handler "%s" raised: %s', result.intent, exc, exc_info=True)
        await _original_reply('Something went wrong executing that command.')
    finally:
        context.args = original_args
        msg.reply_text = _original_reply  # type: ignore[method-assign]

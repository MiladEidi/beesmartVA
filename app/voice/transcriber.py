"""
Speech-to-text using faster-whisper (local, CPU or CUDA).

Install:
    pip install faster-whisper

System requirement:
    ffmpeg must be in PATH  (sudo apt install ffmpeg)

The model is loaded once at import time and reused across requests.
Change MODEL_SIZE or DEVICE in your .env or here directly.
"""

import asyncio
import logging
import os
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
# Sizes: tiny, base, small, medium, large-v2, large-v3
# Use 'base' for fast CPU; 'medium' or 'large-v2' for higher accuracy on GPU.
MODEL_SIZE = os.getenv('WHISPER_MODEL', 'base')
DEVICE = os.getenv('WHISPER_DEVICE', 'cpu')          # 'cpu' or 'cuda'
COMPUTE_TYPE = os.getenv('WHISPER_COMPUTE', 'int8')  # 'int8' for CPU, 'float16' for GPU

_model = None


def _get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        logger.info('Loading Whisper model "%s" on %s …', MODEL_SIZE, DEVICE)
        _model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)
        logger.info('Whisper model ready.')
    return _model


# ── OGG → WAV conversion ──────────────────────────────────────────────────────

async def _convert_ogg_to_wav(ogg_path: str, wav_path: str) -> None:
    """Convert an OGG/OPUS file (Telegram's voice format) to 16 kHz mono WAV."""
    proc = await asyncio.create_subprocess_exec(
        'ffmpeg', '-y', '-i', ogg_path,
        '-ar', '16000', '-ac', '1', '-f', 'wav', wav_path,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f'ffmpeg conversion failed (code {proc.returncode})')


# ── Public API ────────────────────────────────────────────────────────────────

async def transcribe_voice(file_bytes: bytes, language: str = 'en') -> str:
    """
    Transcribe raw voice bytes (OGG/OPUS from Telegram) and return the text.

    Args:
        file_bytes: Raw bytes of the downloaded Telegram voice file.
        language:   ISO 639-1 language hint (e.g. 'en', 'fa').
                    Pass None to let Whisper auto-detect.

    Returns:
        Transcribed string, stripped of leading/trailing whitespace.

    Raises:
        RuntimeError: If ffmpeg conversion fails.
    """
    with tempfile.TemporaryDirectory() as tmp:
        ogg_path = str(Path(tmp) / 'voice.ogg')
        wav_path = str(Path(tmp) / 'voice.wav')

        # Write the bytes Telegram gave us
        with open(ogg_path, 'wb') as f:
            f.write(file_bytes)

        await _convert_ogg_to_wav(ogg_path, wav_path)

        # Run Whisper in a thread so it doesn't block the event loop
        loop = asyncio.get_running_loop()
        text = await loop.run_in_executor(None, _transcribe_sync, wav_path, language)

    return text.strip()


def _transcribe_sync(wav_path: str, language: str | None) -> str:
    model = _get_model()
    kwargs = {'beam_size': 5}
    if language:
        kwargs['language'] = language
    segments, _ = model.transcribe(wav_path, **kwargs)
    return ' '.join(seg.text for seg in segments)

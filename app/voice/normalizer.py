"""
Normalizes raw Whisper transcripts into clean text for intent matching.

Steps:
  1. Lowercase
  2. Strip punctuation that breaks regex (but keep #, ., :, -)
  3. Remove common speech filler words
  4. Collapse extra whitespace
"""

import re

# Filler words Whisper commonly produces or people say aloud
_FILLERS = re.compile(
    r'\b(um|uh|uhh|hmm|like|you know|i mean|basically|actually|literally|'
    r'so|well|okay|ok|right|yeah|yep|yes please|please|hey|hi|hello|'
    r'can you|could you|i want to|i would like to|i need to|'
    r'i\'d like to|would you)\b',
    re.IGNORECASE,
)

# Punctuation to strip (keep . for decimals, - for date ranges, # for task IDs)
_PUNCT = re.compile(r'[,!?;\'\"()\[\]{}]')


def normalize(text: str) -> str:
    """Return a cleaned, lowercase version of a Whisper transcript."""
    text = text.lower().strip()
    text = _PUNCT.sub(' ', text)
    text = _FILLERS.sub(' ', text)
    text = re.sub(r'\s{2,}', ' ', text).strip()
    return text

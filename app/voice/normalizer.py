"""
Normalizes raw Whisper transcripts into clean text for intent matching.

Pipeline:
  1. Lowercase
  2. Phonetic corrections  (common Whisper mishearings for this bot's vocabulary)
  3. Word numbers → digits  ("one hour" → "1 hour")
  4. Strip unhelpful punctuation
  5. Remove speech filler words
  6. Collapse whitespace
"""

import re

# ── 1. Phonetic corrections ───────────────────────────────────────────────────
# Whisper frequently mishears short command words. Map the common confusions
# to their canonical form BEFORE any other processing.
# Key: regex pattern  Value: replacement word
_PHONETIC = [
    # "log" variants
    (r'\bluck\b',   'log'),
    (r'\block\b',   'log'),
    (r'\blag\b',    'log'),
    (r'\blug\b',    'log'),
    (r'\blogue\b',  'log'),
    # "task" variants
    (r'\btax\b',    'task'),
    (r'\btusk\b',   'task'),
    (r'\btass\b',   'task'),
    # "done" variants
    (r'\bdun\b',    'done'),
    (r'\bdon\b',    'done'),
    (r'\bdawn\b',   'done'),
    # "hours" / "hour"
    (r'\bours\b',   'hours'),
    (r'\bpowers\b', 'hours'),
    # "flag" variants
    (r'\bflak\b',   'flag'),
    (r'\bflags\b',  'flag'),
    # "confirm" variants
    (r'\bconform\b', 'confirm'),
    # "draft" variants
    (r'\bdrafts\b',  'draft'),    # keep singular for matching
    # "ask" is already clear; "flag" already handled
    # "submit" variants
    (r'\bsubmit\b',  'submit'),   # usually correct, just reinforce
    (r'\bsubmitted\b', 'submit'),
    # "stats" variants
    (r'\bstats\b',   'stats'),
    (r'\bstatus\b',  'stats'),
    # "booked" variants
    (r'\bbook\b',    'booked'),
    # "replied"
    (r'\breply\b',   'replied'),
    (r'\breplie\b',  'replied'),
]

_PHONETIC_COMPILED = [(re.compile(p, re.IGNORECASE), r) for p, r in _PHONETIC]

# ── 2. Word numbers → digits ──────────────────────────────────────────────────
# Whisper spells out numbers; convert them so entity extractors find digits.
_WORD_NUMS = [
    (r'\btwelve\b',    '12'),
    (r'\beleven\b',    '11'),
    (r'\bten\b',       '10'),
    (r'\bnine\b',       '9'),
    (r'\beight\b',      '8'),
    (r'\bseven\b',      '7'),
    (r'\bsix\b',        '6'),
    (r'\bfive\b',       '5'),
    (r'\bfour\b',       '4'),
    (r'\bthree\b',      '3'),
    (r'\btwo\b',        '2'),
    (r'\bone\b',        '1'),
    (r'\bzero\b',       '0'),
    # fractions
    (r'\bhalf\s+an?\s+hour\b',          '0.5 hours'),
    (r'\ban?\s+hour\s+and\s+a\s+half\b','1.5 hours'),
    (r'\ban?\s+hour\b',                 '1 hour'),
    (r'\bquarter\s+(?:of\s+an?\s+)?hour\b', '0.25 hours'),
]

_WORD_NUMS_COMPILED = [(re.compile(p, re.IGNORECASE), r) for p, r in _WORD_NUMS]

# ── 3. Filler words ───────────────────────────────────────────────────────────
_FILLERS = re.compile(
    r'\b(um+|uh+|hmm+|like|you know|i mean|basically|actually|literally|'
    r'so|well|okay|ok|right|yeah|yep|hey|hi|hello|'
    r'can you|could you|would you|'
    r"i'd like to|i would like to)\b",
    re.IGNORECASE,
)

# ── 4. Punctuation to strip ───────────────────────────────────────────────────
_PUNCT = re.compile(r'[,!?;\'\"()\[\]{}]')


# ── Public API ────────────────────────────────────────────────────────────────

def normalize(text: str) -> str:
    """
    Full normalization pipeline.  Returns cleaned lowercase text ready for
    intent matching and entity extraction.
    """
    text = text.lower().strip()

    # Phonetic corrections first (before word-num substitution changes context)
    for pat, replacement in _PHONETIC_COMPILED:
        text = pat.sub(replacement, text)

    # Word numbers → digits (longest phrases first to avoid partial matches)
    for pat, replacement in _WORD_NUMS_COMPILED:
        text = pat.sub(replacement, text)

    # Strip unhelpful punctuation
    text = _PUNCT.sub(' ', text)

    # Remove filler words
    text = _FILLERS.sub(' ', text)

    # Collapse whitespace
    text = re.sub(r'\s{2,}', ' ', text).strip()

    return text

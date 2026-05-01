"""
Normalizes raw Whisper transcripts into clean text for intent matching.

Pipeline:
  1. Lowercase
  2. Phonetic corrections  (common Whisper mishearings for this bot's vocabulary)
  3. Word numbers → digits  ("one hour" → "1 hour", "twenty three" → "23")
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
    (r'\bluck\b',    'log'),
    (r'\block\b',    'log'),
    (r'\blag\b',     'log'),
    (r'\blug\b',     'log'),
    (r'\blogue\b',   'log'),
    (r'\blob\b',     'log'),
    # "task" variants
    (r'\btax\b',     'task'),
    (r'\btusk\b',    'task'),
    (r'\btass\b',    'task'),
    (r'\btas\b',     'task'),
    # "done" variants
    (r'\bdun\b',     'done'),
    (r'\bdon\b',     'done'),
    (r'\bdawn\b',    'done'),
    (r'\bdone\b',    'done'),   # reinforce
    # "hours" / "hour"
    (r'\bours\b',    'hours'),
    (r'\bpowers\b',  'hours'),
    (r'\bower\b',    'hour'),
    # "week" variants — Whisper often hears "weak"
    (r'\bweak\b',    'week'),
    (r'\bweeks\b',   'week'),
    # "flag" variants
    (r'\bflak\b',    'flag'),
    # NOTE: do NOT convert "flags" here — leave it for the intent to handle
    # "confirm" variants
    (r'\bconform\b', 'confirm'),
    (r'\bconfirm\b', 'confirm'),   # reinforce
    # "submit" variants
    (r'\bsubmit\b',  'submit'),    # reinforce
    (r'\bsubmitted\b', 'submit'),
    (r'\bsome\s+bit\b', 'submit'),
    # "stats" / "status"
    (r'\bstatus\b',  'stats'),
    # "booked" variants
    (r'\bbook\b',    'booked'),
    # "replied" variants
    (r'\breply\b',   'replied'),
    (r'\breplie\b',  'replied'),
    (r'\bwrote\s+back\b', 'replied'),
    (r'\bgot\s+back\b',   'replied'),
    # "no response" variants — normalise before router sees them
    (r'\bghostd?\b',     'ghosted'),
    (r'\bghosted\b',     'no response'),
    (r'\bno\s+reply\b',  'no response'),
    (r'\bnot\s+replying\b', 'no response'),
    (r"\bdidn'?t\s+reply\b", 'no response'),
    (r"\bhaven'?t\s+heard\b", 'no response'),
    # "assign" — "a sign" is two words, hard to fix, but "a-sign" can appear
    (r'\ba-sign\b',  'assign'),
    # "rate" — Whisper sometimes hears "raid"
    (r'\braid\b',    'rate'),
    # "schedule" — Whisper sometimes hears "shedule"
    (r'\bshedule\b', 'schedule'),
    # "draft" keep singular — do NOT convert "drafts"→"draft" (breaks list_drafts)
    # "ask" is already clear
]

_PHONETIC_COMPILED = [(re.compile(p, re.IGNORECASE), r) for p, r in _PHONETIC]

# ── 2. Word numbers → digits ──────────────────────────────────────────────────
# Whisper spells out numbers; convert them so entity extractors find digits.
# Order: compound phrases first, then teens, then tens, then ones.
_WORD_NUMS = [
    # Fractions (must come before plain "hour" patterns)
    (r'\bhalf\s+an?\s+hour\b',           '0.5 hours'),
    (r'\ban?\s+hour\s+and\s+a\s+half\b', '1.5 hours'),
    (r'\ban?\s+hour\b',                  '1 hour'),
    (r'\bquarter\s+(?:of\s+an?\s+)?hour\b', '0.25 hours'),
    # Teens (before tens to avoid "fourteen" → "four" + "teen")
    (r'\bnineteen\b',  '19'),
    (r'\beighteen\b',  '18'),
    (r'\bseventeen\b', '17'),
    (r'\bsixteen\b',   '16'),
    (r'\bfifteen\b',   '15'),
    (r'\bfourteen\b',  '14'),
    (r'\bthirteen\b',  '13'),
    # Tens
    (r'\bninety\b',    '90'),
    (r'\beighty\b',    '80'),
    (r'\bseventy\b',   '70'),
    (r'\bsixty\b',     '60'),
    (r'\bfifty\b',     '50'),
    (r'\bforty\b',     '40'),
    (r'\bthirty\b',    '30'),
    (r'\btwenty\b',    '20'),
    # Ones (after teens/tens so "twelve" isn't "two"+"lve")
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
]

_WORD_NUMS_COMPILED = [(re.compile(p, re.IGNORECASE), r) for p, r in _WORD_NUMS]

# ── 3. Filler words ───────────────────────────────────────────────────────────
_FILLERS = re.compile(
    r'\b(um+|uh+|hmm+|like|you know|i mean|basically|actually|literally|'
    r'so|well|okay|ok|right|yeah|yep|hey|hi|hello|please|'
    r'can you|could you|would you|'
    r"i'd like to|i would like to|i want to|i need to|i have to)\b",
    re.IGNORECASE,
)

# ── 4. Punctuation to strip ───────────────────────────────────────────────────
_PUNCT = re.compile(r'[,!?;\'\"()\[\]{}\-–—…:]')


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

"""
Entity extractors for voice command arguments.

Each function takes a normalized text string and returns a typed value
(or None if nothing was found), so the router can build context.args lists
that exactly match what the existing handlers expect.
"""

import re
from datetime import date, timedelta

# ── Date ─────────────────────────────────────────────────────────────────────

_WEEKDAY_NAMES = {
    'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
    'friday': 4, 'saturday': 5, 'sunday': 6,
}

_MONTH_NAMES = {
    'january': 1, 'february': 2, 'march': 3, 'april': 4,
    'may': 5, 'june': 6, 'july': 7, 'august': 8,
    'september': 9, 'october': 10, 'november': 11, 'december': 12,
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4,
    'jun': 6, 'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
}

_WEEKDAY_PAT = '|'.join(_WEEKDAY_NAMES)


def extract_date(text: str) -> str | None:
    """
    Return a date string understood by the hours_command handler:
      - 'today'
      - 'yesterday'
      - 'YYYY-MM-DD'  (for any specific date mentioned)

    Returns None if no date is found (caller should default to 'today').

    Supports:
      - today / yesterday / the day before yesterday / 2 days ago
      - last Monday / this Monday / next Monday / on Monday
      - April 30 / 30 April
      - ISO dates: 2026-04-30
    """
    t = text.lower()

    if re.search(r'\btoday\b', t):
        return 'today'
    if re.search(r'\byesterday\b', t):
        return 'yesterday'
    if re.search(r'\bday\s+before\s+yesterday\b|2\s+days?\s+ago\b', t):
        return (date.today() - timedelta(days=2)).strftime('%Y-%m-%d')

    # "next Monday" → the coming weekday (always in the future)
    m = re.search(r'\bnext\s+(' + _WEEKDAY_PAT + r')\b', t)
    if m:
        target_wd = _WEEKDAY_NAMES[m.group(1)]
        today = date.today()
        days_ahead = (target_wd - today.weekday()) % 7 or 7
        return (today + timedelta(days=days_ahead)).strftime('%Y-%m-%d')

    # "this Monday" → nearest occurrence of that weekday (past or upcoming this week)
    m = re.search(r'\bthis\s+(' + _WEEKDAY_PAT + r')\b', t)
    if m:
        target_wd = _WEEKDAY_NAMES[m.group(1)]
        today = date.today()
        # If that weekday is today or already passed this week, use today's week start
        days_diff = today.weekday() - target_wd
        if days_diff >= 0:
            d = today - timedelta(days=days_diff)
        else:
            d = today + timedelta(days=-days_diff)
        return d.strftime('%Y-%m-%d')

    # "last Monday" / "on Monday" / bare weekday name → most recent past occurrence
    m = re.search(r'(?:last\s+)?(?:on\s+)?(' + _WEEKDAY_PAT + r')\b', t)
    if m:
        target_wd = _WEEKDAY_NAMES[m.group(1)]
        today = date.today()
        days_back = (today.weekday() - target_wd) % 7 or 7
        d = today - timedelta(days=days_back)
        return d.strftime('%Y-%m-%d')

    # "April 30" / "30 April"
    month_pat = '|'.join(_MONTH_NAMES)
    m = re.search(rf'({month_pat})\s+(\d{{1,2}})', t)
    if m:
        month = _MONTH_NAMES[m.group(1)]
        day = int(m.group(2))
        year = date.today().year
        try:
            return date(year, month, day).strftime('%Y-%m-%d')
        except ValueError:
            pass

    m = re.search(rf'(\d{{1,2}})\s+({month_pat})', t)
    if m:
        day = int(m.group(1))
        month = _MONTH_NAMES[m.group(2)]
        year = date.today().year
        try:
            return date(year, month, day).strftime('%Y-%m-%d')
        except ValueError:
            pass

    # ISO / numeric: 2026-04-30
    m = re.search(r'\b(\d{4}-\d{2}-\d{2})\b', t)
    if m:
        return m.group(1)

    return None


# ── Hours ─────────────────────────────────────────────────────────────────────

def extract_hours(text: str) -> str | None:
    """
    Return hours as a string float, e.g. '3', '2.5', '0.5'.

    Assumes normalizer has already converted word numbers to digits
    ("one" → "1", "half an hour" → "0.5 hours"), but also handles
    the raw forms as a fallback.
    """
    t = text.lower()

    # Fallback word forms (in case normalizer wasn't applied)
    if re.search(r'\ban?\s+hour\s+and\s+a\s+half\b', t):
        return '1.5'
    if re.search(r'\bhalf\s+an?\s+hour\b', t):
        return '0.5'
    if re.search(r'\ban?\s+hour\b', t):
        return '1'

    # Digit adjacent to "hour(s)" — most reliable signal
    m = re.search(r'(\d+(?:\.\d+)?)\s*hours?', t)
    if m:
        return m.group(1)

    # Digit alone in an hours context (e.g. "log 3 today")
    m = re.search(r'\b(\d+(?:\.\d+)?)\b', t)
    if m:
        val = float(m.group(1))
        if 0 < val <= 24:
            return m.group(1)

    return None


# ── Numbers (task IDs, user IDs) ──────────────────────────────────────────────

def extract_number(text: str) -> str | None:
    """Return the first integer found, as a string (for task/user IDs)."""
    m = re.search(r'#?(\d+)', text)
    return m.group(1) if m else None


def extract_all_numbers(text: str) -> list[str]:
    """Return all integers found (for commands needing two IDs)."""
    return re.findall(r'#?(\d+)', text)


# ── Platform (for /draft) ─────────────────────────────────────────────────────

# Ordered by specificity: longer/rarer names first to avoid substring collisions
_PLATFORM_PATTERNS = [
    (r'\blinkedin\b',           'linkedin'),
    (r'\binstagram\b',          'instagram'),
    (r'\bfacebook\b',           'facebook'),
    (r'\btiktok\b',             'tiktok'),
    (r'\btwitter\b|\btweet\b',  'twitter'),
    (r'\bx\.?com\b|\bx post\b', 'twitter'),
    (r'\bemail\b|\bmail\b',     'email'),
]

_PLATFORM_COMPILED = [(re.compile(p, re.IGNORECASE), name) for p, name in _PLATFORM_PATTERNS]


def extract_platform(text: str) -> str:
    """Return a draft platform name, defaulting to 'other'."""
    for pat, name in _PLATFORM_COMPILED:
        if pat.search(text):
            return name
    return 'other'


# ── Remainder text (message body / description / note) ────────────────────────

def strip_command_words(text: str, *words: str) -> str:
    """
    Repeatedly strip leading command/trigger words from text to leave just
    the payload.

    E.g. strip_command_words('create task fix the login bug', 'create', 'task')
    → 'fix the login bug'

    Only strips from the front so content words in the middle are preserved.
    """
    pattern = re.compile(
        r'^\s*(?:' + '|'.join(re.escape(w) for w in words) + r')\s*',
        re.IGNORECASE,
    )
    prev = None
    while prev != text:
        prev = text
        text = pattern.sub('', text).strip()
    return text

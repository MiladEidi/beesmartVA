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


def extract_date(text: str) -> str | None:
    """
    Return a date string understood by the hours_command handler:
      - 'today'
      - 'yesterday'
      - 'YYYY-MM-DD'  (for any specific date mentioned)

    Returns None if no date is found (caller should default to 'today').
    """
    t = text.lower()

    if re.search(r'\btoday\b', t):
        return 'today'
    if re.search(r'\byesterday\b', t):
        return 'yesterday'

    # "last Monday" / "on Monday"
    m = re.search(
        r'(?:last\s+)?('
        + '|'.join(_WEEKDAY_NAMES)
        + r')\b',
        t,
    )
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

    # ISO / numeric: 2026-04-30 or 04/30
    m = re.search(r'\b(\d{4}-\d{2}-\d{2})\b', t)
    if m:
        return m.group(1)

    return None


# ── Hours ─────────────────────────────────────────────────────────────────────

def extract_hours(text: str) -> str | None:
    """
    Return hours as a string float, e.g. '3', '2.5', '0.5'.
    Handles:
      - "3 hours" / "3.5 hours"
      - "half an hour" → '0.5'
      - "an hour" / "one hour" → '1'
      - "an hour and a half" → '1.5'
    """
    t = text.lower()

    if re.search(r'\bhalf\s+an?\s+hour\b', t):
        return '0.5'
    if re.search(r'\ban?\s+hour\s+and\s+a\s+half\b', t):
        return '1.5'
    if re.search(r'\ban?\s+hour\b', t) or re.search(r'\bone\s+hour\b', t):
        return '1'

    m = re.search(r'(\d+(?:\.\d+)?)\s*hours?', t)
    if m:
        return m.group(1)

    # bare number immediately adjacent to hours context
    m = re.search(r'\b(\d+(?:\.\d+)?)\b', t)
    if m:
        val = float(m.group(1))
        if 0 < val <= 24:  # sanity check: plausible work hours
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

_PLATFORMS = {'linkedin', 'email', 'instagram', 'other'}

def extract_platform(text: str) -> str:
    """Return a draft platform name, defaulting to 'other'."""
    t = text.lower()
    for p in _PLATFORMS:
        if p in t:
            return p
    return 'other'


# ── Remainder text (message body / description / note) ────────────────────────

def strip_command_words(text: str, *words: str) -> str:
    """
    Remove a set of leading command/trigger words from text to leave just
    the payload.  E.g. strip_command_words('create task fix the login bug', 'create', 'task')
    → 'fix the login bug'
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

"""
Signal-scoring voice command router.

How it works
────────────
Each intent defines two sets of regex signals:

  required  — ALL patterns in this list must match somewhere in the text.
               If any required signal is absent → intent score = 0 (skip it).

  boosts    — Each pattern that matches adds +1 to the score.
               These are optional confirmations that raise confidence.

route() scores every intent against the normalized text and returns the one
with the highest non-zero score.  Ties are broken by list order (more
specific intents are listed first).

Why this beats first-match regex
─────────────────────────────────
• Word ORDER doesn't matter — signals are tested with re.search anywhere.
• A single keyword can be enough (required=[r'\bhour\b']).
• Whisper mishearings that pass phonetic correction still produce partial
  signal matches, so "luck 1 hour today" still fires log_hours.
• Adding a new command = adding a new Intent() block. No regex ordering
  headache.

Adding a new intent
───────────────────
Append an Intent() to _INTENT_SPECS with:
  required  — what MUST be present (list of regex strings, ALL must hit)
  boosts    — what HELPS score (list of regex strings, each adds 1)
  handler   — the existing handler function key (string)
  build_args— (normalized_text) -> list[str] for context.args
"""

import re
from dataclasses import dataclass, field
from typing import Callable

from app.voice.entities import (
    extract_date,
    extract_hours,
    extract_number,
    extract_all_numbers,
    extract_platform,
    strip_command_words,
)


# ── Result ────────────────────────────────────────────────────────────────────

@dataclass
class RouteResult:
    intent: str
    handler: Callable
    args: list[str]


# ── Intent definition ─────────────────────────────────────────────────────────

@dataclass
class Intent:
    name: str
    required: list[str]          # ALL must match
    boosts: list[str]            # each match adds +1
    handler_key: str
    build_args: Callable         # (text: str) -> list[str]
    _req_compiled: list = field(default_factory=list, repr=False)
    _boost_compiled: list = field(default_factory=list, repr=False)

    def compile(self):
        self._req_compiled = [re.compile(p, re.IGNORECASE) for p in self.required]
        self._boost_compiled = [re.compile(p, re.IGNORECASE) for p in self.boosts]

    def score(self, text: str) -> int:
        """Return 0 if any required signal is absent, else 1 + boost count."""
        if not all(p.search(text) for p in self._req_compiled):
            return 0
        return 1 + sum(1 for p in self._boost_compiled if p.search(text))


# ── Arg builders ──────────────────────────────────────────────────────────────

def _hours_args(text: str) -> list[str]:
    hours = extract_hours(text)
    day = extract_date(text) or 'today'
    note = strip_command_words(
        text,
        # leading polite words
        'i', 'want', 'to', 'please', 'a', 'the',
        # command verbs
        'log', 'add', 'record', 'work', 'worked', 'clock', 'clocked',
        # time words — stripped so only the actual note remains
        'hours', 'hour', 'today', 'yesterday',
        'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday',
        'for', 'on',
        # strip the extracted hours digit itself
        *(hours,) if hours else (),
    )
    args = [day, hours or '0']
    if note:
        args += note.split()
    return args


def _draft_args(text: str) -> list[str]:
    platform = extract_platform(text)
    content = strip_command_words(
        text,
        'create', 'write', 'new', 'submit', 'draft', 'a', 'for', 'the',
        'linkedin', 'email', 'instagram', 'facebook', 'twitter', 'tiktok', 'social', 'other',
    )
    return [platform] + content.split()


def _first_number_args(text: str) -> list[str]:
    n = extract_number(text)
    return [n] if n else []


def _two_number_args(text: str) -> list[str]:
    return extract_all_numbers(text)[:2]


def _remainder_args(text: str, *strip: str) -> list[str]:
    return strip_command_words(text, *strip).split()


# ── Intent registry ───────────────────────────────────────────────────────────
# Order matters only for tie-breaking. Put more specific intents first.

_INTENT_SPECS = [

    # ── Tasks ─────────────────────────────────────────────────────────────────

    # "done 5", "task 5 done", "mark 5 complete" — needs BOTH a number AND done-word
    Intent(
        name='done_task',
        required=[r'\b(?:done|complete|finish(?:ed)?|completed)\b', r'\b\d+\b'],
        boosts=[r'\btask\b', r'\bmark\b', r'\bset\b'],
        handler_key='done_command',
        build_args=_first_number_args,
    ),

    # "can't do task 5 skill", "cantdo 5 time because …"
    Intent(
        name='cantdo_task',
        required=[r"\b(?:can'?t|cannot|can\s+not|cantdo)\b", r'\b\d+\b'],
        boosts=[r'\btask\b', r'\b(?:skill|time)\b'],
        handler_key='cantdo_command',
        build_args=lambda t: (
            lambda nums, reason: nums[:1] + ([reason] if reason else [])
        )(
            extract_all_numbers(t),
            next(iter(re.findall(r'\b(skill|time)\b', t, re.I)), None),
        ),
    ),

    # "assign task 3 to user 7"
    Intent(
        name='assign_task',
        required=[r'\bassign\b', r'\b\d+\b'],
        boosts=[r'\btask\b', r'\bto\b', r'\buser\b'],
        handler_key='assign_command',
        build_args=_two_number_args,
    ),

    # "overdue tasks"
    Intent(
        name='overdue_tasks',
        required=[r'\boverdue\b'],
        boosts=[r'\btask[s]?\b', r'\bshow\b', r'\blist\b'],
        handler_key='overdue_command',
        build_args=lambda t: [],
    ),

    # "flagged tasks", "blocked tasks"
    Intent(
        name='flagged_tasks',
        required=[r'\b(?:flagged|blocked)\b'],
        boosts=[r'\btask[s]?\b', r'\bshow\b', r'\blist\b'],
        handler_key='flagged_command',
        build_args=lambda t: [],
    ),

    # "create task fix the login bug" — needs "task" but NOT a lone number + done
    Intent(
        name='create_task',
        required=[r'\btask\b'],
        boosts=[r'\b(?:create|add|new|make|write|log)\b', r'\b(?:for|to)\b'],
        handler_key='task_command',
        build_args=lambda t: _remainder_args(
            t, 'create', 'add', 'new', 'make', 'write', 'log', 'a', 'task', 'to', 'for',
        ),
    ),

    # "show tasks", "list tasks", "open tasks", "tasks"
    Intent(
        name='list_tasks',
        required=[r'\btasks\b'],
        boosts=[r'\b(?:show|list|open|all|current|what|get)\b'],
        handler_key='tasks_command',
        build_args=lambda t: [],
    ),

    # ── Hours ──────────────────────────────────────────────────────────────────

    # "submit hours", "send timesheet", "send my hours"
    Intent(
        name='submit_hours',
        required=[r'\b(?:submit|send)\b', r'\b(?:hours?|timesheet)\b'],
        boosts=[r'\bmy\b', r'\bweek\b'],
        handler_key='submit_hours_command',
        build_args=lambda t: [],
    ),

    # "my week", "this week's hours", "how many hours this week"
    Intent(
        name='my_week',
        required=[r'\bweek\b'],
        boosts=[r'\bmy\b', r'\bhours?\b', r'\bthis\b', r'\bhow\s+many\b'],
        handler_key='myweek_command',
        build_args=lambda t: [],
    ),

    # "log 3 hours today for client calls" — needs a number AND hour-word
    Intent(
        name='log_hours',
        required=[r'\b\d+(?:\.\d+)?\b', r'\bhours?\b'],
        boosts=[
            r'\b(?:log|add|record|work(?:ed)?|clock(?:ed)?)\b',
            r'\b(?:today|yesterday|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b',
            r'\bfor\b',
        ],
        handler_key='hours_command',
        build_args=_hours_args,
    ),

    # "show timesheets", "pending timesheets"
    Intent(
        name='list_timesheets',
        required=[r'\btimesheets?\b'],
        boosts=[r'\b(?:show|list|pending)\b'],
        handler_key='timesheets_command',
        build_args=lambda t: [],
    ),

    # ── Rate ──────────────────────────────────────────────────────────────────

    # "what's my rate", "my hourly rate", "show my rate"
    Intent(
        name='my_rate',
        required=[r'\brate\b'],
        boosts=[r'\b(?:my|hourly|what|show|check|salary)\b'],
        handler_key='rate_command',
        build_args=lambda t: [],
    ),

    # ── Check-ins / Escalations ────────────────────────────────────────────────

    # "ask supervisor about X", "I have a question: X"
    Intent(
        name='ask_supervisor',
        required=[r'\b(?:ask|question)\b'],
        boosts=[r'\b(?:supervisor|manager|about|regarding)\b'],
        handler_key='ask_command',
        build_args=lambda t: _remainder_args(t, 'ask', 'supervisor', 'manager', 'about', 'question', 'for', 'a'),
    ),

    # "flag issue X", "I have a problem: X", "there's a blocker"
    Intent(
        name='flag_issue',
        required=[r'\b(?:flag|problem|issue|blocker|blocked)\b'],
        boosts=[r'\b(?:raise|report|have|there)\b'],
        handler_key='flag_command',
        build_args=lambda t: _remainder_args(t, 'flag', 'issue', 'problem', 'blocker', 'blocked', 'raise', 'report', 'a', 'have'),
    ),

    # "confirm whether X", "need approval for X"
    Intent(
        name='confirm_request',
        required=[r'\b(?:confirm|approve|approval|confirmation)\b'],
        boosts=[r'\b(?:supervisor|manager|whether|need|get)\b'],
        handler_key='confirm_command',
        build_args=lambda t: _remainder_args(t, 'confirm', 'approve', 'approval', 'confirmation', 'supervisor', 'manager', 'whether', 'need', 'get', 'a'),
    ),

    # "notify client: X", "tell the client X", "message the client X"
    Intent(
        name='notify_client',
        required=[r'\b(?:notify|message|tell)\b', r'\bclient\b'],
        boosts=[r'\b(?:send|about)\b'],
        handler_key='notify_client_command',
        build_args=lambda t: _remainder_args(t, 'notify', 'message', 'tell', 'send', 'the', 'client', 'about', 'a'),
    ),

    # "stats", "team dashboard", "how is the team doing"
    Intent(
        name='stats',
        required=[r'\b(?:stats|dashboard)\b'],
        boosts=[r'\b(?:team|show|how)\b'],
        handler_key='stats_command',
        build_args=lambda t: [],
    ),

    # ── Follow-ups ────────────────────────────────────────────────────────────

    # "new connection John on LinkedIn"
    Intent(
        name='new_connection',
        required=[r'\bconnect(?:ion|ed)?\b'],
        boosts=[r'\b(?:new|add|log)\b', r'\b(?:linkedin|twitter|instagram|facebook|tiktok|email)\b'],
        handler_key='connection_command',
        build_args=lambda t: _remainder_args(t, 'new', 'add', 'log', 'connection', 'connected', 'with', 'on'),
    ),

    # "show follow-ups", "who do I need to follow up"
    Intent(
        name='list_followups',
        required=[r'\bfollow.?ups?\b'],
        boosts=[r'\b(?:show|list|pending|who|any)\b'],
        handler_key='followups_command',
        build_args=lambda t: [],
    ),

    # "follow-up done with John", "followed up with John"
    Intent(
        name='follow_done',
        required=[r'\bfollow(?:ed)?\s*(?:up)?\b', r'\b(?:done|complete|finished)\b'],
        boosts=[r'\bwith\b'],
        handler_key='followdone_command',
        build_args=lambda t: _remainder_args(t, 'follow', 'up', 'followed', 'done', 'complete', 'finished', 'with'),
    ),

    # "John replied", "got a reply from Sarah", "Sarah responded", "wrote back"
    Intent(
        name='replied',
        required=[r'\b(?:replied|reply|responded|response|wrote\s+back|got\s+back)\b'],
        boosts=[r'\b(?:from|got|back)\b'],
        handler_key='replied_command',
        build_args=lambda t: _remainder_args(t, 'replied', 'reply', 'responded', 'response', 'wrote', 'got', 'back', 'from', 'a'),
    ),

    # "meeting booked with John", "John is booked", "scheduled a call with John"
    Intent(
        name='booked',
        required=[r'\b(?:booked?|scheduled?\s+(?:a\s+)?(?:meeting|call|appointment))\b'],
        boosts=[r'\b(?:meeting|call|appointment|with)\b'],
        handler_key='booked_command',
        build_args=lambda t: _remainder_args(t, 'booked', 'book', 'scheduled', 'schedule', 'meeting', 'call', 'appointment', 'with', 'a'),
    ),

    # "no response from John", "John didn't respond", "ghosted", "no reply from"
    Intent(
        name='no_response',
        required=[r'\b(?:no\s+response|no\s+reply|noresponse|didn.?t\s+(?:respond|reply)|ghosted|haven.?t\s+heard|not\s+respond)\b'],
        boosts=[r'\b(?:from|close)\b'],
        handler_key='noresponse_command',
        build_args=lambda t: _remainder_args(t, 'no', 'response', 'reply', 'noresponse', 'not', 'respond', "didn't", 'didnt', "haven't", 'havent', 'heard', 'ghosted', 'from', 'close'),
    ),

    # ── Drafts ────────────────────────────────────────────────────────────────

    # "list drafts", "show my drafts"
    # NOTE: uses draft[s]? so it matches even if normalizer didn't fire
    Intent(
        name='list_drafts',
        required=[r'\bdraft[s]?\b'],
        boosts=[r'\b(?:show|list|my|all|pending)\b'],
        handler_key='drafts_command',
        build_args=lambda t: [],
    ),

    # "mark draft ABC as posted", "posted ABC"
    Intent(
        name='mark_posted',
        required=[r'\bposted\b'],
        boosts=[r'\b(?:draft|mark)\b'],
        handler_key='posted_command',
        build_args=lambda t: _remainder_args(t, 'mark', 'draft', 'posted', 'as'),
    ),

    # "create a LinkedIn draft: …"  (singular 'draft', with create/platform boost)
    Intent(
        name='create_draft',
        required=[r'\bdraft\b'],
        boosts=[r'\b(?:create|write|new|submit)\b', r'\b(?:linkedin|email|instagram|facebook|twitter|tiktok|social)\b'],
        handler_key='draft_command',
        build_args=_draft_args,
    ),

    # ── Reports ───────────────────────────────────────────────────────────────

    Intent(
        name='weekly_report',
        required=[r'\bweekly\b'],
        boosts=[r'\b(?:report|summary|generate|show)\b'],
        handler_key='weekly_command',
        build_args=lambda t: [],
    ),

    Intent(
        name='monthly_report',
        required=[r'\bmonthly\b'],
        boosts=[r'\b(?:report|summary|overview|generate|show)\b'],
        handler_key='monthly_command',
        build_args=lambda t: [],
    ),

    Intent(
        name='full_report',
        required=[r'\breport\b'],
        boosts=[r'\b(?:full|executive|complete|overall|all)\b'],
        handler_key='report_all_command',
        build_args=lambda t: [],
    ),

    # ── Scores ────────────────────────────────────────────────────────────────

    Intent(
        name='send_scorecheck',
        required=[r'\b(?:scorecheck|satisfaction)\b', r'\b(?:send|ask|check)\b'],
        boosts=[r'\bclient\b'],
        handler_key='send_scorecheck_command',
        build_args=lambda t: [],
    ),

    Intent(
        name='show_scores',
        required=[r'\bscores?\b'],
        boosts=[r'\b(?:show|list|satisfaction|client|ratings?)\b'],
        handler_key='scores_command',
        build_args=lambda t: [],
    ),

    # ── Team / Users ──────────────────────────────────────────────────────────

    # "show all users", "list team members", "who's in the group", "groups"
    Intent(
        name='list_users',
        required=[r'\b(?:users?|team|group[s]?|members?|people|roster)\b'],
        boosts=[r'\b(?:show|list|all|who|registered|everyone)\b'],
        handler_key='groups_command',
        build_args=lambda t: [],
    ),

    # ── Info / Meta ───────────────────────────────────────────────────────────

    # "show my schedule", "client schedule", "meeting schedule"
    Intent(
        name='show_schedule',
        required=[r'\bschedule\b'],
        boosts=[r'\b(?:show|my|client|meeting|upcoming|calendar)\b'],
        handler_key='schedule_command',
        build_args=lambda t: [],
    ),

    # "show links", "booking links", "show booking link", "calendar link"
    Intent(
        name='show_links',
        required=[r'\b(?:links?|booking)\b'],
        boosts=[r'\b(?:show|my|booking|calendar)\b'],
        handler_key='links_command',
        build_args=lambda t: [],
    ),

    # "contacts", "show contacts", "client contacts"
    Intent(
        name='show_contacts',
        required=[r'\bcontacts?\b'],
        boosts=[r'\b(?:show|list|my|client)\b'],
        handler_key='contacts_command',
        build_args=lambda t: [],
    ),

    # "my preferences", "show settings", "prefs"
    Intent(
        name='show_prefs',
        required=[r'\b(?:prefs?|preferences?|settings?)\b'],
        boosts=[r'\b(?:show|my|view)\b'],
        handler_key='prefs_command',
        build_args=lambda t: [],
    ),

    Intent(
        name='profile',
        required=[r'\bprofile\b'],
        boosts=[r'\b(?:show|my|who)\b'],
        handler_key='profile_command',
        build_args=lambda t: [],
    ),

    Intent(
        name='help',
        required=[r'\bhelp\b'],
        boosts=[r'\b(?:what|can|commands?)\b'],
        handler_key='help_command',
        build_args=lambda t: [],
    ),

    Intent(
        name='menu',
        required=[r'\bmenu\b'],
        boosts=[r'\b(?:open|show)\b'],
        handler_key='menu_command',
        build_args=lambda t: [],
    ),
]


# ── Handler registry (lazy, avoids circular imports) ─────────────────────────

def _load_handlers() -> dict[str, Callable]:
    from app.handlers.tasks import (
        task_command, tasks_command, done_command,
        cantdo_command, assign_command, overdue_command, flagged_command,
    )
    from app.handlers.hours import (
        hours_command, myweek_command, submit_hours_command,
        timesheets_command, rate_command,
    )
    from app.handlers.checkins import (
        ask_command, flag_command, confirm_command,
        notify_client_command, stats_command,
    )
    from app.handlers.followups import (
        connection_command, followups_command, followdone_command,
        replied_command, booked_command, noresponse_command,
    )
    from app.handlers.drafts import draft_command, drafts_command, posted_command
    from app.handlers.reports import weekly_command, monthly_command, report_all_command
    from app.handlers.scores import scores_command, send_scorecheck_command
    from app.handlers.common import (
        profile_command, help_command, links_command,
        contacts_command, schedule_command, prefs_command,
    )
    from app.handlers.admin import groups_command
    from app.handlers.ui import menu_command
    return {k: v for k, v in locals().items()}


_handlers: dict | None = None
_compiled: bool = False


def _get_intents() -> list[Intent]:
    global _handlers, _compiled
    if not _compiled:
        _handlers = _load_handlers()
        for intent in _INTENT_SPECS:
            intent.handler = _handlers[intent.handler_key]
            intent.compile()
        _compiled = True
    return _INTENT_SPECS


# ── Public API ────────────────────────────────────────────────────────────────

def route(normalized_text: str) -> RouteResult | None:
    """
    Score every intent against normalized_text.
    Returns the highest-scoring RouteResult, or None if nothing matched.
    """
    best_score = 0
    best: Intent | None = None

    for intent in _get_intents():
        s = intent.score(normalized_text)
        if s > best_score:
            best_score = s
            best = intent

    if best is None:
        return None

    args = best.build_args(normalized_text)
    return RouteResult(intent=best.name, handler=best.handler, args=args)

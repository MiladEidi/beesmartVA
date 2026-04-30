"""
Regex-based voice command router.

How it works
────────────
1.  The normalized transcript is tested against every intent's patterns
    (using re.search — so the phrase can appear anywhere in the sentence).
2.  The first matching intent wins (intents are ordered most-specific first).
3.  The intent's `build_args` callable receives the regex match + the full
    normalized text and returns the list that will be assigned to context.args.
4.  `route()` returns a RouteResult(handler_fn, args) or None if nothing matched.

Adding a new intent
───────────────────
Append an entry to INTENTS:

    Intent(
        name='my_command',
        patterns=[r'pattern one', r'pattern two'],
        handler=my_handler_fn,
        build_args=lambda m, text: [m.group(1), m.group(2)],
    )

The patterns list is tried in order; stop on first match.
`build_args` receives (match_object | None, full_normalized_text).
When you don't need capture groups, just ignore `m`.
"""

import re
from dataclasses import dataclass
from typing import Callable

from app.voice.entities import (
    extract_date,
    extract_hours,
    extract_number,
    extract_all_numbers,
    extract_platform,
    strip_command_words,
)

# ── Result type ───────────────────────────────────────────────────────────────

@dataclass
class RouteResult:
    intent: str
    handler: Callable
    args: list[str]          # exactly what gets set on context.args


# ── Helpers for complex arg builders (must be defined before _INTENT_SPECS) ───

def _build_hours_args(m, text: str) -> list[str]:
    """Build args for hours_command: [date, hours, ...note_words]"""
    hours = extract_hours(text)
    day = extract_date(text) or 'today'
    note = strip_command_words(
        text,
        'log', 'add', 'record', 'worked', 'clocked', 'hours', 'hour',
        'today', 'yesterday', 'monday', 'tuesday', 'wednesday', 'thursday',
        'friday', 'saturday', 'sunday', 'for', 'on',
        *(hours,) if hours else (),
    )
    args = [day, hours or '0']
    if note:
        args += note.split()
    return args


def _build_draft_args(m, text: str) -> list[str]:
    """Build args for draft_command: [platform, ...content_words]"""
    platform = extract_platform(text)
    content = strip_command_words(
        text,
        'create', 'write', 'new', 'submit', 'draft', 'a', 'for',
        'linkedin', 'email', 'instagram', 'social', 'other',
    )
    return [platform] + content.split()


# ── Intent registry ───────────────────────────────────────────────────────────

@dataclass
class Intent:
    name: str
    patterns: list[str]
    handler: Callable
    build_args: Callable      # (re.Match | None, normalized_text) -> list[str]
    _compiled: list = None

    def compile(self):
        self._compiled = [re.compile(p, re.IGNORECASE) for p in self.patterns]

    def match(self, text: str):
        for pat in self._compiled:
            m = pat.search(text)
            if m:
                return m
        return None


# Lazy import of handlers to avoid circular imports at module load
def _handlers():
    from app.handlers.tasks import (
        task_command, tasks_command, done_command,
        cantdo_command, assign_command, overdue_command, flagged_command,
    )
    from app.handlers.hours import (
        hours_command, myweek_command, submit_hours_command,
        timesheets_command,
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
    from app.handlers.common import profile_command, help_command, guide_command
    from app.handlers.ui import menu_command
    return {k: v for k, v in locals().items()}


# ── Intent definitions ────────────────────────────────────────────────────────
# Ordered most-specific → most-general.
# Each entry is a tuple:
#   (name, [patterns], handler_key, build_args_fn)

_INTENT_SPECS = [

    # ── Tasks ─────────────────────────────────────────────────────────────────

    ('done_task', [
        r'(?:mark|set)?\s*task\s+#?(\d+)\s+(?:as\s+)?(?:done|complete|finished)',
        r'(?:done|complete|finish)\s+task\s+#?(\d+)',
        r'task\s+#?(\d+)\s+(?:is\s+)?done',
        r'#?(\d+)\s+(?:is\s+)?done',
        r'done\s+#?(\d+)',
    ], 'done_command',
        lambda m, t: [m.group(1)]
    ),

    ('cantdo_task', [
        r"(?:can't|cannot|can not)\s+do\s+task\s+#?(\d+)\s+(skill|time)(?:\s+(.+))?",
        r'cantdo\s+#?(\d+)\s+(skill|time)(?:\s+(.+))?',
        r'flag\s+task\s+#?(\d+)\s+(?:as\s+)?(skill|time)(?:\s+(.+))?',
    ], 'cantdo_command',
        lambda m, t: [m.group(1), m.group(2)] + ([m.group(3)] if m.group(3) else [])
    ),

    ('assign_task', [
        r'assign\s+task\s+#?(\d+)\s+to\s+(?:user\s+)?#?(\d+)',
        r'assign\s+#?(\d+)\s+to\s+#?(\d+)',
    ], 'assign_command',
        lambda m, t: [m.group(1), m.group(2)]
    ),

    ('create_task', [
        r'(?:create|add|new|make|log)\s+(?:a\s+)?task\s+(?:to\s+|for\s+)?(.+)',
        r'task[:\s]+(.+)',
        r'to.?do[:\s]+(.+)',
        r'remind\s+(?:me\s+)?to\s+(.+)',
    ], 'task_command',
        lambda m, t: [m.group(1).strip()]
    ),

    ('list_tasks', [
        r'(?:show|list|what are|get|display)\s+(?:all\s+)?(?:the\s+)?(?:open\s+)?tasks',
        r'(?:any|open|current)\s+tasks',
        r'^tasks\s*$',
    ], 'tasks_command',
        lambda m, t: []
    ),

    ('overdue_tasks', [
        r'(?:show|list|any|what are)?\s*overdue\s+tasks',
        r'tasks\s+(?:that are\s+)?overdue',
    ], 'overdue_command',
        lambda m, t: []
    ),

    ('flagged_tasks', [
        r'(?:show|list|any)?\s*flagged\s+tasks',
        r'tasks\s+(?:that are\s+)?flagged',
        r'blocked\s+tasks',
    ], 'flagged_command',
        lambda m, t: []
    ),

    # ── Hours ──────────────────────────────────────────────────────────────────

    ('submit_hours', [
        r'submit\s+(?:my\s+)?(?:hours|timesheet)',
        r'send\s+(?:my\s+)?(?:hours|timesheet)',
    ], 'submit_hours_command',
        lambda m, t: []
    ),

    ('my_week', [
        r'(?:show\s+)?my\s+week',
        r'(?:this\s+)?week(?:\'s)?\s+hours',
        r'how\s+many\s+hours\s+this\s+week',
    ], 'myweek_command',
        lambda m, t: []
    ),

    ('log_hours', [
        r'(?:log|add|record|worked?|clocked?)\s+(\d+(?:\.\d+)?)\s+hours?(?:\s+(today|yesterday|\w+day))?(?:\s+(?:for|on)\s+(.+))?',
        r'(\d+(?:\.\d+)?)\s+hours?\s+(today|yesterday|\w+day)(?:\s+(?:for|on)?\s*(.+))?',
        r'(today|yesterday|\w+day)\s+(\d+(?:\.\d+)?)\s+hours?(?:\s+(?:for|on)?\s*(.+))?',
        r'(?:log|add|record)\s+hours?\s+(\d+(?:\.\d+)?)',
        r'half\s+an?\s+hour(?:\s+(today|yesterday))?',
        r'an?\s+hour(?:\s+(today|yesterday))?',
    ], 'hours_command',
        _build_hours_args  # defined below
    ),

    ('list_timesheets', [
        r'(?:show|list|pending)\s+timesheets?',
        r'timesheets?\s*$',
    ], 'timesheets_command',
        lambda m, t: []
    ),

    # ── Check-ins / Escalations ────────────────────────────────────────────────

    ('ask_supervisor', [
        r'ask\s+(?:supervisor\s+)?(?:about\s+|regarding\s+)?(.+)',
        r'question\s+for\s+supervisor[:\s]+(.+)',
        r'i\s+have\s+a\s+question[:\s]+(.+)',
    ], 'ask_command',
        lambda m, t: [m.group(1).strip()]
    ),

    ('flag_issue', [
        r'flag\s+(?:issue|problem|blocker)[:\s]+(.+)',
        r'(?:raise|report)\s+(?:a\s+)?(?:problem|issue|blocker)[:\s]+(.+)',
        r'i\s+(?:have\s+a\s+)?(?:problem|issue|blocker)[:\s]+(.+)',
    ], 'flag_command',
        lambda m, t: [m.group(1).strip()]
    ),

    ('confirm_request', [
        r'confirm\s+(?:with\s+supervisor\s+)?(?:whether\s+)?(.+)',
        r'(?:need|get)\s+(?:a\s+)?confirmation[:\s]+(.+)',
        r'(?:please\s+)?(?:approve|confirm)[:\s]+(.+)',
    ], 'confirm_command',
        lambda m, t: [m.group(1).strip()]
    ),

    ('notify_client', [
        r'notify\s+client[:\s]+(.+)',
        r'send\s+(?:a\s+)?message\s+to\s+(?:the\s+)?client[:\s]+(.+)',
        r'message\s+client[:\s]+(.+)',
        r'tell\s+(?:the\s+)?client[:\s]+(.+)',
    ], 'notify_client_command',
        lambda m, t: m.group(1).strip().split()
    ),

    ('stats', [
        r'(?:show\s+)?(?:team\s+)?stats',
        r'(?:team\s+)?dashboard',
        r'how\s+(?:is|are)\s+(?:the\s+)?team\s+doing',
    ], 'stats_command',
        lambda m, t: []
    ),

    # ── Follow-ups / Connections ───────────────────────────────────────────────

    ('new_connection', [
        r'(?:new|add|log)\s+connection[:\s]+(\w+(?:\s+\w+)?)\s+(?:on\s+)?(\w+)(?:\s+(.+))?',
        r'connection[:\s]+(\w+(?:\s+\w+)?)\s+(?:on\s+)?(\w+)',
        r'connected\s+with\s+(\w+(?:\s+\w+)?)\s+(?:on\s+)?(\w+)',
    ], 'connection_command',
        lambda m, t: [m.group(1).strip(), m.group(2).strip()]
        + (m.group(3).strip().split() if m.lastindex >= 3 and m.group(3) else [])
    ),

    ('list_followups', [
        r'(?:show|list|any\s+)?follow.?ups?',
        r'who\s+(?:do\s+i\s+)?need\s+to\s+follow\s+up',
    ], 'followups_command',
        lambda m, t: []
    ),

    ('follow_done', [
        r'follow.?up\s+done\s+(?:for\s+|with\s+)?(.+)',
        r'followed\s+up\s+(?:with\s+)?(.+)',
        r'followdone\s+(.+)',
    ], 'followdone_command',
        lambda m, t: [m.group(1).strip()]
    ),

    ('replied', [
        r'(.+)\s+(?:has\s+)?replied',
        r'(?:got\s+a\s+)?reply\s+from\s+(.+)',
        r'replied\s+(.+)',
    ], 'replied_command',
        lambda m, t: [m.group(1).strip()]
    ),

    ('booked', [
        r'(?:meeting|call)\s+booked\s+(?:with\s+)?(.+)',
        r'booked\s+(?:meeting\s+)?(?:with\s+)?(.+)',
        r'(.+)\s+(?:is\s+)?booked',
    ], 'booked_command',
        lambda m, t: [m.group(1).strip()]
    ),

    ('no_response', [
        r'no\s+response\s+from\s+(.+)',
        r'(.+)\s+(?:did\s+)?not\s+respond',
        r'noresponse\s+(.+)',
        r'close\s+follow.?up\s+(?:for\s+)?(.+)',
    ], 'noresponse_command',
        lambda m, t: [m.group(1).strip()]
    ),

    # ── Drafts ────────────────────────────────────────────────────────────────

    ('create_draft', [
        r'(?:create|write|new|submit)\s+(?:a\s+)?(?:linkedin|email|instagram|social)?\s*draft[:\s]+(.+)',
        r'draft\s+(?:for\s+)?(?:linkedin|email|instagram)[:\s]+(.+)',
        r'draft[:\s]+(.+)',
    ], 'draft_command',
        _build_draft_args   # defined below
    ),

    ('list_drafts', [
        r'(?:show|list|my)\s+drafts?',
        r'drafts?\s*$',
    ], 'drafts_command',
        lambda m, t: []
    ),

    ('mark_posted', [
        r'(?:mark|draft)?\s*(?:draft\s+)?(\w+)\s+(?:as\s+)?posted',
        r'posted\s+(\w+)',
    ], 'posted_command',
        lambda m, t: [m.group(1)]
    ),

    # ── Reports ───────────────────────────────────────────────────────────────

    ('weekly_report', [
        r'(?:generate|show|give me)?\s*weekly\s+(?:summary|report)',
        r'weekly\s*$',
    ], 'weekly_command',
        lambda m, t: []
    ),

    ('monthly_report', [
        r'(?:generate|show|give me)?\s*monthly\s+(?:summary|report|overview)',
        r'monthly\s*$',
    ], 'monthly_command',
        lambda m, t: []
    ),

    ('full_report', [
        r'(?:full|executive|complete|overall)\s+report',
        r'report\s+all',
        r'^report\s*$',
    ], 'report_all_command',
        lambda m, t: []
    ),

    # ── Scores ────────────────────────────────────────────────────────────────

    ('show_scores', [
        r'(?:show\s+)?(?:satisfaction\s+)?scores?',
        r'client\s+(?:satisfaction\s+)?ratings?',
    ], 'scores_command',
        lambda m, t: []
    ),

    ('send_scorecheck', [
        r'send\s+(?:satisfaction\s+)?(?:check|survey|scorecheck)',
        r'(?:ask|check)\s+client\s+satisfaction',
    ], 'send_scorecheck_command',
        lambda m, t: []
    ),

    # ── Info / Meta ───────────────────────────────────────────────────────────

    ('profile', [
        r'(?:show\s+)?my\s+profile',
        r'who\s+am\s+i',
        r'^profile\s*$',
    ], 'profile_command',
        lambda m, t: []
    ),

    ('help', [
        r'^help\s*$',
        r'(?:what\s+can\s+(?:you|i)\s+do|what\s+commands)',
    ], 'help_command',
        lambda m, t: []
    ),

    ('menu', [
        r'^menu\s*$',
        r'(?:open|show)\s+menu',
    ], 'menu_command',
        lambda m, t: []
    ),
]


# ── Build the registry ────────────────────────────────────────────────────────

def _build_intents() -> list[Intent]:
    h = _handlers()
    intents = []
    for name, patterns, handler_key, build_args in _INTENT_SPECS:
        fn = h.get(handler_key)
        if fn is None:
            continue
        intent = Intent(name=name, patterns=patterns, handler=fn, build_args=build_args)
        intent.compile()
        intents.append(intent)
    return intents


_INTENTS: list[Intent] | None = None


def _get_intents() -> list[Intent]:
    global _INTENTS
    if _INTENTS is None:
        _INTENTS = _build_intents()
    return _INTENTS


# ── Public API ────────────────────────────────────────────────────────────────

def route(normalized_text: str) -> RouteResult | None:
    """
    Match normalized_text against all intents.

    Returns a RouteResult on the first match, or None if nothing matched.
    The caller should assign result.args to context.args and then call
    result.handler(update, context).
    """
    for intent in _get_intents():
        m = intent.match(normalized_text)
        if m is not None:
            args = intent.build_args(m, normalized_text)
            return RouteResult(intent=intent.name, handler=intent.handler, args=args)
    return None

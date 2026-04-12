from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from typing import Iterable

from app.models import Connection, Draft, HourLog, SatisfactionScore, Task


def format_hours(value) -> str:
    return f'{Decimal(value or 0):.2f}'.rstrip('0').rstrip('.')


def render_timesheet_table(va_name: str, week_start: date, logs: Iterable[HourLog], rate: Decimal | None = None) -> str:
    day_map: dict[date, list[HourLog]] = defaultdict(list)
    for log in logs:
        day_map[log.work_date].append(log)
    lines = [
        'BeeSmartVA — Weekly Timesheet',
        '',
        f'VA: {va_name} · Week: {week_start.isoformat()} → {(week_start.fromordinal(week_start.toordinal()+6)).isoformat()}',
    ]
    if rate is not None:
        lines[-1] += f' · Rate: ${format_hours(rate)}/hr'
    lines.extend(['', 'Day           Hours   Notes', '---------------------------------------------'])
    total = Decimal('0')
    for offset in range(7):
        current_day = week_start.fromordinal(week_start.toordinal() + offset)
        entries = day_map.get(current_day, [])
        if not entries:
            continue
        total_day = sum((Decimal(str(entry.hours)) for entry in entries), Decimal('0'))
        note = ' | '.join(filter(None, [entry.note for entry in entries]))
        lines.append(f'{current_day.strftime("%A"):<12} {format_hours(total_day):>5}   {note[:80]}')
        total += total_day
    lines.append('---------------------------------------------')
    est = f' · Estimated: ${format_hours(total * rate)}' if rate is not None else ''
    lines.append(f'Total        {format_hours(total):>5}h{est}')
    return '\n'.join(lines)


def render_myweek(logs: Iterable[HourLog]) -> str:
    total = Decimal('0')
    lines = ['Your week so far', '']
    for log in sorted(logs, key=lambda x: (x.work_date, x.id)):
        total += Decimal(str(log.hours))
        lines.append(f'{log.work_date.isoformat()} · {format_hours(log.hours)}h · {log.note or "-"}')
    lines.append(f'\nTotal: {format_hours(total)}h')
    return '\n'.join(lines)


def render_task_list(tasks: Iterable[Task], user_map: dict[int, str] | None = None) -> str:
    tasks = list(tasks)
    if not tasks:
        return 'No open tasks in this group.'
    user_map = user_map or {}
    lines = ['Open tasks']
    now = datetime.utcnow()
    for task in tasks:
        age_hours = int((now - task.created_at).total_seconds() // 3600)
        assignee = user_map.get(task.assigned_to, 'unassigned') if task.assigned_to else 'unassigned'
        extra = f' · {task.flag_reason.value}' if task.flag_reason else ''
        lines.append(f'#{task.id} · {task.description} · {assignee} · {age_hours}h old · {task.status.value}{extra}')
    return '\n'.join(lines)


def render_stats(open_tasks: int, flagged_tasks: int, total_hours: Decimal, pending_timesheets: int, pending_drafts: int = 0, pending_followups: int = 0) -> str:
    return (
        'Quick stats\n\n'
        f'Open tasks: {open_tasks}\n'
        f'Flagged tasks: {flagged_tasks}\n'
        f'Hours this week: {format_hours(total_hours)}\n'
        f'Pending timesheets: {pending_timesheets}\n'
        f'Pending drafts: {pending_drafts}\n'
        f'Pending follow-ups: {pending_followups}'
    )


def render_connections(items: Iterable[Connection]) -> str:
    items = list(items)
    if not items:
        return 'No pending follow-ups.'
    lines = ['Follow-up queue']
    for item in items:
        due = item.followup_due_at.strftime('%Y-%m-%d %H:%M') if item.followup_due_at else '-'
        lines.append(f'{item.prospect_name} · {item.platform} · status={item.status.value} · due={due}')
    return '\n'.join(lines)


def render_drafts(items: Iterable[Draft]) -> str:
    items = list(items)
    if not items:
        return 'No drafts found.'
    lines = ['Drafts']
    for draft in items:
        lines.append(f'{draft.draft_code} · {draft.platform} · {draft.status.value} · submitted {draft.submitted_at:%Y-%m-%d %H:%M}')
    return '\n'.join(lines)


def render_scores(items: Iterable[SatisfactionScore]) -> str:
    items = list(items)
    if not items:
        return 'No satisfaction scores recorded yet.'
    lines = ['Satisfaction scores']
    for score in items:
        comment = f' · "{score.comment}"' if score.comment else ''
        lines.append(f'{score.period_label} · score={score.score} · trigger={score.trigger_type.value}{comment}')
    return '\n'.join(lines)

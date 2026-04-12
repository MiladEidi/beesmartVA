from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


def week_start_for(day: date) -> date:
    return day - timedelta(days=day.weekday())


def week_end_for(day: date) -> date:
    return week_start_for(day) + timedelta(days=6)


def current_week_range(timezone_name: str) -> tuple[date, date]:
    now = datetime.now(ZoneInfo(timezone_name))
    start = week_start_for(now.date())
    return start, start + timedelta(days=6)


def local_now(timezone_name: str) -> datetime:
    return datetime.now(ZoneInfo(timezone_name))


def parse_date_maybe(value: str | None, timezone_name: str = 'UTC') -> date:
    if not value:
        return local_now(timezone_name).date()
    lowered = value.lower()
    if lowered == 'today':
        return local_now(timezone_name).date()
    if lowered == 'yesterday':
        return local_now(timezone_name).date() - timedelta(days=1)
    return date.fromisoformat(value)


def parse_schedule_text(schedule_text: str) -> dict:
    text = schedule_text.strip()
    if not text:
        return {}
    if ':' in text and '-' in text and ',' not in text:
        return {'default': text}
    parts = [part.strip() for part in text.split(',') if part.strip()]
    schedule = {}
    for part in parts:
        if ':' not in part:
            continue
        key, value = part.split(':', 1)
        schedule[key.strip().lower()] = value.strip()
    return schedule or {'default': text}


def format_schedule(schedule: dict | None) -> str:
    if not schedule:
        return '-'
    return ', '.join(f'{k}: {v}' for k, v in schedule.items())


def billing_period_for(day: date) -> tuple[date, date]:
    if day.day <= 15:
        return day.replace(day=1), day.replace(day=15)
    start = day.replace(day=16)
    next_month = (day.replace(day=28) + timedelta(days=4)).replace(day=1)
    return start, next_month - timedelta(days=1)

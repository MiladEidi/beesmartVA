from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import InvoiceStatus
from app.models import InvoicePeriod, User
from app.services.audit import write_audit
from app.services.hours import approved_hours_in_period
from app.services.users import decrypt_hourly_rate
from app.utils.formatters import format_hours


async def get_or_create_invoice_period(session: AsyncSession, *, va: User, period_start: date, period_end: date) -> InvoicePeriod:
    period = await session.scalar(select(InvoicePeriod).where(InvoicePeriod.va_id == va.id, InvoicePeriod.client_id == va.client_id, InvoicePeriod.period_start == period_start, InvoicePeriod.period_end == period_end))
    if period:
        return period
    period = InvoicePeriod(va_id=va.id, client_id=va.client_id, period_start=period_start, period_end=period_end)
    session.add(period)
    await session.flush()
    return period


async def invoice_summary(session: AsyncSession, *, va: User, period_start: date, period_end: date) -> tuple[str, Decimal, Decimal, Decimal]:
    logs = await approved_hours_in_period(session, va_id=va.id, client_id=va.client_id, period_start=period_start, period_end=period_end)
    rate = decrypt_hourly_rate(va) or Decimal('0')
    total_hours = sum((Decimal(str(log.hours)) for log in logs), Decimal('0'))
    total_amount = total_hours * rate
    lines = [
        f'Invoice summary for {va.display_name}',
        f'Period: {period_start.isoformat()} → {period_end.isoformat()}',
        f'Rate: ${format_hours(rate)}/hr',
        '',
    ]
    if not logs:
        lines.append('No approved hours in this period.')
    else:
        for log in logs:
            lines.append(f'{log.work_date.isoformat()} · {format_hours(log.hours)}h · {log.note or "-"}')
    lines.append('')
    lines.append(f'Total approved hours: {format_hours(total_hours)}h')
    lines.append(f'Total amount: ${format_hours(total_amount)}')
    return '\n'.join(lines), total_hours, rate, total_amount


async def mark_invoiced(session: AsyncSession, *, va: User, period_start: date, period_end: date, actor_id: int) -> InvoicePeriod:
    period = await get_or_create_invoice_period(session, va=va, period_start=period_start, period_end=period_end)
    _, total_hours, rate, total_amount = await invoice_summary(session, va=va, period_start=period_start, period_end=period_end)
    period.total_approved_hours = total_hours
    period.rate_at_time = rate
    period.total_amount = total_amount
    period.invoiced_at = datetime.utcnow()
    period.status = InvoiceStatus.INVOICED
    await session.flush()
    await write_audit(session, client_id=va.client_id, actor_id=actor_id, action='invoice_marked_sent', entity_type='invoice_period', entity_id=period.id, details={'start': period_start.isoformat(), 'end': period_end.isoformat()})
    return period

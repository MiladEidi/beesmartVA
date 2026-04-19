from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.enums import (
    ConnectionStatus,
    DraftStatus,
    FlagReason,
    InvoiceStatus,
    ReminderType,
    Role,
    ScoreTrigger,
    TaskStatus,
    TimesheetStatus,
)


class Client(Base):
    __tablename__ = 'clients'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_chat_id: Mapped[int] = mapped_column(unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    business_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    tagline: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    primary_service: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), default='UTC')
    preferences: Mapped[dict] = mapped_column(JSON, default=dict)
    booking_links: Mapped[list] = mapped_column(JSON, default=list)
    restricted_contacts: Mapped[list] = mapped_column(JSON, default=list)
    credentials_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    users: Mapped[list['User']] = relationship(back_populates='client', lazy='selectin')


class User(Base):
    __tablename__ = 'users'
    __table_args__ = (UniqueConstraint('telegram_user_id', 'client_id', name='uq_tg_user_client'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(index=True)
    display_name: Mapped[str] = mapped_column(String(150))
    role: Mapped[Role] = mapped_column(Enum(Role), index=True)
    client_id: Mapped[int] = mapped_column(ForeignKey('clients.id'))
    supervisor_id: Mapped[Optional[int]] = mapped_column(ForeignKey('users.id'), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), default='UTC')
    working_hours: Mapped[dict] = mapped_column(JSON, default=dict)
    hourly_rate_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    va_start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    registered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    client: Mapped['Client'] = relationship(back_populates='users', lazy='joined', foreign_keys=[client_id])
    supervisor: Mapped[Optional['User']] = relationship(remote_side='User.id', lazy='joined')


class HourLog(Base):
    __tablename__ = 'hour_logs'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    va_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    client_id: Mapped[int] = mapped_column(ForeignKey('clients.id'), index=True)
    work_date: Mapped[date] = mapped_column(Date, index=True)
    hours: Mapped[float] = mapped_column(Numeric(5, 2))
    note: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    timesheet_id: Mapped[Optional[int]] = mapped_column(ForeignKey('timesheets.id'), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Timesheet(Base):
    __tablename__ = 'timesheets'
    __table_args__ = (UniqueConstraint('va_id', 'client_id', 'week_start_date', name='uq_timesheet_week'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    va_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    client_id: Mapped[int] = mapped_column(ForeignKey('clients.id'), index=True)
    week_start_date: Mapped[date] = mapped_column(Date, index=True)
    total_hours: Mapped[float] = mapped_column(Numeric(6, 2), default=0)
    status: Mapped[TimesheetStatus] = mapped_column(Enum(TimesheetStatus), default=TimesheetStatus.DRAFT, index=True)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    sup_approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    sup_approved_by: Mapped[Optional[int]] = mapped_column(ForeignKey('users.id'), nullable=True)
    client_approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    client_approved_by: Mapped[Optional[int]] = mapped_column(ForeignKey('users.id'), nullable=True)
    query_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    invoiced: Mapped[bool] = mapped_column(Boolean, default=False)


class InvoicePeriod(Base):
    __tablename__ = 'invoice_periods'
    __table_args__ = (UniqueConstraint('va_id', 'client_id', 'period_start', 'period_end', name='uq_invoice_period'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    va_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    client_id: Mapped[int] = mapped_column(ForeignKey('clients.id'), index=True)
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    total_approved_hours: Mapped[float] = mapped_column(Numeric(8, 2), default=0)
    rate_at_time: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    total_amount: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    reminder_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    invoiced_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[InvoiceStatus] = mapped_column(Enum(InvoiceStatus), default=InvoiceStatus.PENDING)


class Task(Base):
    __tablename__ = 'tasks'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey('clients.id'), index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    assigned_to: Mapped[Optional[int]] = mapped_column(ForeignKey('users.id'), nullable=True, index=True)
    description: Mapped[str] = mapped_column(String(500))
    status: Mapped[TaskStatus] = mapped_column(Enum(TaskStatus), default=TaskStatus.OPEN, index=True)
    flag_reason: Mapped[Optional[FlagReason]] = mapped_column(Enum(FlagReason), nullable=True)
    flag_note: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class Connection(Base):
    __tablename__ = 'connections'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey('clients.id'), index=True)
    va_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    prospect_name: Mapped[str] = mapped_column(String(200), index=True)
    platform: Mapped[str] = mapped_column(String(80))
    title: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    company: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    status: Mapped[ConnectionStatus] = mapped_column(Enum(ConnectionStatus), default=ConnectionStatus.CONNECTED, index=True)
    connected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    followup_due_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    last_followup_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    followup_count: Mapped[int] = mapped_column(Integer, default=0)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class Draft(Base):
    __tablename__ = 'drafts'
    __table_args__ = (UniqueConstraint('draft_code', name='uq_draft_code'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    draft_code: Mapped[str] = mapped_column(String(30), index=True)
    client_id: Mapped[int] = mapped_column(ForeignKey('clients.id'), index=True)
    va_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    platform: Mapped[str] = mapped_column(String(80))
    content_text: Mapped[str] = mapped_column(Text)
    status: Mapped[DraftStatus] = mapped_column(Enum(DraftStatus), default=DraftStatus.PENDING, index=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    actioned_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    actioned_by: Mapped[Optional[int]] = mapped_column(ForeignKey('users.id'), nullable=True)
    revision_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    parent_draft_id: Mapped[Optional[int]] = mapped_column(ForeignKey('drafts.id'), nullable=True)


class SatisfactionScore(Base):
    __tablename__ = 'satisfaction_scores'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey('clients.id'), index=True)
    va_id: Mapped[Optional[int]] = mapped_column(ForeignKey('users.id'), nullable=True, index=True)
    score: Mapped[int] = mapped_column(Integer)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    trigger_type: Mapped[ScoreTrigger] = mapped_column(Enum(ScoreTrigger), default=ScoreTrigger.MONTHLY)
    requested_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    responded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    period_label: Mapped[str] = mapped_column(String(50))


class Reminder(Base):
    __tablename__ = 'reminders'
    __table_args__ = (UniqueConstraint('client_id', 'type', 'dedupe_key', name='uq_reminder_dedupe'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey('clients.id'), index=True)
    type: Mapped[ReminderType] = mapped_column(Enum(ReminderType), index=True)
    target_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    send_at: Mapped[datetime] = mapped_column(DateTime)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    dedupe_key: Mapped[str] = mapped_column(String(100), index=True)


class AuditLog(Base):
    __tablename__ = 'audit_log'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey('clients.id'), index=True)
    actor_id: Mapped[Optional[int]] = mapped_column(ForeignKey('users.id'), nullable=True)
    action: Mapped[str] = mapped_column(String(120), index=True)
    entity_type: Mapped[str] = mapped_column(String(80), index=True)
    entity_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    details_json: Mapped[dict] = mapped_column(JSON, default=dict)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class GlobalConfig(Base):
    """Single-row table (id=1) that holds global settings across all workspaces."""

    __tablename__ = 'global_config'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_manager_telegram_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, unique=True)

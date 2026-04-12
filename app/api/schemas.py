from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str


class ClientSummary(BaseModel):
    id: int
    telegram_chat_id: int
    name: str
    business_name: str | None
    timezone: str


class ReportResponse(BaseModel):
    report: str


class UserCreate(BaseModel):
    telegram_user_id: int
    display_name: str
    role: str
    timezone: str = 'UTC'


class ClientCreate(BaseModel):
    telegram_chat_id: int
    name: str
    business_name: str | None = None
    tagline: str | None = None
    primary_service: str | None = None
    description: str | None = None
    timezone: str = 'UTC'

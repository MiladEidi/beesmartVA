from datetime import date

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import ClientCreate, ClientSummary, HealthResponse, ReportResponse, UserCreate
from app.db import get_session, init_db
from app.enums import Role
from app.models import Client, User
from app.services.reports import monthly_report, weekly_report
from app.services.users import add_or_update_user, ensure_client
from app.utils.dates import week_start_for

app = FastAPI(title='BeeSmartVA Bot API', version='1.0.0')


@app.on_event('startup')
async def startup() -> None:
    await init_db()


@app.get('/health', response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status='ok')


@app.get('/clients', response_model=list[ClientSummary])
async def list_clients(session: AsyncSession = Depends(get_session)) -> list[ClientSummary]:
    clients = list((await session.scalars(select(Client).order_by(Client.id.asc()))).all())
    return [ClientSummary(id=c.id, telegram_chat_id=c.telegram_chat_id, name=c.name, business_name=c.business_name, timezone=c.timezone) for c in clients]


@app.post('/clients', response_model=ClientSummary)
async def create_client(payload: ClientCreate, session: AsyncSession = Depends(get_session)) -> ClientSummary:
    client = await ensure_client(session, chat_id=payload.telegram_chat_id, name=payload.name, business_name=payload.business_name, tagline=payload.tagline, primary_service=payload.primary_service, description=payload.description, timezone=payload.timezone)
    await session.commit()
    return ClientSummary(id=client.id, telegram_chat_id=client.telegram_chat_id, name=client.name, business_name=client.business_name, timezone=client.timezone)


@app.post('/clients/{client_id}/users')
async def create_user(client_id: int, payload: UserCreate, session: AsyncSession = Depends(get_session)) -> dict:
    client = await session.scalar(select(Client).where(Client.id == client_id))
    if not client:
        raise HTTPException(status_code=404, detail='Client not found')
    await add_or_update_user(session, client_id=client_id, telegram_user_id=payload.telegram_user_id, display_name=payload.display_name, role=Role(payload.role), timezone=payload.timezone)
    await session.commit()
    return {'status': 'created'}


@app.get('/clients/{client_id}/users')
async def client_users(client_id: int, session: AsyncSession = Depends(get_session)) -> list[dict]:
    rows = list((await session.scalars(select(User).where(User.client_id == client_id).order_by(User.id.asc()))).all())
    return [{'id': u.id, 'telegram_user_id': u.telegram_user_id, 'display_name': u.display_name, 'role': u.role.value, 'timezone': u.timezone} for u in rows]


@app.get('/clients/{client_id}/reports/weekly', response_model=ReportResponse)
async def get_weekly_report(client_id: int, session: AsyncSession = Depends(get_session)) -> ReportResponse:
    client = await session.scalar(select(Client).where(Client.id == client_id))
    if not client:
        raise HTTPException(status_code=404, detail='Client not found')
    report = await weekly_report(session, client_id=client.id, client_name=client.name, week_start=week_start_for(date.today()))
    return ReportResponse(report=report)


@app.get('/clients/{client_id}/reports/monthly', response_model=ReportResponse)
async def get_monthly_report(client_id: int, session: AsyncSession = Depends(get_session)) -> ReportResponse:
    client = await session.scalar(select(Client).where(Client.id == client_id))
    if not client:
        raise HTTPException(status_code=404, detail='Client not found')
    report = await monthly_report(session, client_id=client.id, client_name=client.name, month_label=date.today().strftime('%B %Y'))
    return ReportResponse(report=report)

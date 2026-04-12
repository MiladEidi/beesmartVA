from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    app_name: str = 'BeeSmartVA Team Bot'
    bot_token: str = Field(alias='BOT_TOKEN')
    database_url: str = Field(default='sqlite+aiosqlite:///./beesmartva.db', alias='DATABASE_URL')
    api_host: str = Field(default='0.0.0.0', alias='API_HOST')
    api_port: int = Field(default=8000, alias='API_PORT')
    tz_default: str = Field(default='UTC', alias='TZ_DEFAULT')
    encryption_key: str = Field(alias='ENCRYPTION_KEY')
    supervisor_dm_only: bool = Field(default=True, alias='SUPERVISOR_DM_ONLY')
    app_base_url: str = Field(default='http://localhost:8000', alias='APP_BASE_URL')


@lru_cache
def get_settings() -> Settings:
    return Settings()

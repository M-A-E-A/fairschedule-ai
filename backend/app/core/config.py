from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = 'development'
    database_url: str = 'sqlite:///./demo.db'
    jwt_secret: str = 'dev-secret'
    backend_cors_origins: str = 'http://localhost:5173'
    ai_provider: str = 'none'
    ai_api_key: str = ''
    google_client_id: str = ''
    google_client_secret: str = ''
    use_sqlite_for_tests: bool = True

    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')


@lru_cache
def get_settings() -> Settings:
    return Settings()

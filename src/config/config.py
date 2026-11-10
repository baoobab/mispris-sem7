from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Синхронный драйвер psycopg2 используется и приложением, и Alembic
    DATABASE_URL: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/mispis_sem7"
    APP_TITLE: str = "МиСПрИС: справочник изделий, ХО, спецификации и маршрутная технология"
    APP_VERSION: str = "3.0.0"
    SQL_ECHO: bool = False

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()

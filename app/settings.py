from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite:///./audit_hq.sqlite"
    auth_user: str = "admin"
    auth_password: str = "admin"
    session_secret: str = "dev-secret-change-me"
    raw_data_path: Path = Path("./data")


settings = Settings()

# app/settings.py
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    DB_URL: str  # mysql+pymysql://user:pass@host:3306/library
    LM_BASE: str = "http://127.0.0.1:1234"
    CORS_ORIGIN: str = "*"        # or "http://localhost:3000"
    WHISPER_SIZE: str = "small"
    WH_DEVICE: str = "cpu"        # set to "cuda" on GPU hosts

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

settings = Settings()

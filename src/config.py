from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    EPA_API_BASE_URL: str = "https://data.epa.gov/efservice/PUB_DIM_FACILITY"
    DATABASE_URL: str = "sqlite+aiosqlite:///data/carbon.db"
    DB_PATH: str = "data/carbon.db"
    LOG_LEVEL: str = "INFO"
    REQUEST_TIMEOUT_SECONDS: float = 20.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def sqlite_path(self) -> Path:
        return Path(self.DB_PATH)


settings = Settings()

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    PROJECT_NAME: str = "Restaurant Booking API"
    VERSION: str = "1.0.0"
    API_V1_PREFIX: str = ""

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./bookings.db"
    ECHO_SQL: bool = False

    # Business Rules
    MAX_TABLES_PER_SLOT: int = 10
    BOOKING_MAX_DAYS_AHEAD: int = 90
    BOOKING_OPEN_HOUR: int = 12
    BOOKING_CLOSE_HOUR: int = 22
    TIMEZONE: str = "Europe/Moscow"

    # Pagination Defaults
    DEFAULT_LIMIT: int = 20
    MAX_LIMIT: int = 100


settings = Settings()

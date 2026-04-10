from typing import List
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # API Configuration
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Anthrilo Management System"

    # Environment
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # Supabase Configuration
    SUPABASE_URL: str
    SUPABASE_KEY: str
    SUPABASE_SERVICE_KEY: str = ""

    # Database (Supabase PostgreSQL)
    DATABASE_URL: str

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Security
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000", "http://localhost:3001", "http://localhost:3002"]

    # Pagination
    DEFAULT_PAGE_SIZE: int = 15
    MAX_PAGE_SIZE: int = 100

    # Unicommerce API Configuration
    UNICOMMERCE_TENANT: str = ""
    UNICOMMERCE_ACCESS_CODE: str = ""
    UNICOMMERCE_USERNAME: str = ""
    UNICOMMERCE_PASSWORD: str = ""
    UNICOMMERCE_ACCESS_TOKEN: str = ""
    UNICOMMERCE_REFRESH_TOKEN: str = ""
    UNICOMMERCE_BASE_URL: str = "https://{tenant}.unicommerce.com/services/rest/v1"

    # Unicommerce DB-first sync orchestration
    UNICOMMERCE_SYNC_ENABLE_SCHEDULER: bool = False
    UNICOMMERCE_SYNC_INCREMENTAL_MINUTES: int = 30
    UNICOMMERCE_SYNC_LOOKBACK_DAYS: int = 2
    UNICOMMERCE_SYNC_BACKFILL_CHUNK_DAYS: int = 7
    UNICOMMERCE_SYNC_LOCK_TTL_SECONDS: int = 1200
    UNICOMMERCE_SYNC_DISCOVERY_SKU_LIMIT: int = 5000
    UNICOMMERCE_SYNC_MAX_LAG_MINUTES: int = 120

    # Unicommerce export polling/download resilience
    UNICOMMERCE_EXPORT_MAX_NO_FILEPATH_RETRIES: int = 12
    UNICOMMERCE_EXPORT_STATUS_RETRY_GRACE_SECONDS: int = 180
    UNICOMMERCE_EXPORT_MAX_CONSECUTIVE_POLL_ERRORS: int = 12
    UNICOMMERCE_EXPORT_DOWNLOAD_MAX_RETRIES: int = 4
    UNICOMMERCE_EXPORT_DOWNLOAD_BACKOFF_SECONDS: int = 3

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()

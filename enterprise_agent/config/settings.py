from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Enterprise Agent Configuration Settings"""

    # App
    APP_NAME: str = "Enterprise Agent"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False

    # API
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    # Database - MySQL
    MYSQL_HOST: str = "localhost"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "agent_user"
    MYSQL_PASSWORD: str = ""
    MYSQL_DATABASE: str = "enterprise_agent"

    # Database - Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: Optional[str] = None

    # Auth
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # LLM
    ANTHROPIC_API_KEY: str = ""
    MODEL_ID: str = "claude-sonnet-4-6"

    # Memory
    SHORT_TERM_TTL_HOURS: int = 24
    MAX_MESSAGES_PER_SESSION: int = 100
    TOKEN_THRESHOLD: int = 100000

    model_config = {"env_file": ".env", "case_sensitive": True}


settings = Settings()
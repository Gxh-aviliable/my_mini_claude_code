from pydantic_settings import BaseSettings
from typing import Optional, Literal


class Settings(BaseSettings):
    """Enterprise Agent Configuration Settings"""

    # App
    APP_NAME: str = "Enterprise Agent"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False

    # API
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    # Database - MySQL (for auth/session only)
    MYSQL_HOST: str = "localhost"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "agent_user"
    MYSQL_PASSWORD: str = ""
    MYSQL_DATABASE: str = "enterprise_agent"

    # Database - Redis (short-term memory)
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: Optional[str] = None

    # Database - Chroma (long-term vector memory)
    CHROMA_PERSIST_DIR: str = "./chroma_data"
    CHROMA_COLLECTION_CONVERSATIONS: str = "conversations"
    CHROMA_COLLECTION_PATTERNS: str = "user_patterns"

    # Auth
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # LLM Provider Configuration
    # Supported: "anthropic" | "glm" | "deepseek" | "openai"
    LLM_PROVIDER: str = "anthropic"
    LLM_API_KEY: str = ""  # Universal API key
    LLM_BASE_URL: Optional[str] = None  # Custom base URL for OpenAI-compatible APIs
    MODEL_ID: str = "claude-sonnet-4-6"  # Model identifier

    # Legacy Anthropic config (for backward compatibility)
    ANTHROPIC_API_KEY: str = ""

    # Memory
    SHORT_TERM_TTL_HOURS: int = 24
    MAX_MESSAGES_PER_SESSION: int = 100
    TOKEN_THRESHOLD: int = 100000

    # Embedding (for Chroma)
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"  # Local sentence-transformers model

    model_config = {"env_file": ".env", "case_sensitive": True}

    def get_effective_api_key(self) -> str:
        """Get effective API key based on provider or legacy config."""
        if self.LLM_API_KEY:
            return self.LLM_API_KEY
        # Fallback to legacy Anthropic key
        if self.LLM_PROVIDER == "anthropic" and self.ANTHROPIC_API_KEY:
            return self.ANTHROPIC_API_KEY
        return ""

    def get_effective_base_url(self) -> Optional[str]:
        """Get effective base URL based on provider."""
        if self.LLM_BASE_URL:
            return self.LLM_BASE_URL

        # Default URLs for each provider
        defaults = {
            "glm": "https://open.bigmodel.cn/api/paas/v4",
            "deepseek": "https://api.deepseek.com",
            "openai": "https://api.openai.com/v1",
            "mimo": "https://api.xiaomimimo.com/anthropic",
        }
        return defaults.get(self.LLM_PROVIDER)

    def get_effective_model_id(self) -> str:
        """Get effective model ID based on provider."""
        if self.MODEL_ID:
            return self.MODEL_ID

        # Default models for each provider
        defaults = {
            "anthropic": "claude-sonnet-4-6",
            "glm": "glm-4",
            "deepseek": "deepseek-chat",
            "openai": "gpt-4",
        }
        return defaults.get(self.LLM_PROVIDER, "claude-sonnet-4-6")


settings = Settings()
from pathlib import Path
from typing import Optional

from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Enterprise Agent Configuration Settings"""

    # App
    APP_NAME: str = "Enterprise Agent"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False

    # API
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000"

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
    CHROMA_PERSIST_DIR: str = str(Path(__file__).resolve().parent.parent.parent / "chroma_data")
    CHROMA_COLLECTION_CONVERSATIONS: str = "conversations"
    CHROMA_COLLECTION_PATTERNS: str = "user_patterns"

    # Auth
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # LLM Provider Configuration
    # Supported: "anthropic" | "glm" | "deepseek" | "openai" | "mimo"
    # DeepSeek supports both OpenAI-compatible (/v1) and Anthropic-compatible (/anthropic) endpoints
    LLM_PROVIDER: str = "deepseek"
    LLM_API_KEY: str = ""  # Universal API key
    LLM_BASE_URL: Optional[str] = "https://api.deepseek.com/anthropic"  # Anthropic-compatible endpoint
    MODEL_ID: str = "deepseek-v4-pro"  # Model identifier

    # Legacy Anthropic config (for backward compatibility)
    ANTHROPIC_API_KEY: str = ""

    # Memory
    SHORT_TERM_TTL_HOURS: int = 24
    MAX_MESSAGES_PER_SESSION: int = 100
    TOKEN_THRESHOLD: int = 500000

    # Tool output limits
    TOOL_OUTPUT_MAX_CHARS: int = 50000  # Truncation limit for tool outputs
    # Auto-compact: how much recent text (chars) the summarizer LLM sees.
    # With TOKEN_THRESHOLD=500K (~2M chars), 200K chars (~50K tokens) gives the
    # summarizer enough context to produce a useful summary (~10% of full context).
    CONTEXT_SUMMARY_TRIGGER_CHARS: int = 200000

    # Agent behavior
    MICROCOMPACT_KEEP_LAST: int = 3  # Messages to keep during microcompact
    NAG_REMINDER_THRESHOLD: int = 3  # Rounds without TodoWrite before reminder
    COMMAND_TIMEOUT_SECONDS: int = 120  # Shell/background command timeout
    AGENT_INVOKE_TIMEOUT_SECONDS: int = 600  # Max seconds for a single graph invocation
    MAX_AGENT_ROUNDS: int = 50  # Max LLM→tool rounds before forced stop
    SUBAGENT_MAX_ROUNDS: int = 30  # Max rounds for subagent execution
    TODO_MAX_ITEMS: int = 20  # Max todo items per session
    TODO_MAX_IN_PROGRESS: int = 1  # Max concurrent in_progress todos

    # LangSmith tracing (optional — if API key is set, tracing auto-enables)
    LANGSMITH_API_KEY: str = ""
    LANGSMITH_PROJECT: str = "enterprise-agent"

    # Embedding (for Chroma)
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"  # Local sentence-transformers model

    model_config = {"env_file": ".env", "case_sensitive": True, "extra": "ignore"}

    @model_validator(mode="after")
    def validate_security(self):
        """Validate security-sensitive settings at startup."""
        if self.JWT_SECRET_KEY == "change-me-in-production":
            raise ValueError(
                "JWT_SECRET_KEY must be set in .env (not the default value). "
                "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
            )
        return self

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
        return self.MODEL_ID


settings = Settings()

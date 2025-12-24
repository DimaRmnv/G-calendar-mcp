"""
Application settings with environment variable support.

All settings can be overridden via GCAL_MCP_* environment variables.
Supports both local (stdio) and cloud (http) modes.
"""

import os
from pathlib import Path
from typing import Literal, Optional

try:
    from pydantic import Field
    from pydantic_settings import BaseSettings
    PYDANTIC_AVAILABLE = True
except ImportError:
    PYDANTIC_AVAILABLE = False
    BaseSettings = object
    Field = lambda **kwargs: kwargs.get("default_factory", lambda: None)()


class Settings(BaseSettings if PYDANTIC_AVAILABLE else object):
    """Google Calendar MCP configuration."""

    # Transport mode
    transport_mode: Literal["stdio", "http"] = "stdio"
    http_host: str = "0.0.0.0"
    http_port: int = 8000

    # API key for HTTP transport (required in http mode)
    api_key: Optional[str] = None

    # OAuth 2.0 Client Credentials for external clients (e.g., Claude.ai)
    oauth_client_id: Optional[str] = None
    oauth_client_secret: Optional[str] = None

    # SSL/TLS settings
    ssl_certfile: Optional[Path] = None
    ssl_keyfile: Optional[Path] = None

    # OAuth settings for web callback flow
    oauth_redirect_uri: Optional[str] = None  # e.g., https://mcp-serv.duckdns.org/mcp/calendar/oauth/callback
    server_base_url: Optional[str] = None  # e.g., https://mcp-serv.duckdns.org/mcp/calendar

    # Directory paths
    data_dir: Path = Field(
        default_factory=lambda: Path.home() / ".mcp" / "google-calendar"
    ) if PYDANTIC_AVAILABLE else Path.home() / ".mcp" / "google-calendar"

    credentials_dir: Path = Field(
        default_factory=lambda: Path.home() / ".mcp" / "google-calendar" / "credentials"
    ) if PYDANTIC_AVAILABLE else Path.home() / ".mcp" / "google-calendar" / "credentials"

    # PostgreSQL settings (for cloud mode)
    postgres_host: Optional[str] = None
    postgres_port: int = 5432
    postgres_user: Optional[str] = None
    postgres_password: Optional[str] = None
    postgres_db: str = "google_calendar_mcp"
    database_url: Optional[str] = None  # Override individual settings

    if PYDANTIC_AVAILABLE:
        model_config = {
            "env_prefix": "GCAL_MCP_",
            "env_file": ".env",
            "extra": "ignore",
        }

    def __init__(self, **kwargs):
        if PYDANTIC_AVAILABLE:
            super().__init__(**kwargs)
        else:
            # Fallback for when pydantic-settings not installed
            self._load_from_env()

    def _load_from_env(self):
        """Load settings from environment (fallback without pydantic)."""
        self.transport_mode = os.getenv("GCAL_MCP_TRANSPORT_MODE", "stdio")
        self.http_host = os.getenv("GCAL_MCP_HTTP_HOST", "0.0.0.0")
        self.http_port = int(os.getenv("GCAL_MCP_HTTP_PORT", "8000"))
        self.api_key = os.getenv("GCAL_MCP_API_KEY")
        self.oauth_client_id = os.getenv("GCAL_MCP_OAUTH_CLIENT_ID")
        self.oauth_client_secret = os.getenv("GCAL_MCP_OAUTH_CLIENT_SECRET")
        self.oauth_redirect_uri = os.getenv("GCAL_MCP_OAUTH_REDIRECT_URI")
        self.server_base_url = os.getenv("GCAL_MCP_SERVER_BASE_URL")

        ssl_cert = os.getenv("GCAL_MCP_SSL_CERTFILE")
        self.ssl_certfile = Path(ssl_cert) if ssl_cert else None
        ssl_key = os.getenv("GCAL_MCP_SSL_KEYFILE")
        self.ssl_keyfile = Path(ssl_key) if ssl_key else None

        data = os.getenv("GCAL_MCP_DATA_DIR")
        self.data_dir = Path(data) if data else Path.home() / ".mcp" / "google-calendar"
        creds = os.getenv("GCAL_MCP_CREDENTIALS_DIR")
        self.credentials_dir = Path(creds) if creds else self.data_dir / "credentials"

        # PostgreSQL
        self.postgres_host = os.getenv("POSTGRES_HOST")
        self.postgres_port = int(os.getenv("POSTGRES_PORT", "5432"))
        self.postgres_user = os.getenv("POSTGRES_USER")
        self.postgres_password = os.getenv("POSTGRES_PASSWORD")
        self.postgres_db = os.getenv("POSTGRES_DB", "google_calendar_mcp")
        self.database_url = os.getenv("DATABASE_URL")

    def ensure_dirs(self) -> None:
        """Create directories if they don't exist."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.credentials_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "tokens").mkdir(parents=True, exist_ok=True)

    def get_credentials_account_dir(self, account: str) -> Path:
        """Get directory for account credentials."""
        account_dir = self.credentials_dir / account
        account_dir.mkdir(parents=True, exist_ok=True)
        return account_dir

    def get_token_path(self, account: str) -> Path:
        """Get token file path for account."""
        return self.get_credentials_account_dir(account) / "token.json"

    def get_oauth_client_path(self) -> Path:
        """Get OAuth client credentials path."""
        return self.data_dir / "oauth_client.json"

    def get_config_path(self) -> Path:
        """Get config file path."""
        return self.data_dir / "config.json"

    def get_cache_dir(self) -> Path:
        """Get cache directory."""
        cache_dir = self.data_dir / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir

    def get_auth_start_url(self, account: str) -> Optional[str]:
        """Get URL to start OAuth flow for account."""
        if self.server_base_url:
            return f"{self.server_base_url}/oauth/start/{account}"
        return None

    def get_db_url(self) -> Optional[str]:
        """Get PostgreSQL connection URL."""
        if self.database_url:
            return self.database_url

        if self.postgres_host and self.postgres_user:
            password = f":{self.postgres_password}" if self.postgres_password else ""
            return f"postgresql://{self.postgres_user}{password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

        return None

    def is_cloud_mode(self) -> bool:
        """Check if running in cloud mode (HTTP + PostgreSQL)."""
        return self.transport_mode == "http" and self.get_db_url() is not None


# Global settings instance
settings = Settings()

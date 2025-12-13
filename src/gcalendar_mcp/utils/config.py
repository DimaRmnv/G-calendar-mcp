"""
Configuration management for GCalendar MCP.

Handles:
- Config directory paths (~/.mcp/gcalendar/)
- Config file read/write
- Account management
- Time tracking feature toggle
"""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import Optional


APP_NAME = "gcalendar"


def get_mcp_root() -> Path:
    """Get MCP root directory: ~/.mcp"""
    root = Path.home() / ".mcp"
    root.mkdir(exist_ok=True)
    return root


def get_app_dir() -> Path:
    """Get app directory: ~/.mcp/gcalendar"""
    app_dir = get_mcp_root() / APP_NAME
    app_dir.mkdir(exist_ok=True)
    return app_dir


def get_tokens_dir() -> Path:
    """Get tokens directory: ~/.mcp/gcalendar/tokens"""
    tokens_dir = get_app_dir() / "tokens"
    tokens_dir.mkdir(exist_ok=True)
    return tokens_dir


def get_cache_dir() -> Path:
    """Get cache directory: ~/.mcp/gcalendar/cache"""
    cache_dir = get_app_dir() / "cache"
    cache_dir.mkdir(exist_ok=True)
    return cache_dir


def get_config_path() -> Path:
    """Get config file path: ~/.mcp/gcalendar/config.json"""
    return get_app_dir() / "config.json"


def get_oauth_client_path() -> Path:
    """Get OAuth client credentials path: ~/.mcp/gcalendar/oauth_client.json"""
    return get_app_dir() / "oauth_client.json"


def get_token_path(account: str) -> Path:
    """Get token file path for account: ~/.mcp/gcalendar/tokens/{account}.json"""
    return get_tokens_dir() / f"{account}.json"


def load_config() -> dict:
    """Load config from file. Returns default config if not exists."""
    config_path = get_config_path()
    
    default_config = {
        "default_account": None,
        "accounts": {},
        "time_tracking": {
            "enabled": False
        }
    }
    
    if not config_path.exists():
        return default_config
    
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
        # Ensure time_tracking section exists
        if "time_tracking" not in config:
            config["time_tracking"] = {"enabled": False}
        return config
    except (json.JSONDecodeError, IOError):
        return default_config


def save_config(config: dict) -> None:
    """Save config to file with secure permissions."""
    config_path = get_config_path()
    config_path.write_text(
        json.dumps(config, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    os.chmod(config_path, 0o600)


def add_account(name: str, email: str, timezone: Optional[str] = None) -> None:
    """Add account to config."""
    config = load_config()
    
    config["accounts"][name] = {
        "email": email,
        "timezone": timezone,
        "added": datetime.now().isoformat()
    }
    
    # Set as default if first account
    if config["default_account"] is None:
        config["default_account"] = name
    
    save_config(config)


def remove_account(name: str) -> bool:
    """Remove account from config. Returns True if removed."""
    config = load_config()
    
    if name not in config["accounts"]:
        return False
    
    del config["accounts"][name]
    
    # Remove token file
    token_path = get_token_path(name)
    if token_path.exists():
        token_path.unlink()
    
    # Update default if removed
    if config["default_account"] == name:
        config["default_account"] = next(iter(config["accounts"]), None)
    
    save_config(config)
    return True


def get_account(name: Optional[str] = None) -> Optional[dict]:
    """Get account info. Uses default if name is None."""
    config = load_config()
    
    if name is None:
        name = config["default_account"]
    
    if name is None or name not in config["accounts"]:
        return None
    
    return {
        "name": name,
        **config["accounts"][name]
    }


def get_default_account() -> Optional[str]:
    """Get default account name."""
    config = load_config()
    return config["default_account"]


def set_default_account(name: str) -> bool:
    """Set default account. Returns True if successful."""
    config = load_config()
    
    if name not in config["accounts"]:
        return False
    
    config["default_account"] = name
    save_config(config)
    return True


def list_accounts() -> dict[str, dict]:
    """List all accounts."""
    config = load_config()
    return config["accounts"]


def get_account_names() -> list[str]:
    """Get list of account names."""
    config = load_config()
    return list(config["accounts"].keys())


def is_default(name: str) -> bool:
    """Check if account is default."""
    config = load_config()
    return config["default_account"] == name


def has_oauth_client() -> bool:
    """Check if OAuth client credentials exist."""
    return get_oauth_client_path().exists()


def save_oauth_client(credentials: dict) -> None:
    """Save OAuth client credentials with secure permissions."""
    oauth_path = get_oauth_client_path()
    oauth_path.write_text(
        json.dumps(credentials, indent=2),
        encoding="utf-8"
    )
    os.chmod(oauth_path, 0o600)


def load_oauth_client() -> Optional[dict]:
    """Load OAuth client credentials."""
    oauth_path = get_oauth_client_path()
    
    if not oauth_path.exists():
        return None
    
    try:
        return json.loads(oauth_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, IOError):
        return None


# =============================================================================
# Time Tracking Configuration
# =============================================================================

def is_time_tracking_enabled() -> bool:
    """Check if time tracking feature is enabled."""
    config = load_config()
    return config.get("time_tracking", {}).get("enabled", False)


def enable_time_tracking() -> None:
    """Enable time tracking feature."""
    config = load_config()
    if "time_tracking" not in config:
        config["time_tracking"] = {}
    config["time_tracking"]["enabled"] = True
    save_config(config)


def disable_time_tracking() -> None:
    """Disable time tracking feature."""
    config = load_config()
    if "time_tracking" not in config:
        config["time_tracking"] = {}
    config["time_tracking"]["enabled"] = False
    save_config(config)

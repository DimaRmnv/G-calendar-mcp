"""
Authentication CLI commands.

Handles:
- Interactive account setup (auth)
- Account removal (auth --remove)
- Set default account (auth --default)
- OAuth client credentials input
- Duplicate detection (name, email, token)
"""

import json
import sys
from typing import Optional

from gcalendar_mcp.utils.config import (
    add_account,
    remove_account,
    get_account_names,
    get_account,
    has_oauth_client,
    save_oauth_client,
    load_oauth_client,
    is_default,
    set_default_account,
    list_accounts,
    get_token_path,
)
from gcalendar_mcp.api.client import (
    run_oauth_flow,
    get_authorized_email,
    verify_credentials,
    get_credentials,
)


def print_header(text: str) -> None:
    """Print formatted header."""
    print(f"\n{'=' * 50}")
    print(f"  {text}")
    print(f"{'=' * 50}\n")


def print_success(text: str) -> None:
    """Print success message."""
    print(f"✓ {text}")


def print_error(text: str) -> None:
    """Print error message."""
    print(f"✗ {text}", file=sys.stderr)


def print_warning(text: str) -> None:
    """Print warning message."""
    print(f"⚠ {text}")


def print_info(text: str) -> None:
    """Print info message."""
    print(f"ℹ {text}")


def prompt(text: str, default: Optional[str] = None) -> str:
    """Prompt user for input."""
    if default:
        result = input(f"{text} [{default}]: ").strip()
        return result if result else default
    return input(f"{text}: ").strip()


def confirm(text: str, default: bool = False) -> bool:
    """Prompt for yes/no confirmation."""
    suffix = "[Y/n]" if default else "[y/N]"
    result = input(f"{text} {suffix}: ").strip().lower()
    
    if not result:
        return default
    return result in ("y", "yes")


def get_email_by_account_name(name: str) -> Optional[str]:
    """Get email for existing account."""
    accounts = list_accounts()
    if name in accounts:
        return accounts[name].get("email")
    return None


def find_account_by_email(email: str) -> Optional[str]:
    """Find account name by email. Returns None if not found."""
    accounts = list_accounts()
    email_lower = email.lower()
    
    for name, info in accounts.items():
        if info.get("email", "").lower() == email_lower:
            return name
    return None


def check_token_exists(account: str) -> bool:
    """Check if token file exists for account."""
    return get_token_path(account).exists()


def check_token_valid(account: str) -> bool:
    """Check if token is valid (not expired, can refresh)."""
    creds = get_credentials(account)
    return creds is not None


def collect_oauth_client() -> dict:
    """
    Collect OAuth client JSON from user input.
    
    User pastes JSON from Google Cloud Console.
    """
    print("Paste OAuth client JSON from Google Cloud Console.")
    print("(Get it from: APIs & Services → Credentials → OAuth 2.0 Client IDs)")
    print("Press Enter twice when done:\n")
    
    lines = []
    empty_count = 0
    
    while True:
        try:
            line = input()
        except EOFError:
            break
            
        if line == "":
            empty_count += 1
            if empty_count >= 1:
                break
        else:
            empty_count = 0
            lines.append(line)
    
    json_text = "".join(lines)
    
    if not json_text.strip():
        raise ValueError("No JSON provided")
    
    try:
        credentials = json.loads(json_text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e}")
    
    # Validate structure
    if "installed" not in credentials and "web" not in credentials:
        raise ValueError(
            "Invalid OAuth client JSON. "
            "Expected 'installed' or 'web' application credentials."
        )
    
    return credentials


def get_oauth_project_id() -> Optional[str]:
    """Get project_id from current OAuth client."""
    client = load_oauth_client()
    if not client:
        return None
    config = client.get("installed") or client.get("web") or {}
    return config.get("project_id")


def auth_add_account() -> Optional[str]:
    """
    Interactive flow to add a new account.
    
    Returns account name on success, None on failure.
    """
    existing_names = get_account_names()
    
    # Get account name
    while True:
        name = prompt("Account name (e.g., work, personal)")
        
        if not name:
            print_error("Account name is required")
            continue
        
        # Validate name format
        if not all(c.isalnum() or c in "-_" for c in name):
            print_error("Account name can only contain letters, numbers, dash, underscore")
            continue
        
        # Check duplicate name
        if name in existing_names:
            existing_email = get_email_by_account_name(name)
            print_warning(f"Account '{name}' already exists ({existing_email})")
            
            if check_token_valid(name):
                print_info("Token is valid. No re-authorization needed.")
                if not confirm("Re-authorize this account anyway?"):
                    return name  # Return existing account
            else:
                print_info("Token is invalid or expired.")
                if not confirm("Re-authorize this account?"):
                    continue  # Ask for different name
            
            # User wants to re-authorize existing account
            break
        
        # Check if token file exists for this name (orphaned token)
        if check_token_exists(name):
            print_warning(f"Token file exists for '{name}' but account not in config.")
            if confirm("Remove orphaned token and continue?", default=True):
                get_token_path(name).unlink()
            else:
                continue
        
        break
    
    # Get email
    while True:
        email = prompt("Email address")
        
        if not email or "@" not in email:
            print_error("Valid email address is required")
            continue
        
        # Check duplicate email (different account name)
        existing_account = find_account_by_email(email)
        if existing_account and existing_account != name:
            print_warning(f"Email '{email}' already registered as account '{existing_account}'")
            
            if confirm(f"Use existing account '{existing_account}' instead?", default=True):
                name = existing_account
                if check_token_valid(name):
                    print_info("Token is valid. No re-authorization needed.")
                    if not confirm("Re-authorize anyway?"):
                        return name
                break
            else:
                # Allow same email for different account (user's choice)
                if not confirm("Register same email under different account name?"):
                    continue
        
        break
    
    # OAuth client handling - always offer choice if one exists
    if has_oauth_client():
        project_id = get_oauth_project_id() or "unknown"
        print(f"\nExisting OAuth client: {project_id}")
        
        if confirm("Use different OAuth client (different Google Cloud project)?"):
            try:
                credentials = collect_oauth_client()
                save_oauth_client(credentials)
                new_project = credentials.get("installed", credentials.get("web", {})).get("project_id", "unknown")
                print_success(f"OAuth client updated: {new_project}")
            except ValueError as e:
                print_error(str(e))
                return None
        else:
            print_info(f"Using existing OAuth client: {project_id}")
    else:
        print()
        try:
            credentials = collect_oauth_client()
            save_oauth_client(credentials)
            print_success("OAuth client saved")
        except ValueError as e:
            print_error(str(e))
            return None
    
    # Run OAuth flow with email hint for account pre-selection
    print(f"\nOpening browser — sign in with {email}...")
    
    try:
        run_oauth_flow(name, email_hint=email)
    except Exception as e:
        print_error(f"Authorization failed: {e}")
        return None
    
    # Verify and get actual email + timezone
    try:
        profile = verify_credentials(name)
        actual_email = profile.get("email")
        timezone = profile.get("timezone")
    except Exception:
        actual_email = None
        timezone = None
    
    # Check email match
    if actual_email and actual_email.lower() != email.lower():
        print_warning(f"You entered: {email}")
        print_warning(f"But authorized: {actual_email}")
        
        # Check if actual_email already exists under different account
        existing_for_actual = find_account_by_email(actual_email)
        if existing_for_actual and existing_for_actual != name:
            print_error(f"Email '{actual_email}' already registered as '{existing_for_actual}'")
            print_info("Either re-authorize with correct email or remove existing account first.")
            # Remove the token we just created
            token_path = get_token_path(name)
            if token_path.exists():
                token_path.unlink()
            return None
        
        if not confirm("Save with authorized email?", default=True):
            print("Aborted.")
            # Remove the token we just created
            token_path = get_token_path(name)
            if token_path.exists():
                token_path.unlink()
            return None
        
        email = actual_email
    
    # Save account
    add_account(name, email, timezone)
    
    default_marker = " (default)" if is_default(name) else ""
    tz_info = f" [{timezone}]" if timezone else ""
    print_success(f"Account '{name}' authorized: {email}{tz_info}{default_marker}")
    
    return name


def auth_remove(name: str) -> bool:
    """
    Remove an account.
    
    Returns True on success.
    """
    account = get_account(name)
    
    if not account:
        # Check for orphaned token
        if check_token_exists(name):
            print_warning(f"Account '{name}' not in config but token file exists.")
            if confirm("Remove orphaned token file?"):
                get_token_path(name).unlink()
                print_success("Orphaned token removed")
                return True
        
        print_error(f"Account '{name}' not found")
        return False
    
    email = account.get("email", "unknown")
    
    if not confirm(f"Remove account '{name}' ({email})?"):
        print("Aborted.")
        return False
    
    if remove_account(name):
        print_success(f"Account '{name}' removed")
        return True
    else:
        print_error(f"Failed to remove account '{name}'")
        return False


def auth_set_default(name: str) -> bool:
    """
    Set default account.
    
    Returns True on success.
    """
    if set_default_account(name):
        email = get_email_by_account_name(name) or "unknown"
        print_success(f"Default account set to '{name}' ({email})")
        return True
    else:
        print_error(f"Account '{name}' not found")
        return False


def auth_list() -> None:
    """List all configured accounts with status."""
    accounts = list_accounts()
    
    if not accounts:
        print("No accounts configured.")
        print("Run 'gcalendar-mcp auth' to add an account.")
        return
    
    print("\nConfigured accounts:\n")
    
    for name, info in accounts.items():
        email = info.get("email", "unknown")
        timezone = info.get("timezone", "")
        default_marker = " [default]" if is_default(name) else ""
        tz_info = f" ({timezone})" if timezone else ""
        
        # Check token status
        if check_token_valid(name):
            status = "✓"
        elif check_token_exists(name):
            status = "⚠ token expired"
        else:
            status = "✗ no token"
        
        print(f"  {status} {name}: {email}{tz_info}{default_marker}")
    
    print()


def run_auth(
    remove: Optional[str] = None,
    list_accounts_flag: bool = False,
    set_default: Optional[str] = None
) -> int:
    """
    Main auth command entry point.
    
    Returns exit code (0 = success, 1 = error).
    """
    # List accounts
    if list_accounts_flag:
        auth_list()
        return 0
    
    # Set default
    if set_default:
        return 0 if auth_set_default(set_default) else 1
    
    # Remove account
    if remove:
        return 0 if auth_remove(remove) else 1
    
    # Add account(s) interactively
    print_header("GCalendar MCP Account Setup")
    
    while True:
        result = auth_add_account()
        
        if result is None:
            return 1
        
        print()
        if not confirm("Add another account?"):
            break
        
        print()
    
    # Show summary
    print_header("Setup Complete")
    auth_list()
    
    print("Server will start automatically when invoked by Claude Desktop.\n")
    
    return 0

# Google Calendar MCP Server - Prioritized Fix Plan
**Date:** December 12, 2025
**Status:** Action Required
**Estimated Total Effort:** 368 hours (46 days at 8 hours/day)

---

## Priority Matrix

| Priority | Issues | Est. Effort | Business Impact | Risk Level |
|----------|--------|-------------|-----------------|------------|
| **P0 - Critical** | 5 | 16h (2d) | HIGH | CRITICAL |
| **P1 - High** | 7 | 48h (6d) | HIGH | HIGH |
| **P2 - Medium** | 6 | 304h (38d) | CRITICAL | MEDIUM |
| **P3 - Low** | 10 | 80h (10d) | MEDIUM | LOW |

---

## P0: CRITICAL - Week 1 (Must Fix Immediately)

### Issue #1: Credential File Permissions Vulnerability
**Priority:** P0 🔴 CRITICAL
**Category:** Security
**Estimated Effort:** 2 hours
**Risk:** Account takeover, token theft

**Problem:**
OAuth credentials and tokens written with default permissions (0644), readable by all users.

**Files to Fix:**
- `src/google_calendar/utils/config.py:186-192` - `save_oauth_client()`
- `src/google_calendar/utils/config.py:81-87` - `save_config()`
- `src/google_calendar/api/client.py:72-75` - `save_credentials()`

**Implementation:**

```python
import os
from pathlib import Path

def save_oauth_client(credentials: dict) -> None:
    """Save OAuth client credentials with secure permissions."""
    oauth_path = get_oauth_client_path()

    # Write file
    oauth_path.write_text(
        json.dumps(credentials, indent=2),
        encoding="utf-8"
    )

    # Set secure permissions (owner read/write only)
    os.chmod(oauth_path, 0o600)  # -rw-------

def save_credentials(account: str, creds: Credentials) -> None:
    """Save credentials with secure permissions."""
    token_path = get_token_path(account)
    token_path.parent.mkdir(parents=True, exist_ok=True)

    token_path.write_text(creds.to_json(), encoding="utf-8")
    os.chmod(token_path, 0o600)  # -rw-------

def save_config(config: dict) -> None:
    """Save configuration with secure permissions."""
    config_path = get_config_path()
    config_path.write_text(
        json.dumps(config, indent=2),
        encoding="utf-8"
    )
    os.chmod(config_path, 0o600)  # -rw-------
```

**Testing:**
```python
# Test file permissions
def test_credential_permissions():
    # Create test credential
    save_credentials("test", mock_credentials)

    # Check permissions
    token_path = get_token_path("test")
    stat_info = token_path.stat()
    permissions = oct(stat_info.st_mode)[-3:]

    assert permissions == "600", f"Expected 600, got {permissions}"
```

**Validation:**
```bash
# After fix, verify:
ls -l ~/.mcp/gcalendar/
# Should show: -rw------- (600) for all credential files
```

---

### Issue #2: Token Refresh Failures Not Logged
**Priority:** P0 🔴 CRITICAL
**Category:** Security / Observability
**Estimated Effort:** 1 hour
**Risk:** Cannot detect credential compromise

**Problem:**
Token refresh exceptions swallowed without logging, no audit trail.

**File to Fix:**
- `src/google_calendar/api/client.py:57-64`

**Implementation:**

```python
import logging
from google.auth.exceptions import RefreshError

logger = logging.getLogger(__name__)

def get_credentials(account: Optional[str] = None) -> Optional[Credentials]:
    """Get credentials for an account with logging."""
    # ... existing code ...

    if creds and creds.expired and creds.refresh_token:
        try:
            logger.info(f"Refreshing token for account: {account}")
            creds.refresh(Request())

            # Save refreshed token with secure permissions
            token_path.write_text(creds.to_json(), encoding="utf-8")
            os.chmod(token_path, 0o600)

            logger.info(f"Token refresh successful for account: {account}")

        except RefreshError as e:
            logger.error(
                f"Token refresh failed for account {account}: {e}",
                extra={"account": account, "error_type": "RefreshError"}
            )
            return None

        except Exception as e:
            logger.exception(
                f"Unexpected error refreshing token for {account}",
                extra={"account": account}
            )
            return None

    return creds
```

**Testing:**
```python
def test_token_refresh_logging(caplog):
    """Test that token refresh is logged."""
    with caplog.at_level(logging.INFO):
        get_credentials("test")

    assert "Refreshing token" in caplog.text
    assert "Token refresh successful" in caplog.text
```

---

### Issue #3: No Rate Limiting on API Calls
**Priority:** P0 🔴 CRITICAL
**Category:** Performance / Security
**Estimated Effort:** 4 hours
**Risk:** API quota exhaustion, account suspension

**Problem:**
No protection against quota exhaustion. Google Calendar API limits:
- 1,000,000 queries/day
- 10 queries/second/user

**Files to Fix:**
- `src/google_calendar/api/client.py` - Add rate limiter
- `src/google_calendar/tools/intelligence/batch_operations.py:17` - Add batch size limit

**Implementation:**

```python
# src/google_calendar/utils/rate_limiter.py

from functools import wraps
from time import time, sleep
from collections import defaultdict, deque
from threading import Lock

class RateLimiter:
    """Token bucket rate limiter."""

    def __init__(self, calls_per_second: int = 8):
        """
        Initialize rate limiter.

        Args:
            calls_per_second: Max API calls per second (default 8, under Google's 10/sec limit)
        """
        self.calls_per_second = calls_per_second
        self.calls = defaultdict(deque)
        self.lock = Lock()

    def wait_if_needed(self, account: str):
        """Wait if rate limit would be exceeded."""
        with self.lock:
            now = time()

            # Remove calls older than 1 second
            while self.calls[account] and now - self.calls[account][0] > 1.0:
                self.calls[account].popleft()

            # Check if we're at limit
            if len(self.calls[account]) >= self.calls_per_second:
                # Calculate wait time
                oldest_call = self.calls[account][0]
                wait_time = 1.0 - (now - oldest_call)

                if wait_time > 0:
                    logger.info(f"Rate limit reached for {account}, waiting {wait_time:.2f}s")
                    sleep(wait_time)
                    now = time()

            # Record this call
            self.calls[account].append(now)

# Global rate limiter instance
_rate_limiter = RateLimiter(calls_per_second=8)

def rate_limited(func):
    """Decorator to rate limit API calls."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        # Extract account from kwargs
        account = kwargs.get('account', 'default')

        # Wait if needed
        _rate_limiter.wait_if_needed(account)

        return func(*args, **kwargs)

    return wrapper

# Apply to API functions
@rate_limited
def api_list_events(calendar_id: str = "primary", ..., account: Optional[str] = None):
    # ... existing implementation ...
```

**Batch Size Limit:**

```python
# src/google_calendar/tools/intelligence/batch_operations.py

MAX_BATCH_SIZE = 100  # Reasonable limit for batch operations

def batch_operations(
    operations: list[dict],
    calendar_id: str = "primary",
    send_updates: str = "all",
    account: Optional[str] = None,
) -> dict:
    """Execute batch operations with size limit."""

    # Validate batch size
    if len(operations) > MAX_BATCH_SIZE:
        raise ValueError(
            f"Batch size {len(operations)} exceeds maximum {MAX_BATCH_SIZE}. "
            f"Please split into multiple batches."
        )

    # ... rest of implementation ...
```

**Testing:**
```python
def test_rate_limiter():
    """Test rate limiting prevents excessive calls."""
    limiter = RateLimiter(calls_per_second=2)

    start = time()
    for i in range(5):
        limiter.wait_if_needed("test")
    end = time()

    # Should take at least 2 seconds (5 calls / 2 per second)
    assert end - start >= 2.0

def test_batch_size_limit():
    """Test batch operation size limit."""
    operations = [{"action": "create"}] * 150

    with pytest.raises(ValueError, match="exceeds maximum 100"):
        batch_operations(operations)
```

---

### Issue #4: Zero Test Coverage
**Priority:** P0 🔴 CRITICAL
**Category:** Testing
**Estimated Effort:** 3 hours (skeleton), 40+ hours (comprehensive)
**Risk:** Undetected breaking changes

**Problem:**
No tests despite pytest configuration. Critical logic untested:
- Recurring event handling
- Timezone conversions
- OAuth flows

**Implementation - Test Skeleton:**

```bash
# Create test structure
mkdir -p tests/{test_api,test_tools,test_cli,test_utils}

# Create test files
touch tests/conftest.py
touch tests/test_api/test_client.py
touch tests/test_api/test_events.py
touch tests/test_tools/test_create_event.py
touch tests/test_utils/test_config.py
```

**tests/conftest.py:**
```python
import pytest
from unittest.mock import MagicMock, patch
from google.oauth2.credentials import Credentials

@pytest.fixture
def mock_credentials():
    """Mock Google OAuth credentials."""
    creds = MagicMock(spec=Credentials)
    creds.valid = True
    creds.expired = False
    creds.refresh_token = "mock_refresh_token"
    creds.to_json.return_value = '{"token": "mock_token"}'
    return creds

@pytest.fixture
def mock_service():
    """Mock Google Calendar service."""
    with patch('google_calendar.api.client.get_service') as mock:
        service = MagicMock()
        mock.return_value = service
        yield service

@pytest.fixture
def sample_event():
    """Sample calendar event."""
    return {
        "id": "test_event_123",
        "summary": "Test Meeting",
        "start": {"dateTime": "2025-01-15T10:00:00-08:00"},
        "end": {"dateTime": "2025-01-15T11:00:00-08:00"},
        "attendees": [
            {"email": "user1@example.com"},
            {"email": "user2@example.com"}
        ],
        "status": "confirmed",
        "htmlLink": "https://calendar.google.com/event?eid=123"
    }
```

**tests/test_api/test_events.py:**
```python
import pytest
from google_calendar.api.events import format_event_summary, _is_date_only, _ensure_rfc3339

def test_is_date_only():
    """Test date-only string detection."""
    assert _is_date_only("2025-01-15") == True
    assert _is_date_only("2025-01-15T10:00:00") == False
    assert _is_date_only("2025-01-15T10:00:00Z") == False

def test_ensure_rfc3339_with_timezone():
    """Test RFC3339 with timezone is unchanged."""
    assert _ensure_rfc3339("2025-01-15T10:00:00Z") == "2025-01-15T10:00:00Z"
    assert _ensure_rfc3339("2025-01-15T10:00:00-08:00") == "2025-01-15T10:00:00-08:00"

def test_ensure_rfc3339_without_timezone():
    """Test RFC3339 without timezone gets Z suffix."""
    assert _ensure_rfc3339("2025-01-15T10:00:00") == "2025-01-15T10:00:00Z"

def test_ensure_rfc3339_date_only_raises():
    """Test RFC3339 validation rejects date-only."""
    with pytest.raises(ValueError, match="Expected datetime, got date"):
        _ensure_rfc3339("2025-01-15")

def test_format_event_summary(sample_event):
    """Test event summary formatting."""
    summary = format_event_summary(sample_event)

    assert summary["id"] == "test_event_123"
    assert summary["summary"] == "Test Meeting"
    assert summary["attendees"] == 2  # Count, not list
    assert "hasConference" in summary
```

**tests/test_tools/test_create_event.py:**
```python
import pytest
from google_calendar.tools.crud.create_event import create_event

def test_create_event_basic(mock_service, sample_event):
    """Test basic event creation."""
    mock_service.events().insert().execute.return_value = sample_event

    result = create_event(
        summary="Test Meeting",
        start="2025-01-15T10:00:00",
        end="2025-01-15T11:00:00"
    )

    assert result["id"] == "test_event_123"
    assert result["summary"] == "Test Meeting"
    assert result["attendees"] == 2
```

**Run tests:**
```bash
pytest tests/ -v --cov=src/google_calendar --cov-report=html
```

---

### Issue #5: Incomplete "Following" Scope in update_event
**Priority:** P0 🔴 CRITICAL
**Category:** Functionality
**Estimated Effort:** 6 hours
**Risk:** Users expect feature that doesn't work

**Problem:**
TODO comment at `update_event.py:123` - "following" scope partially implemented.

**File to Fix:**
- `src/google_calendar/tools/crud/update_event.py:84-141`

**Current State:**
```python
if scope == "following":
    # TODO: This only updates the instance, not the master RRULE
    # Properly handling "this and following" requires complex RRULE modification
    pass  # Currently just updates the instance
```

**Implementation:**

```python
def update_event(
    event_id: str,
    calendar_id: str = "primary",
    scope: str = "single",
    ...
) -> dict:
    """Update calendar event with proper 'following' scope support."""

    service = get_service(account)

    if scope == "following":
        # Get the instance
        instance = service.events().get(
            calendarId=calendar_id,
            eventId=event_id
        ).execute()

        # Get original start time of this instance
        original_start = instance.get("originalStartTime", {}).get("dateTime")
        if not original_start:
            raise ValueError(
                "Cannot use 'following' scope on non-recurring event. "
                "Use scope='single' instead."
            )

        # Get the master event (recurring rule)
        recurring_event_id = instance.get("recurringEventId")
        if not recurring_event_id:
            raise ValueError("Could not find master recurring event ID")

        master_event = service.events().get(
            calendarId=calendar_id,
            eventId=recurring_event_id
        ).execute()

        # Parse original RRULE
        rrule_lines = master_event.get("recurrence", [])
        if not rrule_lines:
            raise ValueError("Master event has no recurrence rules")

        # Modify RRULE to end before this instance
        from datetime import datetime
        original_dt = datetime.fromisoformat(original_start.replace('Z', '+00:00'))

        # Update master RRULE to end before this occurrence
        updated_rrule = []
        for line in rrule_lines:
            if line.startswith("RRULE:"):
                # Remove existing UNTIL/COUNT
                parts = [p for p in line.split(';')
                        if not p.startswith('UNTIL=') and not p.startswith('COUNT=')]

                # Add UNTIL for day before this occurrence
                until_dt = original_dt.replace(hour=0, minute=0, second=0)
                until_str = until_dt.strftime("%Y%m%dT%H%M%SZ")
                parts.append(f"UNTIL={until_str}")

                updated_rrule.append(';'.join(parts))
            else:
                updated_rrule.append(line)

        # Update master event
        master_event["recurrence"] = updated_rrule
        service.events().update(
            calendarId=calendar_id,
            eventId=recurring_event_id,
            body=master_event
        ).execute()

        # Create new recurring event starting from this instance
        new_event = {**master_event}
        new_event.pop("id", None)
        new_event.pop("recurringEventId", None)
        new_event["start"] = instance["start"]
        new_event["end"] = instance["end"]

        # Apply updates
        if summary is not None:
            new_event["summary"] = summary
        # ... apply other updates ...

        result = service.events().insert(
            calendarId=calendar_id,
            body=new_event,
            sendUpdates=send_updates
        ).execute()

        return format_event_summary(result)

    # ... existing single/all logic ...
```

**Testing:**
```python
def test_update_following_scope(mock_service):
    """Test 'following' scope updates master RRULE."""
    # Mock recurring event instance
    instance = {
        "id": "instance_123",
        "recurringEventId": "master_123",
        "originalStartTime": {"dateTime": "2025-01-15T10:00:00Z"}
    }

    master = {
        "id": "master_123",
        "recurrence": ["RRULE:FREQ=WEEKLY;BYDAY=MO"]
    }

    mock_service.events().get.side_effect = [instance, master]

    update_event(
        event_id="instance_123",
        scope="following",
        summary="Updated"
    )

    # Verify RRULE was modified with UNTIL
    update_call = mock_service.events().update.call_args
    updated_master = update_call[1]["body"]

    assert "UNTIL=" in updated_master["recurrence"][0]
```

---

## P0 Summary

| Issue | Effort | Files Changed | Tests Added |
|-------|--------|---------------|-------------|
| #1 File permissions | 2h | 3 | 1 |
| #2 Refresh logging | 1h | 1 | 1 |
| #3 Rate limiting | 4h | 3 | 2 |
| #4 Test skeleton | 3h | 10 | 5 |
| #5 "Following" scope | 6h | 1 | 1 |
| **TOTAL** | **16h** | **18** | **10** |

**Validation Checklist:**
- [ ] All credential files have 0600 permissions
- [ ] Token refresh success/failure logged
- [ ] Rate limiter tested under load
- [ ] pytest runs successfully
- [ ] "Following" scope updates RRULE correctly

---

## P1: HIGH PRIORITY - Month 1

### Issue #6: No Structured Logging
**Priority:** P1 ⚠️ HIGH
**Category:** Observability
**Estimated Effort:** 8 hours

**Implementation:**

```python
# src/google_calendar/utils/logging.py

import logging
import logging.handlers
from pathlib import Path
from google_calendar.utils.config import get_app_dir

def setup_logging(level: str = "INFO") -> None:
    """Configure structured logging."""
    log_dir = get_app_dir() / "logs"
    log_dir.mkdir(exist_ok=True)

    # Main application log
    app_log = log_dir / "google_calendar.log"

    # Rotating file handler (10MB, 5 backups)
    file_handler = logging.handlers.RotatingFileHandler(
        app_log,
        maxBytes=10*1024*1024,
        backupCount=5,
        encoding='utf-8'
    )

    # Audit log (separate file for security events)
    audit_log = log_dir / "audit.log"
    audit_handler = logging.FileHandler(audit_log, encoding='utf-8')
    audit_handler.setLevel(logging.INFO)

    # Formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    file_handler.setFormatter(formatter)
    audit_handler.setFormatter(formatter)

    # Sensitive data filter
    class SensitiveDataFilter(logging.Filter):
        """Redact tokens, passwords, secrets from logs."""
        SENSITIVE_PATTERNS = ['token', 'password', 'secret', 'key', 'credential']

        def filter(self, record):
            if hasattr(record, 'msg'):
                msg = str(record.msg)
                for pattern in self.SENSITIVE_PATTERNS:
                    if pattern in msg.lower():
                        record.msg = msg[:50] + ' [REDACTED]'
            return True

    file_handler.addFilter(SensitiveDataFilter())

    # Configure root logger
    root_logger = logging.getLogger('google_calendar')
    root_logger.setLevel(getattr(logging, level.upper()))
    root_logger.addHandler(file_handler)

    # Configure audit logger
    audit_logger = logging.getLogger('google_calendar.audit')
    audit_logger.addHandler(audit_handler)
    audit_logger.setLevel(logging.INFO)

# Helper functions
def log_api_call(operation: str, account: str, **kwargs):
    """Log API operations."""
    logger = logging.getLogger('google_calendar.api')
    logger.info(f"API call: {operation}", extra={
        "account": account,
        **kwargs
    })

def log_auth_event(event_type: str, account: str, success: bool, **kwargs):
    """Log authentication events to audit log."""
    audit_logger = logging.getLogger('google_calendar.audit')

    level = logging.INFO if success else logging.WARNING
    audit_logger.log(level, f"AUTH_{event_type}", extra={
        "account": account,
        "success": success,
        **kwargs
    })
```

**Usage in code:**

```python
# In server.py
from google_calendar.utils.logging import setup_logging

def main():
    setup_logging(level="INFO")
    # ... rest of main ...

# In api/client.py
from google_calendar.utils.logging import log_api_call

def api_list_events(...):
    log_api_call("list_events", account=account, calendar_id=calendar_id)
    # ... rest of implementation ...

# In cli/auth.py
from google_calendar.utils.logging import log_auth_event

def auth_add_account(...):
    try:
        # ... OAuth flow ...
        log_auth_event("ADD_ACCOUNT", name, success=True, email=email)
    except Exception as e:
        log_auth_event("ADD_ACCOUNT", name, success=False, error=str(e))
```

---

### Issue #7: Improve Email Validation
**Priority:** P1 ⚠️ HIGH
**Category:** Security
**Estimated Effort:** 2 hours

**Implementation:**

```python
# src/google_calendar/utils/validation.py

import re
from typing import Union

EMAIL_REGEX = re.compile(
    r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
)

MAX_EMAIL_LENGTH = 254  # RFC 5321

def validate_email(email: str) -> tuple[bool, Union[str, None]]:
    """
    Validate email address format.

    Returns:
        (is_valid, error_message)
    """
    if not email:
        return False, "Email address is required"

    email = email.strip()

    if len(email) > MAX_EMAIL_LENGTH:
        return False, f"Email address too long (max {MAX_EMAIL_LENGTH} characters)"

    if not EMAIL_REGEX.match(email):
        return False, "Invalid email format (e.g., user@example.com)"

    # Check for homograph attacks (non-ASCII chars that look like ASCII)
    try:
        email.encode('ascii')
    except UnicodeEncodeError:
        return False, "Email contains non-ASCII characters"

    return True, None

# Use in auth.py
from google_calendar.utils.validation import validate_email

def auth_add_account(...):
    email = prompt("Email address").strip()

    is_valid, error = validate_email(email)
    if not is_valid:
        print_error(error)
        continue
```

---

### Issue #8: Add Input Length Limits
**Priority:** P1 ⚠️ HIGH
**Category:** Security / Performance
**Estimated Effort:** 4 hours

**Implementation:**

```python
# src/google_calendar/utils/validation.py

# Field length limits (based on Google Calendar API)
MAX_SUMMARY_LENGTH = 1024
MAX_DESCRIPTION_LENGTH = 8192
MAX_LOCATION_LENGTH = 1024
MAX_ATTENDEE_COUNT = 200

def validate_string_length(
    value: str,
    field_name: str,
    max_length: int
) -> tuple[bool, Union[str, None]]:
    """Validate string length."""
    if not value:
        return True, None

    if len(value) > max_length:
        return False, f"{field_name} exceeds maximum length of {max_length} characters"

    return True, None

# Apply to create_event
def create_event(
    summary: str,
    start: str,
    end: str,
    description: Optional[str] = None,
    location: Optional[str] = None,
    attendees: Optional[list[str]] = None,
    ...
) -> dict:
    """Create event with input validation."""

    # Validate lengths
    is_valid, error = validate_string_length(summary, "Summary", MAX_SUMMARY_LENGTH)
    if not is_valid:
        raise ValueError(error)

    if description:
        is_valid, error = validate_string_length(description, "Description", MAX_DESCRIPTION_LENGTH)
        if not is_valid:
            raise ValueError(error)

    if location:
        is_valid, error = validate_string_length(location, "Location", MAX_LOCATION_LENGTH)
        if not is_valid:
            raise ValueError(error)

    if attendees and len(attendees) > MAX_ATTENDEE_COUNT:
        raise ValueError(f"Too many attendees (max {MAX_ATTENDEE_COUNT})")

    # ... rest of implementation ...
```

---

### Issue #9: Optimize Docstrings (Save 1,800 Tokens)
**Priority:** P1 ⚠️ HIGH
**Category:** Token Efficiency
**Estimated Effort:** 6 hours

**Changes:**

1. **Move RRULE examples to README**
2. **Shorten time format explanations**
3. **Use schema-level defaults**

**Before (create_event.py):**
```python
"""
Args:
    start: Event start time: '2025-01-01T10:00:00' for timed events or '2025-01-01'
           for all-day events. Also accepts Google Calendar API object format:
           {date: '2025-01-01'} or {dateTime: '2025-01-01T10:00:00', timeZone: 'America/Los_Angeles'}
    ...
    recurrence: Recurrence rules in RFC5545 RRULE format. Examples:
        - Daily for 5 days: ["RRULE:FREQ=DAILY;COUNT=5"]
        - Every weekday: ["RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"]
        - Every Monday and Wednesday: ["RRULE:FREQ=WEEKLY;BYDAY=MO,WE"]
        - Monthly on 15th: ["RRULE:FREQ=MONTHLY;BYMONTHDAY=15"]
        - Every 2 weeks on Friday: ["RRULE:FREQ=WEEKLY;INTERVAL=2;BYDAY=FR"]
        - Until specific date: ["RRULE:FREQ=WEEKLY;BYDAY=MO;UNTIL=20250331T000000Z"]
"""
```

**After:**
```python
"""
Args:
    start: ISO datetime ('2025-01-01T10:00:00') or date ('2025-01-01')
    ...
    recurrence: RFC5545 RRULE list. Examples: ["RRULE:FREQ=DAILY;COUNT=5"],
                ["RRULE:FREQ=WEEKLY;BYDAY=MO,WE"]. See README for full reference.
"""
```

**Add to README.md:**
```markdown
## RRULE Reference

Common recurrence patterns:

| Pattern | RRULE |
|---------|-------|
| Daily for 5 days | `RRULE:FREQ=DAILY;COUNT=5` |
| Every weekday | `RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR` |
| Every Monday & Wednesday | `RRULE:FREQ=WEEKLY;BYDAY=MO,WE` |
| Monthly on 15th | `RRULE:FREQ=MONTHLY;BYMONTHDAY=15` |
| Every 2 weeks on Friday | `RRULE:FREQ=WEEKLY;INTERVAL=2;BYDAY=FR` |
| Until specific date | `RRULE:FREQ=WEEKLY;BYDAY=MO;UNTIL=20250331T000000Z` |

[Full RFC5545 specification](https://icalendar.org/iCalendar-RFC-5545/)
```

**Token Savings:** ~150 tokens per tool × 12 tools = 1,800 tokens

---

### Issue #10: Add GitHub Actions CI
**Priority:** P1 ⚠️ HIGH
**Category:** DevOps
**Estimated Effort:** 4 hours

**Implementation:**

```yaml
# .github/workflows/ci.yml

name: CI

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

jobs:
  test:
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest]
        python-version: ['3.10', '3.11', '3.12']

    steps:
    - uses: actions/checkout@v3

    - name: Set up Python ${{ matrix.python-version }}
      uses: actions/setup-python@v4
      with:
        python-version: ${{ matrix.python-version }}

    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -e .[dev]

    - name: Lint with ruff
      run: |
        ruff check src/

    - name: Type check with mypy
      run: |
        mypy src/ --ignore-missing-imports
      continue-on-error: true  # Don't fail yet, just report

    - name: Run tests
      run: |
        pytest tests/ -v --cov=src/google_calendar --cov-report=xml --cov-report=term

    - name: Upload coverage to Codecov
      uses: codecov/codecov-action@v3
      with:
        file: ./coverage.xml
        flags: unittests
        name: codecov-umbrella

  security:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v3

    - name: Run Bandit security scan
      run: |
        pip install bandit
        bandit -r src/ -f json -o bandit-report.json
      continue-on-error: true

    - name: Upload Bandit results
      uses: actions/upload-artifact@v3
      with:
        name: bandit-report
        path: bandit-report.json
```

---

### Issue #11: Create User Preference System
**Priority:** P1 ⚠️ HIGH
**Category:** User Experience
**Estimated Effort:** 8 hours

**Implementation:**

```python
# src/google_calendar/utils/preferences.py

from pathlib import Path
import json
from typing import Optional

def get_preferences_path() -> Path:
    """Get user preferences file path."""
    return get_app_dir() / "preferences.json"

def load_preferences() -> dict:
    """Load user preferences."""
    pref_path = get_preferences_path()

    if not pref_path.exists():
        return {
            "default_timezone": None,
            "default_calendar_id": "primary",
            "work_hours_start": "09:00",
            "work_hours_end": "17:00",
            "default_meeting_duration": 60,
            "default_send_updates": "all"
        }

    with open(pref_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_preferences(preferences: dict) -> None:
    """Save user preferences."""
    pref_path = get_preferences_path()

    with open(pref_path, 'w', encoding='utf-8') as f:
        json.dump(preferences, f, indent=2)

    os.chmod(pref_path, 0o600)

# Add CLI command
def cli_preferences():
    """Interactive preference editor."""
    prefs = load_preferences()

    print("\nCurrent Preferences:")
    for key, value in prefs.items():
        print(f"  {key}: {value}")

    print("\nUpdate preferences (leave blank to keep current):")

    new_tz = input(f"Default timezone [{prefs['default_timezone']}]: ").strip()
    if new_tz:
        prefs['default_timezone'] = new_tz

    # ... repeat for other preferences ...

    save_preferences(prefs)
    print("✓ Preferences saved")

# Use in tools
def create_event(..., timezone: Optional[str] = None, ...):
    """Create event with preference defaults."""
    prefs = load_preferences()

    # Use preference as fallback
    if timezone is None:
        timezone = prefs.get('default_timezone', 'UTC')

    # ... rest of implementation ...
```

---

### Issue #12: Simplify Onboarding (Automated Setup)
**Priority:** P1 ⚠️ HIGH
**Category:** User Experience
**Estimated Effort:** 16 hours

**Implementation:**

```python
# src/google_calendar/cli/quickstart.py

import webbrowser
from pathlib import Path

def quick_start():
    """Guided quick start for first-time users."""

    print("🚀 Google Calendar MCP Quick Start\n")
    print("This wizard will help you set up your calendar integration.\n")

    # Step 1: Check Python version
    print("Step 1/5: Checking prerequisites...")
    import sys
    if sys.version_info < (3, 10):
        print("❌ Python 3.10+ required. You have:", sys.version)
        return
    print("✓ Python version OK")

    # Step 2: Check OAuth credentials
    print("\nStep 2/5: Setting up Google Cloud credentials...")
    oauth_path = get_oauth_client_path()

    if not oauth_path.exists():
        print("""
To use this tool, you need OAuth credentials from Google Cloud:

1. Go to: https://console.cloud.google.com/apis/credentials
2. Create a new OAuth 2.0 Client ID
3. Download the JSON file
4. Paste the path below

Full instructions: https://github.com/YOUR_REPO/blob/main/docs/SETUP.md
        """)

        # Option 1: Path to file
        cred_path = input("\nPath to credentials JSON file: ").strip()

        if cred_path:
            import shutil
            shutil.copy(cred_path, oauth_path)
            print("✓ Credentials saved")
        else:
            # Option 2: Paste JSON
            print("\nOr paste JSON content (Ctrl+D when done):")
            import sys
            json_content = sys.stdin.read()
            oauth_path.write_text(json_content)
            print("✓ Credentials saved")
    else:
        print("✓ OAuth credentials found")

    # Step 3: Add account
    print("\nStep 3/5: Connecting your Google Calendar...")
    account_name = input("Account name (e.g., 'work', 'personal'): ").strip()

    try:
        auth_add_account(account_name)
        print(f"✓ Account '{account_name}' connected")
    except Exception as e:
        print(f"❌ Failed to connect account: {e}")
        return

    # Step 4: Set preferences
    print("\nStep 4/5: Setting preferences...")
    timezone = input("Your timezone (e.g., 'America/Los_Angeles'): ").strip()

    prefs = {
        "default_timezone": timezone or "UTC",
        "default_calendar_id": "primary",
        "work_hours_start": "09:00",
        "work_hours_end": "17:00"
    }
    save_preferences(prefs)
    print("✓ Preferences saved")

    # Step 5: Install Claude Desktop integration
    print("\nStep 5/5: Installing Claude Desktop integration...")
    try:
        install_to_claude_desktop()
        print("✓ Claude Desktop integration installed")
    except Exception as e:
        print(f"⚠ Could not auto-install: {e}")
        print("\nManual installation instructions:")
        print("  Add to Claude Desktop config.json:")
        print(f"""
  "google-calendar-mcp": {{
    "command": "python",
    "args": ["-m", "google_calendar"]
  }}
        """)

    # Done!
    print("\n🎉 Setup complete!")
    print("\nNext steps:")
    print("  1. Restart Claude Desktop")
    print("  2. Ask Claude: 'What's on my calendar today?'")
    print("  3. Read the docs: https://github.com/YOUR_REPO")

# Add to CLI
if __name__ == "__main__":
    if "--quickstart" in sys.argv:
        quick_start()
```

**Add to README:**
```markdown
## Quick Start (< 5 minutes)

```bash
pip install google-calendar-mcp
google-calendar-mcp --quickstart
```

The wizard will guide you through:
1. Setting up Google Cloud credentials
2. Connecting your Google Calendar
3. Configuring preferences
4. Installing Claude Desktop integration
```

---

## P1 Summary

| Issue | Effort | Impact |
|-------|--------|--------|
| #6 Structured logging | 8h | Observability |
| #7 Email validation | 2h | Security |
| #8 Input length limits | 4h | Security/Performance |
| #9 Optimize docstrings | 6h | Token efficiency |
| #10 GitHub Actions CI | 4h | Code quality |
| #11 User preferences | 8h | User experience |
| #12 Automated setup | 16h | User experience |
| **TOTAL** | **48h** | |

---

## P2: BUSINESS-CRITICAL FEATURES - Quarter 1

### Issue #13: Time Tracking Foundation
**Priority:** P2 🟡 MEDIUM (but CRITICAL for consultants)
**Category:** Feature
**Estimated Effort:** 40 hours

**Goal:** Enable consultants to track billable hours from calendar events.

**Implementation:**

```python
# src/google_calendar/utils/time_tracking.py

from typing import Optional

# Extended properties schema for time tracking
TIME_TRACKING_SCHEMA = {
    "private": {
        "billable": "true|false",
        "client_code": "string",
        "project_code": "string",
        "task_type": "meeting|consulting|development|research",
        "hourly_rate": "float",
        "notes": "string"
    }
}

def mark_as_billable(
    event_id: str,
    client_code: str,
    project_code: Optional[str] = None,
    hourly_rate: Optional[float] = None,
    task_type: str = "meeting",
    calendar_id: str = "primary",
    account: Optional[str] = None
) -> dict:
    """
    Mark calendar event as billable time.

    Args:
        event_id: Event to mark
        client_code: Client identifier
        project_code: Optional project code
        hourly_rate: Optional override hourly rate
        task_type: Type of work (meeting, consulting, etc.)
    """
    service = get_service(account)

    # Get event
    event = service.events().get(
        calendarId=calendar_id,
        eventId=event_id
    ).execute()

    # Add time tracking metadata
    extended_props = event.get("extendedProperties", {"private": {}})
    extended_props["private"]["billable"] = "true"
    extended_props["private"]["client_code"] = client_code

    if project_code:
        extended_props["private"]["project_code"] = project_code
    if hourly_rate:
        extended_props["private"]["hourly_rate"] = str(hourly_rate)

    extended_props["private"]["task_type"] = task_type

    event["extendedProperties"] = extended_props

    # Update event
    updated = service.events().update(
        calendarId=calendar_id,
        eventId=event_id,
        body=event
    ).execute()

    return format_event_summary(updated)

def get_billable_hours(
    start_date: str,
    end_date: str,
    client_code: Optional[str] = None,
    project_code: Optional[str] = None,
    calendar_id: str = "primary",
    account: Optional[str] = None
) -> dict:
    """
    Calculate billable hours for a date range.

    Returns:
        {
            "total_hours": float,
            "total_amount": float,
            "by_client": {
                "client_code": {
                    "hours": float,
                    "amount": float,
                    "events": [...]
                }
            },
            "by_project": {...},
            "by_task_type": {...}
        }
    """
    service = get_service(account)

    # Fetch events
    events = service.events().list(
        calendarId=calendar_id,
        timeMin=_ensure_rfc3339(start_date),
        timeMax=_ensure_rfc3339(end_date),
        singleEvents=True
    ).execute()

    # Calculate billable hours
    total_hours = 0.0
    total_amount = 0.0
    by_client = {}
    by_project = {}
    by_task_type = {}

    for event in events.get("items", []):
        extended_props = event.get("extendedProperties", {}).get("private", {})

        # Skip non-billable
        if extended_props.get("billable") != "true":
            continue

        # Filter by client/project
        event_client = extended_props.get("client_code")
        event_project = extended_props.get("project_code")

        if client_code and event_client != client_code:
            continue
        if project_code and event_project != project_code:
            continue

        # Calculate duration
        start = event["start"].get("dateTime", event["start"].get("date"))
        end = event["end"].get("dateTime", event["end"].get("date"))

        from datetime import datetime
        start_dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
        end_dt = datetime.fromisoformat(end.replace('Z', '+00:00'))

        duration_hours = (end_dt - start_dt).total_seconds() / 3600

        # Get hourly rate
        hourly_rate = float(extended_props.get("hourly_rate", 0))
        amount = duration_hours * hourly_rate

        # Aggregate
        total_hours += duration_hours
        total_amount += amount

        # By client
        if event_client not in by_client:
            by_client[event_client] = {
                "hours": 0, "amount": 0, "events": []
            }
        by_client[event_client]["hours"] += duration_hours
        by_client[event_client]["amount"] += amount
        by_client[event_client]["events"].append({
            "id": event["id"],
            "summary": event.get("summary"),
            "start": start,
            "duration_hours": round(duration_hours, 2),
            "amount": round(amount, 2)
        })

        # Similar for by_project, by_task_type...

    return {
        "total_hours": round(total_hours, 2),
        "total_amount": round(total_amount, 2),
        "by_client": by_client,
        "by_project": by_project,
        "by_task_type": by_task_type
    }

def export_to_csv(
    start_date: str,
    end_date: str,
    output_file: str,
    client_code: Optional[str] = None,
    calendar_id: str = "primary",
    account: Optional[str] = None
) -> str:
    """Export billable hours to CSV."""
    import csv

    hours_data = get_billable_hours(
        start_date, end_date, client_code, calendar_id=calendar_id, account=account
    )

    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)

        # Header
        writer.writerow([
            "Date", "Client", "Project", "Task Type",
            "Summary", "Duration (hours)", "Rate", "Amount"
        ])

        # Rows
        for client, client_data in hours_data["by_client"].items():
            for event in client_data["events"]:
                writer.writerow([
                    event["start"][:10],
                    client,
                    event.get("project", ""),
                    event.get("task_type", "meeting"),
                    event["summary"],
                    event["duration_hours"],
                    event.get("rate", 0),
                    event["amount"]
                ])

    return f"Exported {len(hours_data['by_client'])} client records to {output_file}"
```

**MCP Tools:**
```python
@mcp.tool()
def mark_event_billable(...):
    """Mark calendar event as billable time."""

@mcp.tool()
def get_billable_hours_report(...):
    """Generate billable hours report for date range."""

@mcp.tool()
def export_timesheet(...):
    """Export billable hours to CSV for invoicing."""
```

---

### Issue #14: Harvest/Toggl Integration
**Priority:** P2 🟡 MEDIUM
**Category:** Integration
**Estimated Effort:** 24 hours

*(Implementation details for Harvest/Toggl API integration)*

---

### Issue #15-18: Additional Business Features

*(Detailed implementations for client portfolio management, meeting prep assistant, team resource dashboard, Jira/Asana integration)*

Due to length constraints, these are outlined in the audit report. Each requires 40-80 hours of development.

---

## P3: LOW PRIORITY - Backlog

### Nice-to-Have Improvements

1. **Refactor complex functions** (16h)
2. **Add result caching** (8h)
3. **Improve algorithm efficiency** (12h)
4. **Add type checking with mypy** (8h)
5. **Create architecture diagrams** (8h)
6. **Add inline code comments** (8h)
7. **Implement health check endpoint** (4h)
8. **Add metrics collection** (16h)

**Total P3 Effort:** 80 hours

---

## Implementation Timeline

### Week 1 (P0 - Critical)
- Day 1-2: Fix credential permissions, add logging, implement rate limiting
- Day 3: Create test skeleton, add basic tests
- Day 4-5: Implement "following" scope, add validation

### Month 1 (P1 - High Priority)
- Week 2: Structured logging, email validation, input limits
- Week 3: Optimize docstrings, set up CI/CD, create user preferences
- Week 4: Build automated onboarding wizard

### Quarter 1 (P2 - Business Features)
- Month 2: Time tracking foundation, Harvest integration
- Month 3: Client portfolio management, meeting prep assistant
- Month 4: Team resource dashboard, PM tool integrations

---

## Success Metrics

### P0 Completion Criteria
- [ ] All credential files have 0600 permissions
- [ ] Token refresh logged with success/failure
- [ ] Rate limiter prevents quota exhaustion
- [ ] Test suite runs with >50% coverage
- [ ] "Following" scope updates RRULE correctly

### P1 Completion Criteria
- [ ] Structured logging to file with rotation
- [ ] Email validation blocks malformed input
- [ ] Input length limits prevent DoS
- [ ] Docstrings optimized (1,800 token savings)
- [ ] CI pipeline passing on all PRs
- [ ] User preferences saved and applied
- [ ] Quick start wizard completes in <5 minutes

### P2 Completion Criteria
- [ ] Consultants can track billable hours
- [ ] Export to Harvest/CSV works
- [ ] Client portfolio management operational
- [ ] Meeting prep provides context
- [ ] Team resource dashboard shows capacity
- [ ] Jira/Asana sync bidirectional

---

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| Breaking changes | Comprehensive test suite (P0 #4) |
| Security incidents | Audit logging (P1 #6), file permissions (P0 #1) |
| API quota exhaustion | Rate limiting (P0 #3) |
| User abandonment | Simplified onboarding (P1 #12) |
| Feature creep | Strict prioritization, consultant focus first |

---

## Resource Requirements

### Developer Time
- **P0:** 2 days (1 senior developer)
- **P1:** 6 days (1 senior developer)
- **P2:** 38 days (1-2 developers, can parallelize)
- **P3:** 10 days (optional, backlog)

### Infrastructure
- GitHub Actions (free tier sufficient)
- Log storage (~100MB/month estimated)
- Test Google Calendar account

---

## Conclusion

This fix plan addresses **32 identified issues** across security, functionality, and user experience. The prioritization focuses on:

1. **P0 (Week 1):** Fix critical security vulnerabilities and establish testing
2. **P1 (Month 1):** Improve observability and user experience
3. **P2 (Quarter 1):** Build must-have business features for consultants/PMs

**Estimated Total Effort:** 368 hours (~46 days)

**Recommended Approach:**
- Start with P0 immediately (2 days)
- Allocate 1-2 developers for P1 (1 month)
- Focus P2 on consultant features first (time tracking = highest ROI)

With this plan, the project can move from "technically sound MVP" to "market-ready product" in 4-6 months.

---

**Plan Prepared By:** Multi-Agent Audit Team
**Plan Date:** December 12, 2025
**Next Review:** After P0 completion (Week 2)

# Google Calendar MCP Server

MCP (Model Context Protocol) server for Google Calendar integration with Claude Desktop. Provides comprehensive calendar management, multi-account support, time tracking, and contacts management.

## Features

**Core Calendar**
- Full CRUD operations for events (create, read, update, delete)
- Recurring event support with scope control (single instance, all, following)
- Attendee management with RSVP tracking
- Free/busy queries and meeting slot finder
- Batch operations for bulk changes
- Weekly briefing with analytics

**Multi-Account Support**
- Multiple Google accounts (work, personal, etc.)
- Account-aware tool calls with `account` parameter
- Per-account OAuth token management

**Time Tracking** *(optional module)*
- Project/phase/task hierarchy with billable flags
- Monthly hour norms and progress tracking
- Calendar event parsing with customizable patterns
- Excel report generation (weekly, monthly, custom)

**Contacts Management** *(optional module)*
- Contact database with multi-channel support (email, phone, Telegram, Teams)
- Project role assignments with 19 standard roles
- Fuzzy search and intelligent contact resolution
- Integration with Telegram/Teams/Gmail for enrichment
- Excel export for contacts and project teams

## Installation

### Prerequisites

- Python 3.10+
- Google Cloud project with Calendar API enabled
- OAuth 2.0 credentials (Desktop application type)

### Setup

```bash
# Clone repository
git clone https://github.com/DimaRmnv/G-calendar-mcp.git
cd G-calendar-mcp

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# Install package
pip install -e .
```

### Google OAuth Configuration

1. Create a project in [Google Cloud Console](https://console.cloud.google.com/)
2. Enable Google Calendar API
3. Create OAuth 2.0 credentials (Desktop application)
4. Download `client_secret.json`

```bash
# Initialize with OAuth credentials
google-calendar-mcp setup /path/to/client_secret.json

# Add Google account
google-calendar-mcp add-account work
# Opens browser for OAuth consent

# Optional: add more accounts
google-calendar-mcp add-account personal
```

### Claude Desktop Configuration

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "google-calendar": {
      "command": "/path/to/G-calendar-mcp/.venv/bin/python",
      "args": ["-m", "google_calendar"]
    }
  }
}
```

## Configuration

Configuration stored in `~/.mcp/google-calendar/`:

```
~/.mcp/google-calendar/
├── config.json          # Accounts and feature flags
├── oauth_client.json    # OAuth credentials
├── tokens/              # Per-account OAuth tokens
│   ├── work.json
│   └── personal.json
├── cache/               # Response caching
└── time_tracking.db     # SQLite database (time tracking + contacts)
```

### Enable Optional Modules

Edit `~/.mcp/google-calendar/config.json`:

```json
{
  "default_account": "work",
  "accounts": {
    "work": {"email": "user@company.com"},
    "personal": {"email": "user@gmail.com"}
  },
  "time_tracking": {
    "enabled": true
  },
  "contacts": {
    "enabled": true
  }
}
```

Or use CLI:

```bash
google-calendar-mcp enable-time-tracking
google-calendar-mcp enable-contacts
```

## Available Tools

### Core Calendar Tools

| Tool | Description |
|------|-------------|
| `list_events` | List events with time filters (`period`: today/week/month) |
| `create_event` | Create event with optional Meet link, attendees, recurrence |
| `get_event` | Get full event details including attendees |
| `update_event` | Update event; supports `scope` for recurring events |
| `delete_event` | Delete event; supports `scope` for recurring events |
| `search_events` | Free-text search across events |
| `get_freebusy` | Check availability for calendars |

### Reference Tools

| Tool | Description |
|------|-------------|
| `manage_calendars` | List/create/update/delete calendars |
| `list_colors` | Get available event colors |
| `manage_settings` | Get/set timezone, list accounts |

### Attendees Tools

| Tool | Description |
|------|-------------|
| `manage_attendees` | Add/remove/list attendees, resend invites |
| `respond_to_event` | RSVP to event invitations |

### Intelligence Tools

| Tool | Description |
|------|-------------|
| `batch_operations` | Execute multiple create/update/delete in one call |
| `find_meeting_slots` | Find available slots across calendars and timezones |
| `weekly_brief` | Generate weekly schedule summary with analytics |

### Time Tracking Tools

| Tool | Description |
|------|-------------|
| `time_tracking` | Batch operations for projects, phases, tasks, norms, config |
| `time_tracking_report` | Generate status, weekly, monthly, or custom reports |

### Contacts Tools

| Tool | Description |
|------|-------------|
| `contacts` | Batch operations for contacts, channels, assignments, roles |

## Time Tracking Module

The time tracking module parses calendar events to calculate billable and non-billable hours against monthly norms.

### Event Title Format

Events are parsed using configurable patterns. Default format:

```
[PROJECT] Description
[PROJECT:PHASE] Description
[PROJECT:PHASE:TASK] Description
```

Examples:
- `[CAYIB] Inception workshop preparation`
- `[SEDRA3:P2] Report drafting`
- `[EDD:DD:Analysis] Bank X assessment`

### Project Structure Levels

Projects support 1-3 level hierarchies:

| Level | Structure | Example |
|-------|-----------|---------|
| 1 | Project only | `[BFC]` |
| 2 | Project + Phase | `[CAYIB:P1]` |
| 3 | Project + Phase + Task | `[EDD:DD:Analysis]` |

### Operations

```python
# Initialize database
time_tracking(operations=[{"op": "init"}])

# Add project with phases
time_tracking(operations=[
    {"op": "project_add", "code": "CAYIB", "description": "Central Asia Youth in Business", 
     "is_billable": True, "structure_level": 2},
    {"op": "phase_add", "project_id": 1, "code": "P1", "description": "Inception"},
    {"op": "phase_add", "project_id": 1, "code": "P2", "description": "Implementation"}
])

# Set monthly norm
time_tracking(operations=[
    {"op": "norm_add", "year": 2025, "month": 1, "hours": 176}
])

# Get active projects (for event creation)
time_tracking(operations=[{"op": "project_list_active"}])

# Generate reports
time_tracking_report(report_type="status")  # Quick WTD/MTD summary
time_tracking_report(report_type="week")    # Weekly breakdown → Excel
time_tracking_report(report_type="month")   # Monthly breakdown → Excel
```

### Report Types

| Type | Output | Description |
|------|--------|-------------|
| `status` | JSON | Week-to-date and month-to-date progress with on-track % |
| `week` | JSON + Excel | Daily breakdown with project hours |
| `month` | JSON + Excel | Full month analysis with billable/non-billable split |
| `custom` | JSON + Excel | Custom date range via `start_date`/`end_date` |

## Contacts Module

The contacts module provides a CRM-like database for managing contacts across projects with multi-channel communication support.

### Database Schema

```
contacts                 # Core contact info
├── contact_channels     # Email, phone, Telegram, Teams, etc.
├── contact_projects     # Role assignments to projects
└── project_roles        # 19 standard consultant/client/donor roles
```

### Operations

```python
# Initialize contacts tables
contacts(operations=[{"op": "init"}])

# Add contact with channels
contacts(operations=[
    {"op": "contact_add", "first_name": "John", "last_name": "Smith",
     "organization": "ADB", "organization_type": "donor", "country": "Philippines"},
    {"op": "channel_add", "contact_id": 1, "channel_type": "email",
     "channel_value": "jsmith@adb.org", "is_primary": True},
    {"op": "channel_add", "contact_id": 1, "channel_type": "telegram_username",
     "channel_value": "johnsmith"}
])

# Assign to project
contacts(operations=[
    {"op": "assignment_add", "contact_id": 1, "project_id": 1, "role_code": "DO"}
])

# Search contacts (fuzzy matching)
contacts(operations=[{"op": "contact_search", "query": "John"}])

# Resolve contact from any identifier
contacts(operations=[{"op": "contact_resolve", "identifier": "@johnsmith"}])
contacts(operations=[{"op": "contact_resolve", "identifier": "jsmith@adb.org"}])
```

### Channel Types

| Type | Description |
|------|-------------|
| `email` | Email address |
| `phone` | Phone number with country code |
| `telegram_username` | Telegram @username |
| `telegram_chat_id` | Telegram numeric chat ID (for sending) |
| `telegram_id` | Telegram user ID |
| `teams_chat_id` | Microsoft Teams chat ID |
| `whatsapp` | WhatsApp number |
| `linkedin` | LinkedIn profile URL |
| `skype` | Skype username |

### Role Codes

Standard roles organized by category:

**Consultant**: TL (Team Leader), DTL (Deputy TL), SE (Senior Expert), JE (Junior Expert), NKE (National Expert), PM (Project Manager)

**Client**: CPM (Client PM), CFP (Client Focal Point), CC (Client Counterpart)

**Donor**: DO (Donor Officer), DPM (Donor PM), DF (Donor Focal)

**Partner**: PP (Partner PM), PC (Partner Contact), LB (Local Bank)

### Reports and Export

```python
# Summary report
contacts(operations=[{"op": "report", "report_type": "summary"}])

# Project team roster
contacts(operations=[{"op": "report", "report_type": "project_team", "project_id": 1}])

# Contacts by organization
contacts(operations=[{"op": "report", "report_type": "organization", "organization": "ADB"}])

# Export to Excel
contacts(operations=[{"op": "export_contacts"}])
contacts(operations=[{"op": "export_contacts", "filter_params": {"country": "Kyrgyzstan"}}])
contacts(operations=[{"op": "export_project_team", "project_id": 1}])
```

### Enrichment from Other Tools

The contacts module integrates with Telegram, Teams, and Gmail MCP servers:

```python
# Get enrichment suggestions for a contact
contacts(operations=[{"op": "suggest_enrichment", "contact_id": 1}])
# Returns instructions to find telegram_chat_id, teams_chat_id, phone from signatures

# Scan communication channels for new contacts
contacts(operations=[{"op": "suggest_new_contacts", "period": "month", "sources": ["telegram", "gmail"]}])
# Returns scan instructions for Claude to execute
```

### Activity Brief (contact_brief)

Generate a unified activity timeline across all communication channels for a contact. Returns fetch instructions for Claude to execute in parallel.

```python
# Get activity brief for contact
contacts(operations=[{"op": "contact_brief", "contact_id": 8, "days_back": 7, "days_forward": 7}])
```

**Parameters**:
- `contact_id` (required): Contact ID
- `days_back` (default 7): Lookback period for messages and past meetings
- `days_forward` (default 7): Lookahead period for upcoming calendar events

**Available Sources** (auto-detected based on contact channels):

| Source | Required Channel | Tool Used |
|--------|------------------|----------|
| Telegram | `telegram_chat_id` | `telegram:read_chat` |
| Teams | `teams_chat_id` | `teams:read_messages` |
| Gmail | `email` | `google-mail:find_context` |
| Calendar | `email` | `google-calendar:search_events` |

**Response Structure**:

```json
{
  "contact": {"id": 8, "display_name": "Alex Tsybko", "organization": "BFC"},
  "available_channels": {"email": [...], "telegram_chat_id": [...], "teams_chat_id": [...]},
  "available_sources": ["telegram", "teams", "gmail", "calendar"],
  "time_range": {"past": "7 days back (2025-12-13)", "future": "7 days forward"},
  "fetch_instructions": [
    {
      "source": "telegram",
      "priority": 1,
      "tool": "telegram:read_chat",
      "params": {"chat": 372068885, "limit": 70},
      "filter_hint": "Filter messages where date >= 2025-12-13"
    },
    // ... more instructions for teams, gmail, calendar
  ],
  "workflow": ["1. Execute all priority=1 fetch instructions in parallel", ...],
  "aggregation_hints": {
    "timeline_merge": "Sort all messages/emails by date descending",
    "highlight_unanswered": "Flag incoming messages without response within 24h"
  }
}
```

**Workflow for Claude**:

1. Call `contact_brief` to get fetch instructions
2. Execute all `priority=1` instructions in parallel
3. If any fail, try `priority=2` alternatives
4. Filter results by date range if tool doesn't support it natively
5. Aggregate into unified brief with sections:
   - Contact summary
   - Upcoming events (calendar)
   - Recent activity timeline (merged by date from all sources)
   - Past meetings
6. Highlight: last interaction date, next scheduled meeting, pending items

**Message Limits** (auto-scaled based on `days_back`):
- Telegram: `days_back * 10` (max 100)
- Teams: `days_back * 5` (max 50)
- Gmail: 20 emails via `find_context`
- Calendar: 20 events per direction (past/upcoming)

**Example Aggregated Output**:

```
## Alex Tsybko — Activity Brief (13-27 Dec 2025)

Contact: BFC, Ukraine | Preferred: email | Telegram: @alextsybko

### Upcoming Meetings
- 24 Dec 16:00 — CAYIB weekly team sync (14 attendees, Teams)

### Recent Activity Timeline
| Date | Channel | Direction | Summary |
|------|---------|-----------|-------|
| 20 Dec 09:46 | Telegram | ← | Координация встречи в отеле |
| 19 Dec 20:46 | Email | → | MFO scoring methodology на review |
| 19 Dec 15:36 | Teams | ← | "It works!" (MCP test) |
| 17 Dec 16:00 | Calendar | — | CAYIB team sync meeting |

### Summary Stats
- Telegram: 70 messages | Teams: 3 messages | Email: 13 in 11 threads
- Meetings: 1 past, 1 upcoming
```

## Multi-Account Usage

When user mentions calendar names ("личный календарь", "work calendar", "family"):

1. First call `manage_settings(action="list_accounts")` to see available accounts
2. Match user's description to account name
3. Pass `account="matched_name"` in subsequent calls

```python
# Wrong: assumes default account
list_events(period="today")

# Correct: explicit account selection
list_events(period="today", account="personal")
```

**Account vs Calendar**:
- **Account** = Google account (work@company.com, personal@gmail.com). Parameter: `account="work"`
- **Calendar** = Calendar within account (primary, holidays, family). Parameter: `calendar_id="holidays"`

## Examples

### Create Meeting with Attendees

```python
create_event(
    summary="Project Kickoff",
    start="2025-01-15T10:00:00",
    end="2025-01-15T11:30:00",
    attendees=["client@company.com", "team@bfc.com"],
    add_meet_link=True,
    account="work"
)
```

### Find Meeting Slots Across Timezones

```python
find_meeting_slots(
    duration_minutes=60,
    date_range_start="2025-01-20",
    date_range_end="2025-01-24",
    participant_timezones=["Asia/Bangkok", "Europe/Berlin"],
    working_hours_start=9,
    working_hours_end=17
)
```

### Update Recurring Event (All Instances)

```python
update_event(
    event_id="abc123",
    summary="Updated Weekly Standup",
    scope="all"  # Applies to entire series
)
```

### Move Event to Another Calendar

```python
# First, get calendar list
manage_calendars(action="list")

# Then move event
update_event(
    event_id="abc123",
    destination_calendar_id="calendar_id_from_list"
)
```

### Time Tracking Workflow

```python
# 1. Check current status
time_tracking_report(report_type="status")

# 2. See what projects are available
time_tracking(operations=[{"op": "project_list_active"}])

# 3. Create properly tagged event
create_event(
    summary="[CAYIB:P1] Inception workshop",
    start="2025-01-15T09:00:00",
    end="2025-01-15T17:00:00"
)

# 4. Generate weekly report
time_tracking_report(report_type="week")
```

## Development

### Setup Development Environment

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Lint code
ruff check src/
```

### Project Structure

```
src/google_calendar/
├── __init__.py
├── __main__.py          # CLI entry point
├── server.py            # FastMCP server definition
├── api/                 # Google Calendar API wrapper
├── cli/                 # Command-line interface
├── tools/
│   ├── crud/            # Core CRUD operations
│   ├── reference/       # Calendar, colors, settings
│   ├── attendees/       # Attendee management
│   ├── intelligence/    # Batch, slots, briefing
│   ├── time_tracking/   # Time tracking module
│   └── contacts/        # Contacts module
└── utils/
    ├── config.py        # Configuration management
    └── auth.py          # OAuth handling
```

### Adding New Tools

1. Create tool function with docstring (used for LLM instructions)
2. Register in `server.py` using `mcp.tool(function)`
3. Add tests in `tests/`

## License

MIT License. See [LICENSE](LICENSE) for details.

## Author

Dmytro Romanov

## Links

- Repository: https://github.com/DimaRmnv/G-calendar-mcp
- MCP Protocol: https://modelcontextprotocol.io/
- FastMCP: https://github.com/jlowin/fastmcp

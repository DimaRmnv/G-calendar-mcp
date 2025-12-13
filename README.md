# GCalendar MCP

A Model Context Protocol server that gives Claude direct access to your Google Calendar. Create events, check availability, find meeting slots across timezones, and get intelligent schedule analysis through natural conversation.

## Why This Tool

**Cross-timezone scheduling.** `find_meeting_slots` finds slots that work across multiple timezones. Specify participant timezones and working hours — get ranked slots with local times for everyone.

**One-shot meeting creation.** Create events with Google Meet links, attendees, reminders, and recurrence in a single command.

**Time tracking (optional).** Track billable hours, generate timesheet reports, monitor progress against monthly targets. Parse calendar events by project/phase/task codes.

**Weekly intelligence.** `weekly_brief` synthesizes your schedule: total hours, busiest day, free days, conflicts, large meetings.

**Multi-account support.** Switch between work and personal calendars mid-conversation. Each account has separate OAuth tokens.

**Batch operations.** Create, update, or delete multiple events in one request.

## Installation

### Prerequisites

- Python 3.10+
- Google Cloud project with Calendar API enabled
- OAuth 2.0 credentials (Desktop application type)

### Setup

```bash
git clone https://github.com/dmytroromanov/gcalendar-mcp.git
cd gcalendar-mcp
pip install -e .
python -m gcalendar_mcp auth
python -m gcalendar_mcp install
```

Restart Claude Desktop after installation.

### Google Cloud Configuration

1. [Google Cloud Console](https://console.cloud.google.com/) → Create or select project
2. APIs & Services → Library → Google Calendar API → Enable
3. APIs & Services → Credentials → Create Credentials → OAuth client ID → Desktop app
4. Download JSON file
5. Paste JSON content when `gcalendar-mcp auth` prompts

---

## Time Tracking (Optional Feature)

Track project hours, billable time, and generate timesheet reports based on calendar events. Disabled by default.

### Enable Time Tracking

```bash
# Enable the feature
python -m gcalendar_mcp time-tracking enable

# Initialize database with default projects
python -m gcalendar_mcp time-tracking init

# Restart Claude Desktop to load new tools
```

### Event Format

Events are parsed from summary using delimiter ` * ` or `:`:

| Structure Level | Format | Example |
|-----------------|--------|---------|
| Level 1 (full) | `PROJECT * PHASE * TASK * Description` | `ADB25 * UZ-Davr * BA * Review financial statements` |
| Level 2 (phase) | `PROJECT * PHASE * Description` | `BCH * AI * Review implementation options` |
| Level 3 (simple) | `PROJECT * Description` | `CSUM * Prepare MFO assessment` |

### Time Tracking Tools

| Tool | Purpose |
|------|---------|
| `time_tracking_status` | Quick WTD/MTD summary with on-track percentages |
| `time_tracking_report` | Full report with Excel export |
| `time_tracking_projects` | CRUD for projects (add/list/update/delete) |
| `time_tracking_phases` | CRUD for project phases |
| `time_tracking_tasks` | CRUD for task types |
| `time_tracking_norms` | Set monthly working hours norms |
| `time_tracking_exclusions` | Patterns to skip (Away, Lunch, etc.) |
| `time_tracking_config` | Settings: work_calendar, billable_target, base_location |
| `time_tracking_init` | Initialize database with defaults |

### Configuration

```
"Set my work calendar to dmytro.romanov@bfconsulting.com"
"Set billable target to 75 percent"
"Set base location to Bangkok"
```

Settings:
- `work_calendar`: Calendar ID to track (default: primary)
- `billable_target_type`: "percent" or "days"
- `billable_target_value`: Target number (e.g., 75 for 75%, or 15 for 15 days)
- `base_location`: Home city for context

### Reports

```
"Show my time tracking status"
"Generate timesheet report for this month"
"Create Excel report for last week"
```

Report metrics:
- Total hours worked vs norm
- Billable hours vs target
- On-track percentage (should be ~100% if keeping pace)
- Breakdown by project
- Events with parsing errors

### Default Projects

Initialization populates:
- **Billable (Level 1):** ADB25, CAYIB, EDD
- **Billable (Level 3):** UFSP, CSUM, SEDRA3, EFCF, AIYL-MN
- **Non-billable (Level 2):** BCH, BFC, BDU, BDU-TEN
- **Non-billable (Level 3):** MABI4, OPP, MAPS
- **Workday norms:** 2025 Thailand calendar
- **Exclusions:** Away, Lunch, Offline, Out of office

Customize with CRUD tools after initialization.

### CLI Commands

```bash
python -m gcalendar_mcp time-tracking enable      # Enable feature
python -m gcalendar_mcp time-tracking disable     # Disable feature
python -m gcalendar_mcp time-tracking status      # Show status
python -m gcalendar_mcp time-tracking init        # Create database with defaults
python -m gcalendar_mcp time-tracking init --no-defaults  # Empty database
```

### Data Storage

```
~/.mcp/gcalendar/
├── time_tracking.db     # SQLite database
├── reports/             # Generated Excel files
└── ...
```

---

## Calendar Tools

### list_events

List calendar events with time range filters.

```
"What's on my calendar today?"
"Show me this week's events"
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| calendar_id | `"primary"` | Calendar to query |
| period | `None` | Quick filter: `today`, `tomorrow`, `week`, `month` |
| time_min / time_max | `None` | ISO 8601 datetime range |
| query | `None` | Text search |
| max_results | `50` | 1-250 |

### create_event

Create calendar event with full parameter support.

```
"Schedule a meeting with john@example.com tomorrow at 2pm for 1 hour"
"Create a weekly standup every Monday at 9am with Meet link"
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| summary | required | Event title |
| start / end | required | Datetime or date for all-day |
| attendees | `None` | List of email addresses |
| add_meet_link | `False` | Generate Google Meet link |
| recurrence | `None` | RFC5545 RRULE |
| reminders_minutes | `None` | List: `[10, 60]` |

**Recurrence examples:**

| Pattern | Rule |
|---------|------|
| Daily for 5 days | `["RRULE:FREQ=DAILY;COUNT=5"]` |
| Every weekday | `["RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"]` |
| Monthly on 15th | `["RRULE:FREQ=MONTHLY;BYMONTHDAY=15"]` |

### get_event

Get full event details including attendees and Meet link.

### update_event

Modify existing event. For recurring events, use `scope="single"` or `scope="all"`.

### delete_event

Delete event. For recurring: `scope="single"` (this instance) or `scope="all"` (series).

### search_events

Full-text search across title, description, location, attendees.

### get_freebusy

Check availability across calendars for a time range.

### manage_attendees

Add, remove, list, or resend invitations. Actions: `list`, `add`, `remove`, `resend`.

### respond_to_event

RSVP to invitation: `accepted`, `declined`, `tentative`.

### batch_operations

Execute multiple create/update/delete operations in one request.

### find_meeting_slots

Find available times across calendars and timezones.

```
find_meeting_slots(
    duration_minutes=60,
    date_range_start="2025-01-15",
    date_range_end="2025-01-17",
    timezone="Asia/Bangkok",
    participant_timezones=["Europe/London"],
    working_hours_start=9,
    working_hours_end=17
)
```

Returns slots that work for all participant timezones within specified working hours.

### weekly_brief

Synthesized weekly overview: total hours, busiest day, free days, conflicts.

### Reference Tools

- `list_calendars`: Show all accessible calendars
- `list_colors`: Available event colors
- `get_settings`: User's timezone and preferences

---

## Multi-Account

```bash
python -m gcalendar_mcp auth        # → name it "work"
python -m gcalendar_mcp auth        # → name it "personal"
python -m gcalendar_mcp auth --list
python -m gcalendar_mcp auth --default work
```

Specify `account` parameter when needed:

```
"Show events from personal calendar"
```

---

## CLI Reference

```bash
# Account management
python -m gcalendar_mcp auth              # Add account
python -m gcalendar_mcp auth --list       # Show accounts
python -m gcalendar_mcp auth --default X  # Set default
python -m gcalendar_mcp auth --remove X   # Remove account

# Installation
python -m gcalendar_mcp install           # Install to Claude Desktop
python -m gcalendar_mcp install --force   # Reinstall
python -m gcalendar_mcp install --dev     # Dev mode
python -m gcalendar_mcp install --remove  # Uninstall

# Time tracking
python -m gcalendar_mcp time-tracking enable
python -m gcalendar_mcp time-tracking disable
python -m gcalendar_mcp time-tracking status
python -m gcalendar_mcp time-tracking init

# Debug
python -m gcalendar_mcp serve             # Run server directly
```

---

## Data Storage

```
~/.mcp/gcalendar/
├── config.json          # Account registry, feature flags
├── oauth_client.json    # Google OAuth credentials
├── time_tracking.db     # Time tracking database (if enabled)
├── reports/             # Generated Excel reports
├── tokens/
│   ├── work.json
│   └── personal.json
├── src/                 # Package (standalone mode)
└── venv/                # Virtual environment (standalone mode)
```

---

## Troubleshooting

**"Calendar API has not been used in project X"**
Enable Calendar API in Google Cloud Console.

**Server not appearing in Claude**
1. Check accounts: `python -m gcalendar_mcp auth --list`
2. Verify config: `cat ~/Library/Application\ Support/Claude/claude_desktop_config.json`
3. Restart Claude Desktop

**Time tracking tools not showing**
1. Enable: `python -m gcalendar_mcp time-tracking enable`
2. Restart Claude Desktop

**Token expired**
Re-run `python -m gcalendar_mcp auth` with same account name.

---

## License

MIT

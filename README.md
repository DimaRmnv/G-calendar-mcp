# GCalendar MCP

A Model Context Protocol server that gives Claude direct access to your Google Calendar. Create events, check availability, find meeting slots across timezones, and get intelligent schedule analysis through natural conversation.

## Why This Tool

**Cross-timezone scheduling.** `find_meeting_slots` finds slots that work across multiple timezones. Specify participant timezones and working hours — get ranked slots with local times for everyone. Essential for distributed teams.

**One-shot meeting creation.** Create events with Google Meet links, attendees, reminders, and recurrence in a single command. No context-switching to browser.

**Weekly intelligence.** `weekly_brief` synthesizes your schedule: total hours, busiest day, free days, conflicts, large meetings. Morning planning in one call.

**Multi-account support.** Switch between work and personal calendars mid-conversation. Each account has separate OAuth tokens.

**Batch operations.** Create, update, or delete multiple events in one request. Useful for bulk rescheduling or cleanup.

**Token-optimized.** `list_events` returns summary data; `get_event` fetches full details only when needed. Intelligence tools calculate locally, minimizing API calls.

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

## Tools

### list_events

List calendar events with time range filters.

```
"What's on my calendar today?"
"Show me this week's events"
"List meetings for next month"
```

| Parameter | Default | When to specify |
|-----------|---------|-----------------|
| calendar_id | `"primary"` | When accessing non-primary calendar |
| time_min | `None` | ISO 8601 datetime for range start |
| time_max | `None` | ISO 8601 datetime for range end |
| period | `None` | Quick filter: `today`, `tomorrow`, `yesterday`, `week`, `month`. Mutually exclusive with time_min/time_max |
| query | `None` | Text search across title, description, location |
| max_results | `50` | 1-250. Increase for comprehensive listing |
| private_extended_property | `None` | Filter by private extended properties (key=value) |
| shared_extended_property | `None` | Filter by shared extended properties |
| account | default | Only for non-default account |

**Returns:** Event summaries with id, summary, start, end, location, status, htmlLink, attendee count, hasConference flag.

---

### create_event

Create calendar event with full parameter support.

```
"Schedule a meeting with john@example.com tomorrow at 2pm for 1 hour"
"Create a weekly standup every Monday at 9am with Meet link"
"Add all-day event for December 25th"
```

| Parameter | Default | When to specify |
|-----------|---------|-----------------|
| summary | required | Event title |
| start | required | `'2025-01-15T10:00:00'` for timed, `'2025-01-15'` for all-day |
| end | required | End time. For all-day events, use next day (exclusive) |
| calendar_id | `"primary"` | For non-primary calendar |
| description | `None` | Notes, agenda, details |
| location | `None` | Physical location or URL |
| timezone | `None` | IANA timezone (e.g., `Asia/Bangkok`). Uses calendar default if omitted |
| attendees | `None` | List of email addresses to invite |
| add_meet_link | `False` | Set `True` to auto-generate Google Meet link |
| reminders_minutes | `None` | List: `[10, 60]` for 10min and 1hr reminders |
| recurrence | `None` | RFC5545 RRULE format (see examples below) |
| color_id | `None` | Event color. Use `list_colors` to see options |
| visibility | `None` | `public`, `private`, `confidential` |
| transparency | `None` | `opaque` (busy) or `transparent` (free) |
| extended_properties | `None` | `{"private": {"project": "X"}, "shared": {"client": "Y"}}` |
| send_updates | `"all"` | `all`, `externalOnly`, `none` for invite notifications |
| account | default | Only for non-default account |

**Recurrence examples (RFC5545 RRULE):**

| Pattern | Rule |
|---------|------|
| Daily for 5 days | `["RRULE:FREQ=DAILY;COUNT=5"]` |
| Every weekday | `["RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"]` |
| Every Monday and Wednesday | `["RRULE:FREQ=WEEKLY;BYDAY=MO,WE"]` |
| Monthly on 15th | `["RRULE:FREQ=MONTHLY;BYMONTHDAY=15"]` |
| Every 2 weeks on Friday | `["RRULE:FREQ=WEEKLY;INTERVAL=2;BYDAY=FR"]` |
| Until specific date | `["RRULE:FREQ=WEEKLY;BYDAY=MO;UNTIL=20250331T000000Z"]` |

**Returns:** Event ID, htmlLink, start, end, meetLink (if requested), attendee count, status.

---

### get_event

Get full event details by ID.

```
"Show me details of that meeting"
"Who's attending the sync?"
"What's the Meet link for tomorrow's call?"
```

| Parameter | Default | When to specify |
|-----------|---------|-----------------|
| event_id | required | From list_events or create_event results |
| calendar_id | `"primary"` | For non-primary calendar |
| account | default | Only for non-default account |

**Returns:** Full details including description, attendees with RSVP status (accepted/declined/tentative/needsAction), organizer, meetLink, reminders, recurrence, extendedProperties.

---

### update_event

Modify existing event. Only provided fields are updated.

```
"Move the meeting to 3pm"
"Add Sarah to tomorrow's sync"
"Update all instances of the recurring standup"
```

| Parameter | Default | When to specify |
|-----------|---------|-----------------|
| event_id | required | Event to update. For recurring: instance ID (e.g., `abc123_20250115T100000Z`) or master ID |
| calendar_id | `"primary"` | For non-primary calendar |
| scope | `"single"` | For recurring events: `single` (this instance), `all` (entire series) |
| summary | `None` | New title |
| start | `None` | New start time |
| end | `None` | New end time |
| description | `None` | New description |
| location | `None` | New location |
| timezone | `None` | Timezone for new times |
| attendees | `None` | **Replace** all attendees with this list |
| add_attendees | `None` | Add emails to existing attendees |
| remove_attendees | `None` | Remove emails from attendees |
| add_meet_link | `False` | Add Meet link if not present |
| reminders_minutes | `None` | New reminder settings |
| color_id | `None` | New color |
| visibility | `None` | New visibility |
| transparency | `None` | New transparency |
| extended_properties | `None` | Update extended properties |
| send_updates | `"all"` | Notification setting |
| account | default | Only for non-default account |

**Recurring events:** Use `scope` to control which instances are affected. `scope="single"` with master ID updates first upcoming instance. `scope="all"` updates entire series.

**Attendee options:** Use `attendees` to replace entire list, or `add_attendees`/`remove_attendees` for incremental changes.

---

### delete_event

Delete calendar event.

```
"Cancel tomorrow's meeting"
"Delete just this instance of the weekly sync"
"Delete all instances of the recurring standup"
```

| Parameter | Default | When to specify |
|-----------|---------|-----------------|
| event_id | required | Event to delete. For recurring: instance ID or master ID |
| calendar_id | `"primary"` | For non-primary calendar |
| scope | `"single"` | For recurring: `single` (this instance only) or `all` (entire series) |
| send_updates | `"all"` | Notify attendees: `all`, `externalOnly`, `none` |
| account | default | Only for non-default account |

**Recurring events:** `scope="single"` with instance ID deletes that occurrence. `scope="single"` with master ID deletes next upcoming instance. `scope="all"` deletes entire series.

---

### search_events

Full-text search across calendar events.

```
"Find all meetings with John"
"Search for events mentioning budget review"
"Find Zoom meetings from last month"
```

| Parameter | Default | When to specify |
|-----------|---------|-----------------|
| query | required | Search term — matches title, description, location, attendees |
| calendar_id | `"primary"` | For non-primary calendar |
| time_min | 1 year ago | Narrow search range |
| time_max | 1 year ahead | Narrow search range |
| max_results | `25` | 1-250 |
| account | default | Only for non-default account |

---

### get_freebusy

Check availability across calendars.

```
"Am I free tomorrow 2-4pm?"
"Check availability for the team next week"
```

| Parameter | Default | When to specify |
|-----------|---------|-----------------|
| time_min | required | Start of range to check |
| time_max | required | End of range |
| calendars | `["primary"]` | List of calendar IDs to check |
| timezone | `None` | Timezone for results |
| account | default | Only for non-default account |

**Returns:** Busy periods for each calendar. Empty periods = free time.

---

### list_calendars

List all accessible calendars.

```
"What calendars do I have?"
"Show my calendar list"
```

| Parameter | Default | When to specify |
|-----------|---------|-----------------|
| account | default | Only for non-default account |

**Returns:** Calendar ID, name, description, timezone, access role, primary flag.

---

### list_colors

Get available event colors.

```
"What colors can I use for events?"
```

| Parameter | Default | When to specify |
|-----------|---------|-----------------|
| account | default | Only for non-default account |

**Returns:** Color IDs with background/foreground hex values. Use color_id in create_event/update_event.

---

### get_settings

Get user's calendar settings.

```
"What's my calendar timezone?"
"Show my calendar settings"
```

| Parameter | Default | When to specify |
|-----------|---------|-----------------|
| account | default | Only for non-default account |

**Returns:** Timezone, locale, weekStart (0=Sunday, 1=Monday), format24HourTime, defaultEventLength.

---

### manage_attendees

Manage event attendees: add, remove, list, or resend invitations.

```
"Add john@example.com to the meeting"
"Remove Sarah from tomorrow's sync"
"Who's attending the planning session?"
"Resend the invitation to john@example.com"
```

| Parameter | Default | When to specify |
|-----------|---------|-----------------|
| event_id | required | Event to manage |
| action | required | `list`, `add`, `remove`, or `resend` |
| emails | `None` | List of emails for add/remove/resend |
| calendar_id | `"primary"` | For non-primary calendar |
| send_updates | `"all"` | Notification setting |
| account | default | Only for non-default account |

**Actions:**
- `list`: Returns attendees with RSVP status, grouped by status
- `add`: Invites new attendees (skips already-invited)
- `remove`: Removes attendees from event
- `resend`: Re-sends invitation to specified attendees

**Note:** You can only manage attendees for events you organize.

---

### respond_to_event

Respond to event invitation (accept, decline, tentative).

```
"Accept the meeting from Alex"
"Decline tomorrow's call"
"Mark the workshop as tentative"
```

| Parameter | Default | When to specify |
|-----------|---------|-----------------|
| event_id | required | Event to respond to |
| response | required | `accepted`, `declined`, or `tentative` |
| calendar_id | `"primary"` | For non-primary calendar |
| account | default | Only for non-default account |

---

### batch_operations

Execute multiple calendar operations in one request.

```
"Create three meetings for next week"
"Delete all events from the test calendar"
"Update all project meetings to add Meet links"
```

| Parameter | Default | When to specify |
|-----------|---------|-----------------|
| operations | required | List of operations (see format below) |
| calendar_id | `"primary"` | Default for all operations |
| send_updates | `"all"` | Default for all operations |
| account | default | Only for non-default account |

**Operation format:**
```json
[
  {"action": "create", "summary": "Meeting 1", "start": "2025-01-15T10:00:00", "end": "2025-01-15T11:00:00"},
  {"action": "update", "event_id": "abc123", "summary": "Updated Title"},
  {"action": "delete", "event_id": "def456"}
]
```

**Returns:** total, succeeded, failed counts with per-operation results. Failures don't stop other operations.

---

### find_meeting_slots

Find available meeting times across calendars and timezones.

```
"Find a 30-minute slot for a call with London next week"
"When can I meet with the team for 1 hour?"
"Find available times for a morning meeting"
```

| Parameter | Default | When to specify |
|-----------|---------|-----------------|
| duration_minutes | required | Meeting length |
| date_range_start | required | Start of search range (date or datetime) |
| date_range_end | required | End of search range |
| calendars | `["primary"]` | Calendars to check for conflicts |
| working_hours_start | `9` | Start of working hours (0-23) |
| working_hours_end | `18` | End of working hours (0-23) |
| timezone | calendar default | Primary timezone for results |
| participant_timezones | `None` | List of IANA timezones. Slots will be within working hours for ALL |
| max_slots | `10` | Maximum slots to return |
| account | default | Only for non-default account |

**Example:** Find 1-hour slots for a meeting with someone in London:
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

**Returns:** Available slots with start/end in primary timezone plus start_times dict showing local time in each participant timezone. Skips weekends automatically.

---

### weekly_brief

Synthesized weekly schedule overview with analysis.

```
"What's my week look like?"
"Give me a weekly brief"
"Summarize next week's schedule"
```

| Parameter | Default | When to specify |
|-----------|---------|-----------------|
| start_date | current Monday | Week to analyze (date format) |
| calendar_id | `"primary"` | For non-primary calendar |
| timezone | calendar default | Display timezone |
| account | default | Only for non-default account |

**Returns:**
- **Summary:** total_events, total_hours, busiest_day, free_days
- **By day:** Events per day with daily hour totals
- **Highlights:** All-day events, large meetings (5+ attendees)
- **Conflicts:** Overlapping events detected

---

## Multi-Account

```bash
python -m gcalendar_mcp auth        # → name it "work"
python -m gcalendar_mcp auth        # → name it "personal"
python -m gcalendar_mcp auth --list
python -m gcalendar_mcp auth --default work
```

First account becomes default. Specify account explicitly when needed:

```
"Show events from personal calendar"
"Create meeting using work account"
```

## CLI Reference

```bash
# Account management
python -m gcalendar_mcp auth              # Add account (interactive)
python -m gcalendar_mcp auth --list       # Show all accounts
python -m gcalendar_mcp auth --default X  # Set default account
python -m gcalendar_mcp auth --remove X   # Remove account

# Installation
python -m gcalendar_mcp install           # Standalone install to ~/.mcp/gcalendar/
python -m gcalendar_mcp install --force   # Reinstall after code changes
python -m gcalendar_mcp install --dev     # Dev mode (uses current directory)
python -m gcalendar_mcp install --remove  # Remove from Claude Desktop

# Debug
python -m gcalendar_mcp serve             # Run server directly
```

## Data Storage

```
~/.mcp/gcalendar/
├── config.json          # Account registry, default account
├── oauth_client.json    # Google OAuth credentials
├── tokens/
│   ├── work.json        # Per-account tokens
│   └── personal.json
├── src/                 # Package (standalone mode)
└── venv/                # Virtual environment (standalone mode)
```

## Troubleshooting

**"Calendar API has not been used in project X"**
Enable Calendar API: Google Cloud Console → APIs & Services → Library → Google Calendar API → Enable

**Server not appearing in Claude**
1. Check accounts: `python -m gcalendar_mcp auth --list`
2. Verify config: `cat ~/Library/Application\ Support/Claude/claude_desktop_config.json`
3. Restart Claude Desktop completely

**Token expired**
Re-run `python -m gcalendar_mcp auth`, use same account name to refresh.

**Test server manually**
```bash
~/.mcp/gcalendar/venv/bin/python -m gcalendar_mcp.server
```

## License

MIT

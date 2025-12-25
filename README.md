# Google Calendar MCP Server

MCP (Model Context Protocol) server for Google Calendar integration with Claude. Provides calendar management, time tracking, contacts CRM, and project management.

## Features

**Core Calendar**
- Full CRUD operations for events
- Recurring event support with scope control
- Attendee management with RSVP tracking
- Free/busy queries and meeting slot finder
- Weekly briefing with analytics

**Time Tracking**
- Project/phase/task hierarchy with billable flags
- Monthly hour norms and progress tracking
- Calendar event parsing (`PROJECT * PHASE * Description`)
- Excel report generation with download URLs

**Contacts CRM**
- Contact database with multi-channel support (email, Telegram, Teams, phone)
- Project role assignments (19 standard roles)
- Organization management with types (donor, bank, mfi, government, etc.)
- Fuzzy search and intelligent contact resolution
- Excel export with download URLs

**Organizations**
- Full CRUD for organizations
- Link organizations to projects with roles
- Organization types: donor, dfi, bank, mfi, nbfi, government, regulator, client, vendor, consulting, ngo, association, training_provider, partner, other

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Claude    │────▶│  MCP Server │────▶│  PostgreSQL │
│   Desktop   │     │  (FastAPI)  │     │  (shared)   │
└─────────────┘     └─────────────┘     └─────────────┘
                           │
                           ▼
                    ┌─────────────┐
                    │   Google    │
                    │ Calendar API│
                    └─────────────┘
```

## Deployment

### Cloud (Docker + GitHub Actions)

```bash
# Clone
git clone https://github.com/DimaRmnv/G-calendar-mcp.git
cd G-calendar-mcp

# Configure
cp .env.example .env
# Edit .env with your credentials

# Deploy (auto via GitHub Actions on push to main)
git push origin main
```

### Environment Variables

```bash
# PostgreSQL
POSTGRES_HOST=shared-postgres
POSTGRES_PORT=5432
POSTGRES_USER=travel
POSTGRES_PASSWORD=your_password
POSTGRES_DB=google_calendar_mcp

# API Security
GCAL_MCP_API_KEY=your_api_key

# OAuth
GCAL_MCP_OAUTH_CLIENT_ID=your_client_id
GCAL_MCP_OAUTH_CLIENT_SECRET=your_secret

# Export URLs
EXPORT_BASE_URL=http://your-server:8005
```

### Local Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Event Format

Events are parsed using `PROJECT * PHASE * TASK * Description` format:

| Structure Level | Format | Example |
|-----------------|--------|---------|
| 1 | `PROJECT * Description` | `AIYL-MN * Client meeting` |
| 2 | `PROJECT * PHASE * Description` | `BCH * AI * Research automation` |
| 3 | `PROJECT * PHASE * TASK * Description` | `CAYIB * KG-BAILYK * 1.1 * Workshop prep` |

## Tools

### Calendar
| Tool | Description |
|------|-------------|
| `list_events` | List events (period: today/week/month) |
| `create_event` | Create event with Meet link, attendees |
| `update_event` | Update event; scope for recurring |
| `delete_event` | Delete event |
| `search_events` | Free-text search |

### Time Tracking
| Tool | Description |
|------|-------------|
| `projects_manage` | CRUD for projects, phases, tasks, norms, organizations |
| `projects_report` | Generate status/week/month reports → Excel |

### Contacts
| Tool | Description |
|------|-------------|
| `contacts` | CRUD for contacts, channels, assignments |

## Reports

Reports generate Excel files with temporary download URLs (1 hour TTL):

```python
# Generate weekly report
projects_report(report_type="week")
# Returns: {"download_url": "http://server/export/uuid", "expires_in": "1 hour"}

# Export contacts
contacts(operations=[{"op": "export_contacts"}])
# Returns: {"download_url": "http://server/export/uuid"}
```

## Project Roles

| Category | Roles |
|----------|-------|
| Consultant | TL, DTL, KE, NKE, PM, BSM, JE, LA, INT |
| Client | CD, CPM, PIU, CP, BEN |
| Donor | DO, DPM, TA |
| Partner | PC, SUB |

## Organization Types

- **Funding**: donor, dfi
- **Financial**: bank, mfi, nbfi
- **Public**: government, regulator
- **Private**: client, vendor, consulting
- **Non-profit**: ngo, association, training_provider
- **Other**: partner, other

## Project Structure

```
src/google_calendar/
├── server.py           # FastAPI + MCP server
├── export_router.py    # Excel download endpoint
├── oauth_server.py     # OAuth flow
├── api/                # Google Calendar API
├── db/
│   ├── connection.py   # PostgreSQL connection pool
│   └── schema.sql      # Database schema
└── tools/
    ├── contacts/       # Contacts CRM
    ├── projects/       # Time tracking
    └── intelligence/   # Weekly brief
```

## License

MIT License

## Author

Dmytro Romanov

## Links

- Repository: https://github.com/DimaRmnv/G-calendar-mcp
- MCP Protocol: https://modelcontextprotocol.io/

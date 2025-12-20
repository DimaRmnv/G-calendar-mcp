"""
Contacts management module.

Extends time_tracking.db with contacts, channels, and project assignments.
"""

from google_calendar.tools.contacts.manage import contacts
from google_calendar.tools.contacts.lookup import (
    resolve_contact,
    resolve_multiple,
    get_preferred_channel,
    contact_brief,
)
from google_calendar.tools.contacts.report import (
    contacts_report,
    export_contacts_excel,
    export_project_team_excel,
)

__all__ = [
    "contacts",
    "resolve_contact",
    "resolve_multiple", 
    "get_preferred_channel",
    "contact_brief",
    "contacts_report",
    "export_contacts_excel",
    "export_project_team_excel",
]

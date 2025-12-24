"""
attendees tool.

Unified tool for managing event attendees and responding to invitations.
Replaces: manage_attendees, respond_to_event
"""

from typing import Optional, Literal

from google_calendar.api.events import get_event, update_event
from google_calendar.api.client import get_authorized_email


def attendees(
    action: Literal["list", "add", "remove", "resend", "respond"],
    event_id: str,
    calendar_id: str = "primary",
    # add/remove/resend
    emails: Optional[list[str]] = None,
    # respond
    response: Optional[str] = None,
    comment: Optional[str] = None,
    # common
    send_updates: str = "all",
    account: Optional[str] = None,
) -> dict:
    """
    Manage event attendees or respond to invitations.

    IMPORTANT - ACCOUNT SELECTION:
    When user mentions "личный календарь", "personal", "рабочий", "work", etc.:
    1. FIRST call calendars(action="list_accounts") to see available accounts
    2. Match user's description to account name (e.g., "личный" → "personal")
    3. Pass account="personal" (or matched name) to this function
    Do NOT use default account when user specifies a calendar name!

    Args:
        action: One of:
            ORGANIZER ACTIONS (for events you organize):
            - 'list': List current attendees with RSVP status
            - 'add': Add new attendees (requires emails)
            - 'remove': Remove attendees (requires emails)
            - 'resend': Resend invitation to specified attendees (requires emails)

            ATTENDEE ACTION (for events you're invited to):
            - 'respond': Respond to an invitation (requires response)

        event_id: Event ID to modify/respond to
        calendar_id: Calendar ID (use 'primary' for main calendar)

        ORGANIZER PARAMETERS:
        emails: List of email addresses (required for add/remove/resend)

        RESPOND PARAMETERS:
        response: Your response - one of:
            - 'accepted': Accept the invitation
            - 'declined': Decline the invitation
            - 'tentative': Tentatively accept
        comment: Optional comment visible to the organizer

        COMMON PARAMETERS:
        send_updates: Notification setting:
            - 'all': Notify all attendees (default)
            - 'externalOnly': Notify only non-Google Calendar users
            - 'none': No notifications
        account: Account name (uses default if not specified)

    Returns:
        For action='list':
            - attendees: List with email, displayName, responseStatus, organizer, optional, comment
            - total: Total attendee count
            - by_status: Count by response status
            - event_id: Event ID

        For action='add':
            - added: Count of added attendees
            - emails_requested: Requested emails
            - total: Total attendee count

        For action='remove':
            - removed: Count of removed attendees
            - emails_requested: Requested emails
            - total: Total attendee count

        For action='resend':
            - resent: Count of resent invitations
            - emails_requested: Requested emails
            - emails_found: Actually resent emails

        For action='respond':
            - event_id: Event ID
            - response: Your response status
            - event_summary: Event title
            - organizer: Organizer email
            - comment: Your comment (if provided)

    Response status values:
        - needsAction: Has not responded
        - accepted: Accepted invitation
        - declined: Declined invitation
        - tentative: Tentatively accepted

    Examples:
        List attendees: action="list", event_id="abc123"
        Add attendee: action="add", event_id="abc123", emails=["john@example.com"]
        Remove attendee: action="remove", event_id="abc123", emails=["john@example.com"]
        Resend invite: action="resend", event_id="abc123", emails=["john@example.com"]
        Accept invite: action="respond", event_id="abc123", response="accepted"
        Decline with note: action="respond", event_id="abc123", response="declined", comment="I have a conflict"

    Note:
    - For list/add/remove/resend: You must be the event organizer
    - For respond: You must be an attendee of the event
    - For recurring events, this affects the specific instance
    """
    if action == "list":
        return _list_attendees(event_id, calendar_id, account)

    elif action == "add":
        if not emails:
            raise ValueError("emails parameter required for 'add' action")
        return _add_attendees(event_id, emails, calendar_id, send_updates, account)

    elif action == "remove":
        if not emails:
            raise ValueError("emails parameter required for 'remove' action")
        return _remove_attendees(event_id, emails, calendar_id, send_updates, account)

    elif action == "resend":
        if not emails:
            raise ValueError("emails parameter required for 'resend' action")
        return _resend_invites(event_id, emails, calendar_id, send_updates, account)

    elif action == "respond":
        if not response:
            raise ValueError("response parameter required for 'respond' action")
        return _respond_to_event(event_id, response, comment, calendar_id, account)

    else:
        valid_actions = "list, add, remove, resend, respond"
        raise ValueError(f"Invalid action: {action}. Use one of: {valid_actions}")


def _list_attendees(
    event_id: str,
    calendar_id: str,
    account: Optional[str],
) -> dict:
    """List current attendees with RSVP status."""
    event = get_event(event_id, account=account, calendar_id=calendar_id)
    current_attendees = event.get("attendees", [])

    formatted = []
    for att in current_attendees:
        formatted.append({
            "email": att.get("email"),
            "displayName": att.get("displayName"),
            "responseStatus": att.get("responseStatus", "needsAction"),
            "organizer": att.get("organizer", False),
            "optional": att.get("optional", False),
            "comment": att.get("comment"),
        })

    # Group by status for summary
    by_status = {}
    for att in formatted:
        status = att["responseStatus"]
        by_status[status] = by_status.get(status, 0) + 1

    return {
        "action": "list",
        "attendees": formatted,
        "total": len(formatted),
        "by_status": by_status,
        "event_id": event_id,
    }


def _add_attendees(
    event_id: str,
    emails: list[str],
    calendar_id: str,
    send_updates: str,
    account: Optional[str],
) -> dict:
    """Add new attendees to an event."""
    event = get_event(event_id, account=account, calendar_id=calendar_id)
    current_attendees = event.get("attendees", [])

    existing_emails = {att.get("email", "").lower() for att in current_attendees}

    added_count = 0
    new_attendees = list(current_attendees)

    for email in emails:
        if email.lower() not in existing_emails:
            new_attendees.append({"email": email})
            added_count += 1

    if added_count > 0:
        update_event(
            event_id=event_id,
            calendar_id=calendar_id,
            attendees=new_attendees,
            send_updates=send_updates,
            account=account,
        )

    return {
        "action": "add",
        "added": added_count,
        "emails_requested": emails,
        "total": len(new_attendees),
        "event_id": event_id,
    }


def _remove_attendees(
    event_id: str,
    emails: list[str],
    calendar_id: str,
    send_updates: str,
    account: Optional[str],
) -> dict:
    """Remove attendees from an event."""
    event = get_event(event_id, account=account, calendar_id=calendar_id)
    current_attendees = event.get("attendees", [])

    remove_set = {e.lower() for e in emails}

    new_attendees = [
        att for att in current_attendees
        if att.get("email", "").lower() not in remove_set
    ]

    removed_count = len(current_attendees) - len(new_attendees)

    if removed_count > 0:
        update_event(
            event_id=event_id,
            calendar_id=calendar_id,
            attendees=new_attendees,
            send_updates=send_updates,
            account=account,
        )

    return {
        "action": "remove",
        "removed": removed_count,
        "emails_requested": emails,
        "total": len(new_attendees),
        "event_id": event_id,
    }


def _resend_invites(
    event_id: str,
    emails: list[str],
    calendar_id: str,
    send_updates: str,
    account: Optional[str],
) -> dict:
    """Resend invitation to specified attendees."""
    event = get_event(event_id, account=account, calendar_id=calendar_id)
    current_attendees = event.get("attendees", [])

    resend_set = {e.lower() for e in emails}

    # Find attendees to resend to (must already exist)
    attendees_to_resend = []
    other_attendees = []

    for att in current_attendees:
        if att.get("email", "").lower() in resend_set:
            attendees_to_resend.append(att)
        else:
            other_attendees.append(att)

    resent_count = len(attendees_to_resend)

    if resent_count > 0:
        # First update: remove the attendees (no notification)
        update_event(
            event_id=event_id,
            calendar_id=calendar_id,
            attendees=other_attendees,
            send_updates="none",
            account=account,
        )

        # Second update: re-add them (with notification)
        final_attendees = other_attendees + attendees_to_resend
        update_event(
            event_id=event_id,
            calendar_id=calendar_id,
            attendees=final_attendees,
            send_updates=send_updates,
            account=account,
        )

    return {
        "action": "resend",
        "resent": resent_count,
        "emails_requested": emails,
        "emails_found": [att["email"] for att in attendees_to_resend],
        "total": len(current_attendees),
        "event_id": event_id,
    }


def _respond_to_event(
    event_id: str,
    response: str,
    comment: Optional[str],
    calendar_id: str,
    account: Optional[str],
) -> dict:
    """Respond to an event invitation."""
    valid_responses = {"accepted", "declined", "tentative"}
    if response not in valid_responses:
        raise ValueError(f"Invalid response: {response}. Use one of: {', '.join(valid_responses)}")

    # Get current user's email
    user_email = get_authorized_email(account)
    if not user_email:
        raise ValueError("Could not determine user email. Ensure account is authorized.")

    # Fetch event
    event = get_event(event_id, account=account, calendar_id=calendar_id)
    event_attendees = event.get("attendees", [])

    # Find self in attendees
    user_email_lower = user_email.lower()
    self_found = False
    updated_attendees = []

    for att in event_attendees:
        att_email = att.get("email", "").lower()
        if att_email == user_email_lower or att.get("self"):
            # Update self's response
            att["responseStatus"] = response
            if comment:
                att["comment"] = comment
            self_found = True
        updated_attendees.append(att)

    if not self_found:
        raise ValueError(
            f"You ({user_email}) are not an attendee of this event. "
            "You can only respond to events you've been invited to."
        )

    # Update event with new response
    update_event(
        event_id=event_id,
        calendar_id=calendar_id,
        attendees=updated_attendees,
        send_updates="all",  # Notify organizer of response
        account=account,
    )

    # Get organizer info
    organizer = event.get("organizer", {})

    return {
        "action": "respond",
        "event_id": event_id,
        "response": response,
        "event_summary": event.get("summary", "(No title)"),
        "organizer": organizer.get("email"),
        "comment": comment,
    }

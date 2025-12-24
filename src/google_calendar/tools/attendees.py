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
    """Manage event attendees or respond to meeting invitations.

    SKILL REQUIRED: Read calendar-manager skill for participant formatting.

    PREREQUISITE: To add attendees by name, first resolve via contacts tool:
        contacts(operations=[{"op": "contact_resolve", "identifier": "Name"}]) → get email
        OR contacts(operations=[{"op": "project_team", "project_id": X}]) → get all team emails

    ACCOUNT SELECTION:
    Pass account= if event is in non-default calendar.

    Actions (all require event_id):
        ORGANIZER (you created the event):
        - list: Current attendees with RSVP status
        - add: Add attendees. Requires emails[]
        - remove: Remove attendees. Requires emails[]
        - resend: Resend invitation. Requires emails[]

        ATTENDEE (you're invited):
        - respond: Accept/decline/tentative. Requires response

    Key params:
        emails: List of email addresses from contacts lookup
        response: 'accepted' | 'declined' | 'tentative'
        comment: Optional note to organizer
        send_updates: 'all' (default) | 'externalOnly' | 'none'
        account: Required if event in non-default calendar

    Note: For recurring events, affects specific instance only.

    Examples:
        attendees(action="add", event_id="abc", emails=["a.azimbaev@aiylbank.kg"], account="work")
        attendees(action="respond", event_id="abc", response="accepted")
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

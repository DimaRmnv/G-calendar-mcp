"""
manage_attendees tool.

Add, remove, list, or resend invites for event attendees.
"""

from typing import Optional, Literal

from google_calendar.api.events import get_event, update_event


def manage_attendees(
    event_id: str,
    action: Literal["list", "add", "remove", "resend"],
    emails: Optional[list[str]] = None,
    calendar_id: str = "primary",
    send_updates: str = "all",
    account: Optional[str] = None,
) -> dict:
    """
    Manage attendees for an event you organize.

    IMPORTANT - ACCOUNT SELECTION:
    When user mentions "личный календарь", "personal", "рабочий", "work", etc.:
    1. FIRST call manage_settings(action="list_accounts") to see available accounts
    2. Match user's description to account name (e.g., "личный" → "personal")
    3. Pass account="personal" (or matched name) to this function
    Do NOT use default account when user specifies a calendar name!

    Args:
        event_id: Event ID to modify
        action: One of:
            - 'list': List current attendees with RSVP status
            - 'add': Add new attendees (requires emails)
            - 'remove': Remove attendees (requires emails)
            - 'resend': Resend invitation to specified attendees (requires emails)
        emails: List of email addresses (required for add/remove/resend)
        calendar_id: Calendar ID (use 'primary' for the main calendar)
        send_updates: Notification setting:
            - 'all': Notify all attendees (default)
            - 'externalOnly': Notify only non-Google Calendar users
            - 'none': No notifications
        account: Account name (uses default if not specified)
    
    Returns:
        Dictionary with:
        - action: Action performed
        - attendees: List of attendees (for 'list' action)
        - added/removed/resent: Count affected (for add/remove/resend)
        - total: Total attendee count
        - event_id: Event ID
    
    Response status values for 'list':
        - needsAction: Has not responded
        - accepted: Accepted invitation
        - declined: Declined invitation
        - tentative: Tentatively accepted
    
    Note: You can only manage attendees for events where you are the organizer.
    """
    # Fetch current event
    event = get_event(event_id, account=account, calendar_id=calendar_id)
    current_attendees = event.get("attendees", [])
    
    if action == "list":
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
    
    elif action == "add":
        if not emails:
            raise ValueError("emails parameter required for 'add' action")
        
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
    
    elif action == "remove":
        if not emails:
            raise ValueError("emails parameter required for 'remove' action")
        
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
    
    elif action == "resend":
        if not emails:
            raise ValueError("emails parameter required for 'resend' action")
        
        # Resend works by removing and re-adding attendees
        # This triggers a new invitation email
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
    
    else:
        raise ValueError(f"Invalid action: {action}. Use 'list', 'add', 'remove', or 'resend'.")

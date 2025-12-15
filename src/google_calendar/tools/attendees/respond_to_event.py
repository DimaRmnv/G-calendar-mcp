"""
respond_to_event tool.

Accept, decline, or tentatively accept event invitations.
"""

from typing import Optional

from google_calendar.api.events import get_event, update_event
from google_calendar.api.client import get_authorized_email


def respond_to_event(
    event_id: str,
    response: str,
    comment: Optional[str] = None,
    calendar_id: str = "primary",
    account: Optional[str] = None,
) -> dict:
    """
    Respond to an event invitation.
    
    Args:
        event_id: Event ID to respond to
        response: Your response - one of:
            - 'accepted': Accept the invitation
            - 'declined': Decline the invitation
            - 'tentative': Tentatively accept
        comment: Optional comment visible to the organizer
        calendar_id: Calendar ID (use 'primary' for the main calendar)
        account: Account name (uses default if not specified)
    
    Returns:
        Dictionary with:
        - event_id: Event ID
        - response: Your response status
        - event_summary: Event title
        - organizer: Event organizer email
    
    Use this tool to RSVP to meetings and events you've been invited to.
    The organizer will be notified of your response.
    
    Note: For recurring events, this responds to the specific instance.
    To respond to all instances, use the recurring event's base ID.
    """
    valid_responses = {"accepted", "declined", "tentative"}
    if response not in valid_responses:
        raise ValueError(f"Invalid response: {response}. Use one of: {', '.join(valid_responses)}")
    
    # Get current user's email
    user_email = get_authorized_email(account)
    if not user_email:
        raise ValueError("Could not determine user email. Ensure account is authorized.")
    
    # Fetch event
    event = get_event(event_id, account=account, calendar_id=calendar_id)
    attendees = event.get("attendees", [])
    
    # Find self in attendees
    user_email_lower = user_email.lower()
    self_found = False
    updated_attendees = []
    
    for att in attendees:
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
        "event_id": event_id,
        "response": response,
        "event_summary": event.get("summary", "(No title)"),
        "organizer": organizer.get("email"),
        "comment": comment,
    }

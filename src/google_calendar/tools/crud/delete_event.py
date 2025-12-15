"""
delete_event tool.

Delete calendar event with support for recurring event instances.
"""

from typing import Optional, Literal

from google_calendar.api.events import (
    delete_event as api_delete_event,
    get_event as api_get_event,
    get_recurring_instances,
    is_recurring_instance,
)


def delete_event(
    event_id: str,
    calendar_id: str = "primary",
    scope: Literal["single", "all"] = "single",
    send_updates: str = "all",
    account: Optional[str] = None,
) -> dict:
    """
    Delete a calendar event.

    IMPORTANT - ACCOUNT SELECTION:
    When user mentions "личный календарь", "personal", "рабочий", "work", etc.:
    1. FIRST call manage_settings(action="list_accounts") to see available accounts
    2. Match user's description to account name (e.g., "личный" → "personal")
    3. Pass account="personal" (or matched name) to this function
    Do NOT use default account when user specifies a calendar name!

    Args:
        event_id: Event ID to delete. For recurring events, can be either:
            - Instance ID (e.g., "abc123_20250115T100000Z") for specific occurrence
            - Master ID for the recurring series
        calendar_id: Calendar ID (use 'primary' for the main calendar)
        scope: How to apply deletion for recurring events:
            - 'single': Delete only this instance (default). Creates an exception in the series.
            - 'all': Delete entire recurring series (all past and future instances).
            For non-recurring events, this parameter is ignored.
        send_updates: Whether to send cancellation notifications:
            - 'all': Send to all attendees
            - 'externalOnly': Send only to non-Google Calendar attendees
            - 'none': Don't send notifications
        account: Account name (uses default if not specified)
    
    Returns:
        Dictionary with:
        - deleted: True if successfully deleted
        - event_id: ID of deleted event
        - scope_applied: Which scope was actually applied
        - send_updates: Notification setting used
    
    For recurring events:
    - scope='single' with instance ID: Deletes that specific occurrence
    - scope='single' with master ID: Deletes next upcoming instance only
    - scope='all' with any ID: Deletes entire series
    
    This action cannot be undone. Use send_updates='none' to delete without notifying attendees.
    """
    # Determine if this is a recurring event and resolve the target
    current_event = api_get_event(event_id, account=account, calendar_id=calendar_id)
    is_recurring = "recurrence" in current_event or current_event.get("recurringEventId")
    
    target_event_id = event_id
    scope_applied = "single"
    
    if is_recurring:
        if scope == "all":
            # Delete entire series - need master event ID
            if current_event.get("recurringEventId"):
                # This is an instance, get master
                target_event_id = current_event["recurringEventId"]
            # else: already master
            scope_applied = "all"
            
        else:  # scope == "single"
            if is_recurring_instance(event_id):
                # Already have instance ID
                target_event_id = event_id
            else:
                # Master ID provided - get first upcoming instance to delete
                from datetime import datetime
                instances = get_recurring_instances(
                    event_id,
                    account=account,
                    calendar_id=calendar_id,
                    time_min=datetime.now().isoformat(),
                    max_results=1
                )
                if instances:
                    target_event_id = instances[0]["id"]
                else:
                    # No upcoming instances - delete master (effectively deletes series)
                    target_event_id = event_id
                    scope_applied = "all"
            scope_applied = "single"
    
    # Execute deletion
    api_delete_event(
        event_id=target_event_id,
        calendar_id=calendar_id,
        send_updates=send_updates,
        account=account,
    )
    
    return {
        "deleted": True,
        "event_id": target_event_id,
        "original_event_id": event_id if event_id != target_event_id else None,
        "scope_applied": scope_applied,
        "is_recurring": is_recurring,
        "send_updates": send_updates,
    }

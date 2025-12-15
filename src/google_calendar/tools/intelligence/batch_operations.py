"""
batch_operations tool.

Bulk create, update, or delete calendar events.
"""

from typing import Optional

from google_calendar.api.events import (
    create_event as api_create_event,
    update_event as api_update_event,
    delete_event as api_delete_event,
)


def batch_operations(
    operations: list[dict],
    calendar_id: str = "primary",
    send_updates: str = "all",
    account: Optional[str] = None,
    timezone: Optional[str] = None,
) -> dict:
    """
    Execute multiple calendar operations in batch.

    IMPORTANT - ACCOUNT SELECTION:
    When user mentions "личный календарь", "personal", "рабочий", "work", etc.:
    1. FIRST call manage_settings(action="list_accounts") to see available accounts
    2. Match user's description to account name (e.g., "личный" → "personal")
    3. Pass account="personal" (or matched name) to this function
    Do NOT use default account when user specifies a calendar name!

    Args:
        operations: List of operations, each with:
            - action: 'create', 'update', or 'delete'
            - For create: summary, start, end, and optional fields (description, location, attendees, timezone, etc.)
            - For update: event_id and fields to update
            - For delete: event_id
        calendar_id: Calendar ID for all operations (use 'primary' for main calendar)
        send_updates: Notification setting for all operations:
            - 'all': Notify all attendees
            - 'externalOnly': Notify only non-Google Calendar users
            - 'none': No notifications
        account: Account name (uses default if not specified)
        timezone: Default timezone for all operations (IANA format, e.g., 'Europe/Kyiv').
            Can be overridden per operation.
    
    Returns:
        Dictionary with:
        - total: Total operations attempted
        - succeeded: Number of successful operations
        - failed: Number of failed operations
        - results: List of results for each operation with status and details
    
    Example operations:
    ```
    [
        {"action": "create", "summary": "Meeting 1", "start": "2025-01-15T10:00:00", "end": "2025-01-15T11:00:00"},
        {"action": "create", "summary": "Meeting 2", "start": "2025-01-15T14:00:00", "end": "2025-01-15T15:00:00"},
        {"action": "update", "event_id": "abc123", "summary": "Updated Title"},
        {"action": "delete", "event_id": "def456"}
    ]
    ```
    
    Operations are executed sequentially. A failure in one operation does not stop others.
    """
    results = []
    succeeded = 0
    failed = 0
    
    for i, op in enumerate(operations):
        action = op.get("action")
        
        try:
            if action == "create":
                # Extract create parameters (operation timezone overrides global)
                op_timezone = op.get("timezone") or timezone
                result = api_create_event(
                    summary=op.get("summary", "(No title)"),
                    start=op["start"],
                    end=op["end"],
                    account=account,
                    calendar_id=calendar_id,
                    description=op.get("description"),
                    location=op.get("location"),
                    timezone=op_timezone,
                    attendees=[{"email": e} for e in op.get("attendees", [])] if op.get("attendees") else None,
                    send_updates=send_updates,
                )
                results.append({
                    "index": i,
                    "action": "create",
                    "status": "success",
                    "event_id": result.get("id"),
                    "summary": result.get("summary"),
                })
                succeeded += 1
                
            elif action == "update":
                event_id = op.get("event_id")
                if not event_id:
                    raise ValueError("event_id required for update")
                
                # Build update kwargs
                update_kwargs = {
                    "event_id": event_id,
                    "account": account,
                    "calendar_id": calendar_id,
                    "send_updates": send_updates,
                }
                
                # Add optional fields if present
                for field in ["summary", "start", "end", "description", "location"]:
                    if field in op:
                        update_kwargs[field] = op[field]

                # Handle timezone: operation value overrides global
                op_timezone = op.get("timezone") or timezone
                if op_timezone:
                    update_kwargs["timezone"] = op_timezone
                
                result = api_update_event(**update_kwargs)
                results.append({
                    "index": i,
                    "action": "update",
                    "status": "success",
                    "event_id": event_id,
                })
                succeeded += 1
                
            elif action == "delete":
                event_id = op.get("event_id")
                if not event_id:
                    raise ValueError("event_id required for delete")
                
                api_delete_event(
                    event_id=event_id,
                    account=account,
                    calendar_id=calendar_id,
                    send_updates=send_updates,
                )
                results.append({
                    "index": i,
                    "action": "delete",
                    "status": "success",
                    "event_id": event_id,
                })
                succeeded += 1
                
            else:
                raise ValueError(f"Unknown action: {action}. Use 'create', 'update', or 'delete'.")
                
        except Exception as e:
            results.append({
                "index": i,
                "action": action or "unknown",
                "status": "error",
                "error": str(e),
            })
            failed += 1
    
    return {
        "total": len(operations),
        "succeeded": succeeded,
        "failed": failed,
        "results": results,
    }

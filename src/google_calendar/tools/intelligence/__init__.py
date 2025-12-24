"""
Intelligence tools: weekly_brief

Note: batch_operations and find_meeting_slots have been consolidated into:
- events.py (action="batch")
- availability.py (action="find_slots")
"""

from google_calendar.tools.intelligence.weekly_brief import weekly_brief

__all__ = ["weekly_brief"]

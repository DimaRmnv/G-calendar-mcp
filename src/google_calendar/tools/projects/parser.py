"""
Event summary parser for time tracking.

Parses Google Calendar event summaries to extract project code, phase, task, and description.
Based on the format: PROJECT * PHASE * TASK * Description

Supports three structure levels (level = number of components after PROJECT):
- Level 1: PROJECT * Description (UFSP, CSUM, EFCF, SEDRA3, AIYL-MN)
- Level 2: PROJECT * PHASE * Description (BCH, BDU, BDU-TEN)
- Level 3: PROJECT * PHASE * TASK * Description (ADB25, CAYIB, EDD)

Multiple projects can have the same code with different structure levels.
Parser tries each project variant until one matches the event format.
"""

import re
from typing import Optional
from dataclasses import dataclass
from datetime import datetime

from google_calendar.tools.projects.database import (
    get_projects_by_code,
    phase_get,
    task_get,
    is_excluded,
)


@dataclass
class ParsedEvent:
    """Parsed calendar event data."""
    project_code: Optional[str] = None
    project_id: Optional[int] = None
    phase_code: Optional[str] = None
    task_code: Optional[str] = None
    description: Optional[str] = None
    is_billable: bool = False
    position: Optional[str] = None
    errors: list = None
    raw_summary: str = ""
    is_excluded: bool = False
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []
    
    @property
    def is_valid(self) -> bool:
        """Event is valid if project code identified and no errors."""
        return self.project_code is not None and len(self.errors) == 0
    
    @property
    def has_errors(self) -> bool:
        """Event has parsing errors."""
        return len(self.errors) > 0


def parse_summary(summary: str) -> ParsedEvent:
    """
    Parse event summary to extract project code, phase, task, and description.
    
    Supported formats:
    - PROJECT * PHASE * TASK * Description
    - PROJECT : PHASE : TASK : Description
    - PROJECT * PHASE * Description
    - PROJECT * Description
    
    When multiple projects exist with the same code (different structure levels),
    tries each one starting from highest structure_level until a match is found.
    
    Returns ParsedEvent with extracted data and any errors.
    """
    result = ParsedEvent(raw_summary=summary)
    
    if not summary or not summary.strip():
        result.errors.append("Empty summary")
        return result
    
    summary = summary.strip()
    
    # Check exclusions first
    if is_excluded(summary):
        result.is_excluded = True
        return result
    
    # Split by delimiters: ' * ', ':', '*'
    # Priority: ' * ' > ':' > '*'
    if ' * ' in summary:
        parts = summary.split(' * ')
    elif ':' in summary:
        parts = summary.split(':')
    elif '*' in summary:
        parts = summary.split('*')
    else:
        # No delimiter - treat entire summary as description, try to find project code
        parts = [summary]
    
    # Clean parts
    parts = [p.strip() for p in parts if p.strip()]
    
    if not parts:
        result.errors.append("No content after parsing")
        return result
    
    # Extract potential project code (first part, uppercase)
    potential_project = parts[0].upper()
    
    # Handle special case: AIYL-MN suffix marker ##
    if summary.rstrip().endswith('##'):
        result.description = summary  # Keep full for reference
    
    # Look up ALL projects with this code (may be multiple with different levels)
    projects = get_projects_by_code(potential_project)
    
    if not projects:
        # Project not found - entire summary is description with error
        result.description = summary
        result.errors.append(f"Project code '{potential_project}' not found")
        return result
    
    # Try each project variant (sorted by structure_level DESC)
    # Return first successful parse
    for project in projects:
        attempt = _try_parse_with_project(parts, project)
        if attempt.is_valid:
            return attempt
    
    # No variant matched successfully - return last attempt with errors
    # But try to provide best possible result
    return _try_parse_with_project(parts, projects[0])


def _try_parse_with_project(parts: list[str], project: dict) -> ParsedEvent:
    """
    Try to parse event parts using a specific project configuration.
    
    Returns ParsedEvent - check is_valid to see if parsing succeeded.
    """
    result = ParsedEvent(raw_summary=' * '.join(parts))
    result.project_code = project["code"]
    result.project_id = project["id"]
    result.is_billable = project["is_billable"]
    result.position = project["position"]
    
    structure_level = project["structure_level"]
    
    # Parse based on structure level
    if structure_level == 3:
        return _parse_level_3(parts, result, project["id"])
    elif structure_level == 2:
        return _parse_level_2(parts, result, project["id"])
    else:
        return _parse_level_1(parts, result)


def _parse_level_1(parts: list[str], result: ParsedEvent) -> ParsedEvent:
    """
    Parse Level 1 structure: PROJECT * Description
    Used by: UFSP, CSUM, EFCF, SEDRA3, AIYL-MN, MABI4
    """
    if len(parts) > 1:
        result.description = ' * '.join(parts[1:])
    return result


def _parse_level_2(parts: list[str], result: ParsedEvent, project_id: int) -> ParsedEvent:
    """
    Parse Level 2 structure: PROJECT * PHASE * Description
    Used by: BCH, BFC, BDU, BDU-TEN, CAYIB (variant)
    """
    if len(parts) < 2:
        result.errors.append("Missing phase for Level 2 project")
        return result
    
    # Part 1: Phase
    potential_phase = parts[1].upper()
    phase = phase_get(project_id=project_id, code=potential_phase)

    if phase:
        result.phase_code = phase["code"]
        # Remaining parts are description
        if len(parts) > 2:
            result.description = ' * '.join(parts[2:])
    else:
        # Phase not found - treat rest as description with warning
        result.errors.append(f"Phase '{potential_phase}' not found")
        result.description = ' * '.join(parts[1:])
    
    return result


def _parse_level_3(parts: list[str], result: ParsedEvent, project_id: int) -> ParsedEvent:
    """
    Parse Level 3 structure: PROJECT * PHASE * TASK * Description
    Used by: ADB25, CAYIB, EDD
    """
    if len(parts) < 2:
        result.errors.append("Missing phase for Level 3 project")
        return result

    # Part 1: Phase
    potential_phase = parts[1].upper()
    phase = phase_get(project_id=project_id, code=potential_phase)

    if phase:
        result.phase_code = phase["code"]
    else:
        # Phase not found - might be description
        result.errors.append(f"Phase '{potential_phase}' not found")
        result.description = ' * '.join(parts[1:])
        return result

    if len(parts) < 3:
        # Only project and phase, no task or description
        return result

    # Part 2: Task or Description
    potential_task = parts[2].upper()
    task = task_get(project_id=project_id, code=potential_task)

    if task:
        result.task_code = task["code"]
        # Remaining parts are description
        if len(parts) > 3:
            result.description = ' * '.join(parts[3:])
    else:
        # Not a task code - treat as description
        result.description = ' * '.join(parts[2:])

    return result


@dataclass
class TimeEntry:
    """Processed time entry from calendar event."""
    date: datetime
    duration_hours: float
    project_code: Optional[str]
    phase_code: Optional[str]
    task_code: Optional[str]
    description: Optional[str]
    is_billable: bool
    position: Optional[str]
    errors: list
    raw_summary: str
    is_excluded: bool = False
    is_all_day: bool = False
    
    @property
    def is_valid(self) -> bool:
        return self.project_code is not None and len(self.errors) == 0

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0


def parse_calendar_event(event: dict) -> TimeEntry:
    """
    Parse Google Calendar event into TimeEntry.
    
    Args:
        event: Google Calendar event dict with 'summary', 'start', 'end'
    
    Returns:
        TimeEntry with parsed data
    """
    summary = event.get("summary", "")
    
    # Parse start/end times
    start_data = event.get("start", {})
    end_data = event.get("end", {})
    
    is_all_day = "date" in start_data and "dateTime" not in start_data
    
    if "dateTime" in start_data:
        start = datetime.fromisoformat(start_data["dateTime"].replace("Z", "+00:00"))
    elif "date" in start_data:
        start = datetime.fromisoformat(start_data["date"])
    else:
        start = datetime.now()
    
    if "dateTime" in end_data:
        end = datetime.fromisoformat(end_data["dateTime"].replace("Z", "+00:00"))
    elif "date" in end_data:
        end = datetime.fromisoformat(end_data["date"])
    else:
        end = start
    
    # Calculate duration
    if is_all_day:
        duration_hours = 8.0  # Standard workday for all-day events
    else:
        duration_seconds = (end - start).total_seconds()
        duration_hours = round(duration_seconds / 3600, 2)
    
    # Parse summary
    parsed = parse_summary(summary)
    
    return TimeEntry(
        date=start,
        duration_hours=duration_hours,
        project_code=parsed.project_code,
        phase_code=parsed.phase_code,
        task_code=parsed.task_code,
        description=parsed.description,
        is_billable=parsed.is_billable,
        position=parsed.position,
        errors=parsed.errors,
        raw_summary=summary,
        is_excluded=parsed.is_excluded,
        is_all_day=is_all_day
    )


def parse_events_batch(events: list[dict]) -> list[TimeEntry]:
    """
    Parse multiple calendar events.
    
    Args:
        events: List of Google Calendar event dicts
    
    Returns:
        List of TimeEntry objects
    """
    return [parse_calendar_event(event) for event in events]

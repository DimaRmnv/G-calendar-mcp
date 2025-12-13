"""
Database initialization for time tracking.

Creates empty database schema. Data population done separately via time_tracking tool.
"""

from gcalendar_mcp.tools.time_tracking.database import (
    project_add, project_get, phase_add, task_add, norm_add
)


def populate_default_data() -> dict:
    """
    Placeholder for default data population.
    
    Returns empty counts - all data should be added via time_tracking tool operations.
    """
    return {
        "projects": 0,
        "phases": 0,
        "tasks": 0,
        "norms": 0,
    }

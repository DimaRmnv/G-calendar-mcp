"""
Database initialization for projects.

Creates empty database schema. Data population done separately via projects tool.
"""

from google_calendar.tools.projects.database import (
    project_add, project_get, phase_add, task_add, norm_add
)


def populate_default_data() -> dict:
    """
    Placeholder for default data population.

    Returns empty counts - all data should be added via projects tool operations.
    """
    return {
        "projects": 0,
        "phases": 0,
        "tasks": 0,
        "norms": 0,
    }

"""
Projects management tool.

Single tool for project management and reporting:
- projects: CRUD for projects, phases, tasks, norms, exclusions, config + reports
"""

from google_calendar.tools.projects.manage import projects

__all__ = [
    "projects",
]

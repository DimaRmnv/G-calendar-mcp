"""
Time tracking tools for billable hours management.

Two tools (optimized for token efficiency):
- time_tracking: Batch management (projects, phases, tasks, norms, exclusions, config, init)
- time_tracking_report: Status and reports (quick status, week/month reports, Excel export)
"""

from google_calendar.tools.time_tracking.manage import time_tracking
from google_calendar.tools.time_tracking.report import time_tracking_report

__all__ = [
    "time_tracking",
    "time_tracking_report",
]

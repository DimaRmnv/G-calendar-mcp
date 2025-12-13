"""
Initialization tool for time tracking.

Creates database and optionally populates with default project data.
"""

from typing import Optional

from gcalendar_mcp.tools.time_tracking.database import (
    database_exists,
    init_database,
    create_project,
    create_phase,
    create_task,
    set_norm,
    get_project,
)


# Default project data based on calendar-manager skill
DEFAULT_PROJECTS = [
    # Billable projects - Level 3 (full structure: PROJECT * PHASE * TASK * Description)
    {
        "code": "ADB25",
        "description": "ADB TSCFP 2025 - Trade and Supply Chain Finance Program",
        "is_billable": True,
        "position": "Senior Bank Advisor",
        "structure_level": 3,
    },
    {
        "code": "CAYIB",
        "description": "Central Asia Youth In Business Programme",
        "is_billable": True,
        "position": "International MSME Banking Expert",
        "structure_level": 3,
    },
    {
        "code": "EDD",
        "description": "Due Diligence Trade & Supply Chain (GIZ)",
        "is_billable": True,
        "position": "Due Diligence Expert",
        "structure_level": 3,
    },
    # Billable projects - Level 1 (simple: PROJECT * Description)
    {
        "code": "UFSP",
        "description": "Uzbekistan Financial Sector Development",
        "is_billable": True,
        "position": "International MSME Banking Expert",
        "structure_level": 1,
    },
    {
        "code": "CSUM",
        "description": "Capacity Strengthening of Uzbekistan MFOs",
        "is_billable": True,
        "position": "International MSME Banking Expert",
        "structure_level": 1,
    },
    {
        "code": "SEDRA3",
        "description": "Nepal Rural Development - Revolving Fund",
        "is_billable": True,
        "position": "Revolving Fund Expert",
        "structure_level": 1,
    },
    {
        "code": "EFCF",
        "description": "Jordan Education Finance Revolving Fund",
        "is_billable": True,
        "position": "Business Analyst",
        "structure_level": 1,
    },
    {
        "code": "AIYL-MN",
        "description": "AIYL Software Maintenance",
        "is_billable": True,
        "position": "Business Analyst",
        "structure_level": 1,
    },
    # Non-billable projects - Level 2 (PROJECT * PHASE * Description)
    {
        "code": "BCH",
        "description": "BFC Internal Company Projects",
        "is_billable": False,
        "position": None,
        "structure_level": 2,
    },
    {
        "code": "BFC",
        "description": "BFC Internal (alias for BCH)",
        "is_billable": False,
        "position": None,
        "structure_level": 2,
    },
    {
        "code": "BDU",
        "description": "Business Development Unit",
        "is_billable": False,
        "position": "Senior Bank Advisor",
        "structure_level": 2,
    },
    {
        "code": "BDU-TEN",
        "description": "Business Development - Opportunity Evaluation",
        "is_billable": False,
        "position": "Senior Bank Advisor",
        "structure_level": 2,
    },
    # Non-billable - Level 1 (simple: PROJECT * Description)
    {
        "code": "MABI4",
        "description": "Intesa Master APS",
        "is_billable": False,
        "position": "Business Analyst",
        "structure_level": 1,
    },
    {
        "code": "OPP",
        "description": "Opportunity Evaluation",
        "is_billable": False,
        "position": "Senior Bank Advisor",
        "structure_level": 1,
    },
    {
        "code": "MAPS",
        "description": "Master APS Prospection & Internal Development",
        "is_billable": False,
        "position": "Business Analyst",
        "structure_level": 1,
    },
]

# ADB25 phases (countries and banks)
ADB25_PHASES = [
    ("AM", "Armenia"), ("AZ", "Azerbaijan"), ("BD", "Bangladesh"),
    ("KH", "Cambodia"), ("GE", "Georgia"), ("ID", "Indonesia"),
    ("KG", "Kyrgyzstan"), ("LA", "Laos"), ("MN", "Mongolia"),
    ("NP", "Nepal"), ("PK", "Pakistan"), ("LK", "Sri Lanka"),
    ("TJ", "Tajikistan"), ("UZ", "Uzbekistan"), ("VN", "Vietnam"),
    ("PM", "Project Management"),
    # Sample banks
    ("UZ-DAVR", "Davr Bank"), ("UZ-HAMKORBANK", "Hamkorbank"),
    ("UZ-IPAK", "Ipak Yuli Bank"), ("UZ-IPOTEKA", "Ipoteka Bank"),
    ("BD-BRAC", "BRAC Bank"), ("BD-CITY", "City Bank"),
    ("PK-HABIBBANK", "Habib Bank"), ("PK-MEEZAN", "Meezan Bank"),
    ("TJ-ESKHATA", "Eskhata Bank"), ("NP-NABIL", "Nabil Bank"),
]

# ADB25 tasks
ADB25_TASKS = [
    ("BA", "Bank Analysis"), ("BS", "Bank Slide"), ("AMLIC", "AML/CFT Checklist"),
    ("CR", "Country Review"), ("INN", "Innovation"), ("OR", "Other (ADB requests)"),
    ("PM", "Project Management"), ("QMR", "Quarterly Monitoring Report"),
    ("SPR", "Spreads"), ("DC", "Data Collection"), ("ADC", "AML Data Collection"),
    ("AMR", "AML Report"), ("FOCUS", "In Focus Reports"), ("MTG", "Meetings"),
]

# CAYIB phases (PFIs)
CAYIB_PHASES = [
    ("ARNUR", "Arnur Credit"), ("KMF", "KMF"), ("SHINHAN", "Shinhan Bank Kazakhstan"),
    ("BAILYK", "Bailyk Finance"), ("GOLOMT", "Golomt Bank"),
    ("TRANSCAPITAL", "TransCapital"), ("XACBANK", "XacBank"),
    ("ARVAND", "Arvand Bank"), ("ESKHATA", "Eskhata Bank"), ("ICB", "ICB"),
    ("HUMO", "Humo"), ("DAVR", "Davr Bank"), ("HAMKOR", "Hamkorbank"),
    ("IPAK", "Ipak Yuli"), ("SQB", "SQB"),
]

# CAYIB tasks
CAYIB_TASKS = [
    ("0", "Programme-level / Admin"), ("0.1", "Team Meetings / General Preparation"),
    ("0.2", "Reports (prep; subm)"), ("0.3", "Awareness & Marketing"),
    ("1", "Baseline Assessment Report"), ("1.1", "Kick-off Calls / Data Analysis"),
    ("1.2", "BA Report (site-visit; prep; subm)"), ("1.3", "Strategy Workshop"),
    ("2", "Tech Support Workplan"), ("2.1", "PFI Workplan"),
    ("2.2", "NFS Activities"), ("2.3", "Value Proposition and Sales"),
    ("2.4", "Capacity Building"), ("2.5", "Marketing Support"),
    ("2.6", "Data-Driven Management"),
]

# EDD phases
EDD_PHASES = [
    ("KG", "Kyrgyzstan"), ("TJ", "Tajikistan"), ("PK", "Pakistan"), ("UZ", "Uzbekistan"),
    ("UZ-MOEE", "Ministry of Ecology of Uzbekistan"),
    ("KG-MOWR", "Ministry of Water Resources"),
    ("AM", "Admin/Meetings"),
]

# EDD tasks
EDD_TASKS = [
    ("A", "Admin"), ("AM", "Meetings"), ("AR", "Progress Monitoring & Reporting"),
    ("AS", "Administrative Support"),
    ("OF", "Offsite phase"), ("OFK", "Kick-off and document request"),
    ("OFR", "Review documentation & prep"),
    ("ON", "Onsite phase"), ("ONI", "Interviews with stakeholders"),
    ("ONN", "Meeting notes & checklist"),
    ("DR", "Draft Report"), ("DRP", "Prepare Draft Report"),
    ("DRQA", "Draft Report QA"), ("DRF", "Submit Draft to GIZ"),
    ("FR", "Final Report"), ("FRP", "Prepare Final Report"),
    ("FRQA", "Final Report QA"), ("FRF", "Submit Final to GIZ"),
]

# BCH phases (internal categories)
BCH_PHASES = [
    ("ADB", "ADB Innovation"), ("CU", "ClickUp Development"),
    ("AI", "Artificial Intelligence"), ("ES", "Emergency Situations"),
    ("GT", "Get Together"), ("GOV", "Governance / Committee meetings"),
    ("GC", "Greetings Cards"), ("IDG", "IDG4FI"),
    ("IV", "Impact Ventures"), ("IDB", "Insightly Data Base"),
    ("ITS", "IT Security"), ("KMS", "Knowledge Management System"),
    ("L", "Legal"), ("MV", "Maverick"), ("N", "Newsletter"),
    ("MSO", "Office 365"), ("O", "Office"), ("ON", "Onboarding"),
    ("WEB", "Portal / Website"), ("RT", "Resource Tracking"),
    ("SD", "Strategy Development"), ("SA", "Sub Advisory"),
    ("TG", "Timesheets / Google calendar"), ("MTNG", "Meetings"),
]

# BDU phases
BDU_PHASES = [
    ("CRM", "CRM & BI tool"), ("BHR", "HR"),
    ("PDD", "PDs Development / Update"), ("BDR", "Relationship management"),
    ("BDS", "Strategy"), ("TC", "Tender committee"),
    ("BTT", "Tender / rumour tracking"), ("BWC", "Weekly calls"),
    ("OA", "Opportunity analysis"),
]

# BDU-TEN phases (opportunity codes)
BDU_TEN_PHASES = [
    ("NSRA", "2025-10-REG-NASIRA PLUS Onboarding-FMO"),
    ("SCUZ", "Uzbekistan MFI project"),
]

# Default workday norms (Thailand 2025)
DEFAULT_NORMS_2025 = [
    (2025, 1, 176), (2025, 2, 160), (2025, 3, 160), (2025, 4, 168),
    (2025, 5, 160), (2025, 6, 152), (2025, 7, 176), (2025, 8, 160),
    (2025, 9, 176), (2025, 10, 176), (2025, 11, 160), (2025, 12, 176),
]


def _populate_defaults() -> dict:
    """Populate database with default data. Returns counts of created items."""
    counts = {
        "projects": 0,
        "phases": 0,
        "tasks": 0,
        "norms": 0,
    }
    
    # Create projects
    for proj_data in DEFAULT_PROJECTS:
        try:
            if not get_project(proj_data["code"]):
                create_project(**proj_data)
                counts["projects"] += 1
        except Exception:
            pass
    
    # Create phases and tasks for ADB25
    for phase_code, desc in ADB25_PHASES:
        try:
            create_phase("ADB25", phase_code, desc)
            counts["phases"] += 1
        except Exception:
            pass
    
    for task_code, desc in ADB25_TASKS:
        try:
            create_task("ADB25", task_code, desc)
            counts["tasks"] += 1
        except Exception:
            pass
    
    # CAYIB
    for phase_code, desc in CAYIB_PHASES:
        try:
            create_phase("CAYIB", phase_code, desc)
            counts["phases"] += 1
        except Exception:
            pass
    
    for task_code, desc in CAYIB_TASKS:
        try:
            create_task("CAYIB", task_code, desc)
            counts["tasks"] += 1
        except Exception:
            pass
    
    # EDD
    for phase_code, desc in EDD_PHASES:
        try:
            create_phase("EDD", phase_code, desc)
            counts["phases"] += 1
        except Exception:
            pass
    
    for task_code, desc in EDD_TASKS:
        try:
            create_task("EDD", task_code, desc)
            counts["tasks"] += 1
        except Exception:
            pass
    
    # BCH
    for phase_code, desc in BCH_PHASES:
        try:
            create_phase("BCH", phase_code, desc)
            counts["phases"] += 1
        except Exception:
            pass
    
    # BFC (same phases as BCH)
    for phase_code, desc in BCH_PHASES:
        try:
            create_phase("BFC", phase_code, desc)
            counts["phases"] += 1
        except Exception:
            pass
    
    # BDU
    for phase_code, desc in BDU_PHASES:
        try:
            create_phase("BDU", phase_code, desc)
            counts["phases"] += 1
        except Exception:
            pass
    
    # BDU-TEN
    for phase_code, desc in BDU_TEN_PHASES:
        try:
            create_phase("BDU-TEN", phase_code, desc)
            counts["phases"] += 1
        except Exception:
            pass
    
    # Workday norms
    for year, month, hours in DEFAULT_NORMS_2025:
        try:
            set_norm(year, month, hours)
            counts["norms"] += 1
        except Exception:
            pass
    
    return counts


async def time_tracking_init(
    populate_defaults: bool = True,
    force_reset: bool = False,
) -> dict:
    """
    Initialize time tracking database.
    
    Args:
        populate_defaults: If True, populate with default projects/phases/tasks
        force_reset: If True, recreate database even if exists (WARNING: deletes data)
    
    Returns:
        Dict with initialization status and counts of created items
    
    Default data includes:
        - 15 projects (ADB25, CAYIB, EDD, BCH, BDU, CSUM, UFSP, etc.)
        - Phases for Level 2 and 3 projects
        - Task codes for ADB25, CAYIB, EDD
        - 2025 workday norms (Thailand calendar)
        - Default exclusions (Away, Lunch, Offline, Out of office)
    
    After init, configure your settings:
        - time_tracking_config set work_calendar <your-calendar-id>
        - time_tracking_config set base_location <your-city>
        - time_tracking_norms set <year> <month> <hours> (if different from defaults)
    """
    from gcalendar_mcp.tools.time_tracking.database import get_database_path
    import os
    
    db_path = get_database_path()
    already_existed = database_exists()
    
    if force_reset and already_existed:
        os.remove(db_path)
        already_existed = False
    
    if already_existed and not force_reset:
        return {
            "status": "exists",
            "message": "Database already exists. Use force_reset=True to recreate.",
            "path": str(db_path),
        }
    
    # Initialize schema
    init_database()
    
    result = {
        "status": "created",
        "path": str(db_path),
        "schema_initialized": True,
    }
    
    # Populate defaults if requested
    if populate_defaults:
        counts = _populate_defaults()
        result["defaults_populated"] = True
        result["counts"] = counts
        result["message"] = (
            f"Database initialized with {counts['projects']} projects, "
            f"{counts['phases']} phases, {counts['tasks']} tasks, "
            f"{counts['norms']} monthly norms."
        )
    else:
        result["defaults_populated"] = False
        result["message"] = "Database initialized with empty schema. Add projects manually."
    
    return result

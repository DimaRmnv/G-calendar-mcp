"""
Default data for time tracking initialization.

Contains project definitions, phases, tasks, and norms.
Used by manage.py init operation.
"""

from gcalendar_mcp.tools.time_tracking.database import (
    project_add, project_get, phase_add, task_add, norm_add
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

# Phases by project code
PROJECT_PHASES = {
    "ADB25": [
        ("AM", "Armenia"), ("AZ", "Azerbaijan"), ("BD", "Bangladesh"),
        ("KH", "Cambodia"), ("GE", "Georgia"), ("ID", "Indonesia"),
        ("KG", "Kyrgyzstan"), ("LA", "Laos"), ("MN", "Mongolia"),
        ("NP", "Nepal"), ("PK", "Pakistan"), ("LK", "Sri Lanka"),
        ("TJ", "Tajikistan"), ("UZ", "Uzbekistan"), ("VN", "Vietnam"),
        ("PM", "Project Management"),
        ("UZ-DAVR", "Davr Bank"), ("UZ-HAMKORBANK", "Hamkorbank"),
        ("UZ-IPAK", "Ipak Yuli Bank"), ("UZ-IPOTEKA", "Ipoteka Bank"),
        ("BD-BRAC", "BRAC Bank"), ("BD-CITY", "City Bank"),
        ("PK-HABIBBANK", "Habib Bank"), ("PK-MEEZAN", "Meezan Bank"),
        ("TJ-ESKHATA", "Eskhata Bank"), ("NP-NABIL", "Nabil Bank"),
    ],
    "CAYIB": [
        ("ARNUR", "Arnur Credit"), ("KMF", "KMF"), ("SHINHAN", "Shinhan Bank Kazakhstan"),
        ("BAILYK", "Bailyk Finance"), ("GOLOMT", "Golomt Bank"),
        ("TRANSCAPITAL", "TransCapital"), ("XACBANK", "XacBank"),
        ("ARVAND", "Arvand Bank"), ("ESKHATA", "Eskhata Bank"), ("ICB", "ICB"),
        ("HUMO", "Humo"), ("DAVR", "Davr Bank"), ("HAMKOR", "Hamkorbank"),
        ("IPAK", "Ipak Yuli"), ("SQB", "SQB"),
    ],
    "EDD": [
        ("KG", "Kyrgyzstan"), ("TJ", "Tajikistan"), ("PK", "Pakistan"), ("UZ", "Uzbekistan"),
        ("UZ-MOEE", "Ministry of Ecology of Uzbekistan"),
        ("KG-MOWR", "Ministry of Water Resources"),
        ("AM", "Admin/Meetings"),
    ],
    "BCH": [
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
    ],
    "BDU": [
        ("CRM", "CRM & BI tool"), ("BHR", "HR"),
        ("PDD", "PDs Development / Update"), ("BDR", "Relationship management"),
        ("BDS", "Strategy"), ("TC", "Tender committee"),
        ("BTT", "Tender / rumour tracking"), ("BWC", "Weekly calls"),
        ("OA", "Opportunity analysis"),
    ],
    "BDU-TEN": [
        ("NSRA", "2025-10-REG-NASIRA PLUS Onboarding-FMO"),
        ("SCUZ", "Uzbekistan MFI project"),
    ],
}

# BFC gets same phases as BCH
PROJECT_PHASES["BFC"] = PROJECT_PHASES["BCH"]

# Tasks by project code
PROJECT_TASKS = {
    "ADB25": [
        ("BA", "Bank Analysis"), ("BS", "Bank Slide"), ("AMLIC", "AML/CFT Checklist"),
        ("CR", "Country Review"), ("INN", "Innovation"), ("OR", "Other (ADB requests)"),
        ("PM", "Project Management"), ("QMR", "Quarterly Monitoring Report"),
        ("SPR", "Spreads"), ("DC", "Data Collection"), ("ADC", "AML Data Collection"),
        ("AMR", "AML Report"), ("FOCUS", "In Focus Reports"), ("MTG", "Meetings"),
    ],
    "CAYIB": [
        ("0", "Programme-level / Admin"), ("0.1", "Team Meetings / General Preparation"),
        ("0.2", "Reports (prep; subm)"), ("0.3", "Awareness & Marketing"),
        ("1", "Baseline Assessment Report"), ("1.1", "Kick-off Calls / Data Analysis"),
        ("1.2", "BA Report (site-visit; prep; subm)"), ("1.3", "Strategy Workshop"),
        ("2", "Tech Support Workplan"), ("2.1", "PFI Workplan"),
        ("2.2", "NFS Activities"), ("2.3", "Value Proposition and Sales"),
        ("2.4", "Capacity Building"), ("2.5", "Marketing Support"),
        ("2.6", "Data-Driven Management"),
    ],
    "EDD": [
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
    ],
}

# Default workday norms (Thailand 2025)
DEFAULT_NORMS_2025 = [
    (2025, 1, 176), (2025, 2, 160), (2025, 3, 160), (2025, 4, 168),
    (2025, 5, 160), (2025, 6, 152), (2025, 7, 176), (2025, 8, 160),
    (2025, 9, 176), (2025, 10, 176), (2025, 11, 160), (2025, 12, 176),
]


def populate_default_data() -> dict:
    """
    Populate database with default data.

    Returns counts of created items.
    """
    counts = {
        "projects": 0,
        "phases": 0,
        "tasks": 0,
        "norms": 0,
    }

    # Create projects and track their IDs
    project_ids = {}
    for proj_data in DEFAULT_PROJECTS:
        try:
            existing = project_get(code=proj_data["code"])
            if not existing:
                result = project_add(**proj_data)
                project_ids[proj_data["code"]] = result["id"]
                counts["projects"] += 1
            else:
                project_ids[proj_data["code"]] = existing["id"]
        except Exception:
            pass

    # Create phases
    for project_code, phases in PROJECT_PHASES.items():
        project_id = project_ids.get(project_code)
        if not project_id:
            continue
        for phase_code, desc in phases:
            try:
                phase_add(project_id=project_id, code=phase_code, description=desc)
                counts["phases"] += 1
            except Exception:
                pass

    # Create tasks
    for project_code, tasks in PROJECT_TASKS.items():
        project_id = project_ids.get(project_code)
        if not project_id:
            continue
        for task_code, desc in tasks:
            try:
                task_add(project_id=project_id, code=task_code, description=desc)
                counts["tasks"] += 1
            except Exception:
                pass

    # Create norms
    for year, month, hours in DEFAULT_NORMS_2025:
        try:
            norm_add(year=year, month=month, hours=hours)
            counts["norms"] += 1
        except Exception:
            pass

    return counts

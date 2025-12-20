"""
Contact reporting and analytics module.

Provides reports on contacts, project teams, and communication patterns.
Includes Excel export functionality.
"""

from datetime import datetime, timedelta
from typing import Optional
from pathlib import Path
from .database import get_connection


def contacts_report(
    report_type: str,
    project_id: int = None,
    organization: str = None,
    days_stale: int = 90,
    limit: int = 50
) -> dict:
    """
    Generate contact reports.
    
    Args:
        report_type: Type of report:
            - 'project_team': Full team roster with contacts for a project
            - 'organization': Contacts grouped by organization
            - 'communication_map': Contact channels summary
            - 'stale_contacts': Contacts not updated in X days
            - 'summary': Overall contacts summary
        project_id: Required for project_team report
        organization: Filter for organization report
        days_stale: Days threshold for stale_contacts (default 90)
        limit: Max results (default 50)
    
    Returns:
        Dict with report data based on report_type
    """
    if report_type == 'project_team':
        return _report_project_team(project_id)
    elif report_type == 'organization':
        return _report_by_organization(organization, limit)
    elif report_type == 'communication_map':
        return _report_communication_map(limit)
    elif report_type == 'stale_contacts':
        return _report_stale_contacts(days_stale, limit)
    elif report_type == 'summary':
        return _report_summary()
    else:
        return {"error": f"Unknown report type: {report_type}"}


def _report_project_team(project_id: int) -> dict:
    """Full team roster for a project with all contact details."""
    if not project_id:
        return {"error": "project_id is required for project_team report"}
    
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Get project info
        cursor.execute("""
            SELECT id, code, description, is_billable, is_active
            FROM projects WHERE id = ?
        """, (project_id,))
        project = cursor.fetchone()
        if not project:
            return {"error": f"Project {project_id} not found"}
        
        project_info = dict(project)
        
        # Get team members with roles
        cursor.execute("""
            SELECT 
                c.id as contact_id,
                c.first_name,
                c.last_name,
                c.organization,
                c.job_title,
                c.country,
                cp.role_code,
                pr.role_name_en as role_name,
                pr.role_category,
                cp.start_date,
                cp.end_date,
                cp.workdays_allocated,
                cp.is_active as assignment_active
            FROM contact_projects cp
            JOIN contacts c ON cp.contact_id = c.id
            JOIN project_roles pr ON cp.role_code = pr.role_code
            WHERE cp.project_id = ?
            ORDER BY pr.role_category, pr.role_name_en, c.last_name
        """, (project_id,))
        
        members = []
        for row in cursor.fetchall():
            member = dict(row)
            
            # Get channels for this contact
            cursor.execute("""
                SELECT channel_type, channel_value, is_primary
                FROM contact_channels
                WHERE contact_id = ?
                ORDER BY is_primary DESC
            """, (member['contact_id'],))
            member['channels'] = [dict(ch) for ch in cursor.fetchall()]
            
            # Extract primary channels
            for ch in member['channels']:
                if ch['is_primary']:
                    member[f"primary_{ch['channel_type']}"] = ch['channel_value']
            
            members.append(member)
        
        # Group by role category
        by_category = {}
        for m in members:
            cat = m.get('role_category', 'other')
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(m)
        
        return {
            'report_type': 'project_team',
            'project': project_info,
            'team_size': len(members),
            'members': members,
            'by_category': by_category,
            'generated_at': datetime.now().isoformat()
        }


def _report_by_organization(organization: str = None, limit: int = 50) -> dict:
    """Contacts grouped by organization."""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        if organization:
            # Single organization
            cursor.execute("""
                SELECT 
                    id, first_name, last_name, organization, 
                    organization_type, job_title, country,
                    preferred_channel
                FROM contacts
                WHERE organization = ? OR organization LIKE ?
                ORDER BY last_name, first_name
                LIMIT ?
            """, (organization, f"%{organization}%", limit))
            
            contacts = [dict(row) for row in cursor.fetchall()]
            
            # Get channels for each
            for c in contacts:
                cursor.execute("""
                    SELECT channel_type, channel_value, is_primary
                    FROM contact_channels WHERE contact_id = ?
                """, (c['id'],))
                c['channels'] = [dict(ch) for ch in cursor.fetchall()]
            
            return {
                'report_type': 'organization',
                'organization': organization,
                'contact_count': len(contacts),
                'contacts': contacts,
                'generated_at': datetime.now().isoformat()
            }
        else:
            # All organizations summary
            cursor.execute("""
                SELECT 
                    organization,
                    organization_type,
                    COUNT(*) as contact_count,
                    GROUP_CONCAT(DISTINCT country) as countries
                FROM contacts
                WHERE organization IS NOT NULL AND organization != ''
                GROUP BY organization, organization_type
                ORDER BY contact_count DESC
                LIMIT ?
            """, (limit,))
            
            orgs = [dict(row) for row in cursor.fetchall()]
            
            return {
                'report_type': 'organization_summary',
                'organization_count': len(orgs),
                'organizations': orgs,
                'generated_at': datetime.now().isoformat()
            }


def _report_communication_map(limit: int = 50) -> dict:
    """Summary of contact channels - who can be reached how."""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Channel type distribution
        cursor.execute("""
            SELECT 
                channel_type,
                COUNT(*) as count,
                COUNT(CASE WHEN is_primary = 1 THEN 1 END) as primary_count
            FROM contact_channels
            GROUP BY channel_type
            ORDER BY count DESC
        """)
        channel_stats = [dict(row) for row in cursor.fetchall()]
        
        # Contacts with multiple channels
        cursor.execute("""
            SELECT 
                c.id,
                c.first_name || ' ' || c.last_name as name,
                c.organization,
                COUNT(cc.id) as channel_count,
                GROUP_CONCAT(DISTINCT cc.channel_type) as channel_types
            FROM contacts c
            JOIN contact_channels cc ON c.id = cc.contact_id
            GROUP BY c.id
            ORDER BY channel_count DESC
            LIMIT ?
        """, (limit,))
        multi_channel = [dict(row) for row in cursor.fetchall()]
        
        # Contacts without channels
        cursor.execute("""
            SELECT 
                c.id,
                c.first_name || ' ' || c.last_name as name,
                c.organization
            FROM contacts c
            LEFT JOIN contact_channels cc ON c.id = cc.contact_id
            WHERE cc.id IS NULL
            LIMIT ?
        """, (limit,))
        no_channels = [dict(row) for row in cursor.fetchall()]
        
        # Preferred channel distribution
        cursor.execute("""
            SELECT 
                preferred_channel,
                COUNT(*) as count
            FROM contacts
            WHERE preferred_channel IS NOT NULL
            GROUP BY preferred_channel
            ORDER BY count DESC
        """)
        preferred_stats = [dict(row) for row in cursor.fetchall()]
        
        return {
            'report_type': 'communication_map',
            'channel_distribution': channel_stats,
            'preferred_channels': preferred_stats,
            'multi_channel_contacts': multi_channel,
            'contacts_without_channels': no_channels,
            'no_channel_count': len(no_channels),
            'generated_at': datetime.now().isoformat()
        }


def _report_stale_contacts(days_stale: int = 90, limit: int = 50) -> dict:
    """Contacts not updated recently."""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        cutoff = (datetime.now() - timedelta(days=days_stale)).isoformat()
        
        cursor.execute("""
            SELECT 
                c.id,
                c.first_name || ' ' || c.last_name as name,
                c.organization,
                c.updated_at,
                julianday('now') - julianday(c.updated_at) as days_since_update
            FROM contacts c
            WHERE c.updated_at < ? OR c.updated_at IS NULL
            ORDER BY c.updated_at ASC
            LIMIT ?
        """, (cutoff, limit))
        
        stale = [dict(row) for row in cursor.fetchall()]
        
        # Add channels for each
        for c in stale:
            cursor.execute("""
                SELECT channel_type, channel_value
                FROM contact_channels WHERE contact_id = ?
                LIMIT 3
            """, (c['id'],))
            c['channels'] = [dict(ch) for ch in cursor.fetchall()]
        
        return {
            'report_type': 'stale_contacts',
            'days_threshold': days_stale,
            'stale_count': len(stale),
            'contacts': stale,
            'generated_at': datetime.now().isoformat()
        }


def _report_summary() -> dict:
    """Overall contacts database summary."""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Total contacts
        cursor.execute("SELECT COUNT(*) FROM contacts")
        total_contacts = cursor.fetchone()[0]
        
        # Contacts by organization type
        cursor.execute("""
            SELECT organization_type, COUNT(*) as count
            FROM contacts
            WHERE organization_type IS NOT NULL
            GROUP BY organization_type
            ORDER BY count DESC
        """)
        by_org_type = [dict(row) for row in cursor.fetchall()]
        
        # Contacts by country
        cursor.execute("""
            SELECT country, COUNT(*) as count
            FROM contacts
            WHERE country IS NOT NULL
            GROUP BY country
            ORDER BY count DESC
            LIMIT 10
        """)
        by_country = [dict(row) for row in cursor.fetchall()]
        
        # Total channels
        cursor.execute("SELECT COUNT(*) FROM contact_channels")
        total_channels = cursor.fetchone()[0]
        
        # Channel types
        cursor.execute("""
            SELECT channel_type, COUNT(*) as count
            FROM contact_channels
            GROUP BY channel_type
            ORDER BY count DESC
        """)
        channel_types = [dict(row) for row in cursor.fetchall()]
        
        # Project assignments
        cursor.execute("SELECT COUNT(*) FROM contact_projects WHERE is_active = 1")
        active_assignments = cursor.fetchone()[0]
        
        # Unique projects with assignments
        cursor.execute("SELECT COUNT(DISTINCT project_id) FROM contact_projects WHERE is_active = 1")
        projects_with_teams = cursor.fetchone()[0]
        
        # Recent additions (last 30 days)
        cutoff = (datetime.now() - timedelta(days=30)).isoformat()
        cursor.execute("SELECT COUNT(*) FROM contacts WHERE created_at > ?", (cutoff,))
        recent_additions = cursor.fetchone()[0]
        
        return {
            'report_type': 'summary',
            'total_contacts': total_contacts,
            'total_channels': total_channels,
            'active_assignments': active_assignments,
            'projects_with_teams': projects_with_teams,
            'recent_additions_30d': recent_additions,
            'by_organization_type': by_org_type,
            'by_country': by_country,
            'channel_types': channel_types,
            'generated_at': datetime.now().isoformat()
        }


def export_contacts_excel(
    filter_params: dict = None,
    output_path: str = None
) -> dict:
    """
    Export contacts to Excel with all channels.
    
    Args:
        filter_params: Optional filters:
            - organization: Filter by organization
            - organization_type: Filter by org type
            - country: Filter by country
            - project_id: Filter by project assignment
        output_path: Custom output path (default: ~/Downloads/contacts_export_YYYYMMDD.xlsx)
    
    Returns:
        Dict with filepath and export stats
    """
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Border, Side, Alignment
        from openpyxl.utils import get_column_letter
    except ImportError:
        return {"error": "openpyxl not installed. Run: pip install openpyxl"}
    
    filter_params = filter_params or {}
    
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Build query with filters
        query = """
            SELECT DISTINCT
                c.id,
                c.first_name,
                c.last_name,
                c.organization,
                c.organization_type,
                c.job_title,
                c.country,
                c.preferred_channel,
                c.notes,
                c.created_at,
                c.updated_at
            FROM contacts c
        """
        params = []
        where_clauses = []
        
        if filter_params.get('project_id'):
            query += " JOIN contact_projects cp ON c.id = cp.contact_id"
            where_clauses.append("cp.project_id = ?")
            params.append(filter_params['project_id'])
        
        if filter_params.get('organization'):
            where_clauses.append("c.organization LIKE ?")
            params.append(f"%{filter_params['organization']}%")
        
        if filter_params.get('organization_type'):
            where_clauses.append("c.organization_type = ?")
            params.append(filter_params['organization_type'])
        
        if filter_params.get('country'):
            where_clauses.append("c.country = ?")
            params.append(filter_params['country'])
        
        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)
        
        query += " ORDER BY c.last_name, c.first_name"
        
        cursor.execute(query, params)
        contacts = [dict(row) for row in cursor.fetchall()]
        
        # Get all channels
        for c in contacts:
            cursor.execute("""
                SELECT channel_type, channel_value, is_primary
                FROM contact_channels WHERE contact_id = ?
            """, (c['id'],))
            channels = cursor.fetchall()
            
            # Flatten channels into contact dict
            for ch in channels:
                ch_type = ch['channel_type']
                if ch['is_primary']:
                    c[f'{ch_type}_primary'] = ch['channel_value']
                else:
                    # Handle multiple non-primary channels
                    key = ch_type
                    i = 2
                    while key in c:
                        key = f"{ch_type}_{i}"
                        i += 1
                    c[key] = ch['channel_value']
        
        # Get project assignments
        for c in contacts:
            cursor.execute("""
                SELECT p.code, pr.role_name_en
                FROM contact_projects cp
                JOIN projects p ON cp.project_id = p.id
                JOIN project_roles pr ON cp.role_code = pr.role_code
                WHERE cp.contact_id = ? AND cp.is_active = 1
            """, (c['id'],))
            projects = cursor.fetchall()
            c['projects'] = ', '.join([f"{p['code']} ({p['role_name_en']})" for p in projects])
    
    # Create Excel workbook
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Contacts"
    
    # Define columns
    columns = [
        'ID', 'First Name', 'Last Name', 'Organization', 'Org Type',
        'Job Title', 'Country', 'Preferred Channel',
        'Email', 'Phone', 'Telegram', 'Teams', 'WhatsApp',
        'Projects', 'Notes', 'Created', 'Updated'
    ]
    
    # Header style
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")
    thin_border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )
    
    # Write headers
    for col, header in enumerate(columns, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.border = thin_border
        cell.alignment = Alignment(horizontal='center')
    
    # Write data
    for row_idx, contact in enumerate(contacts, 2):
        ws.cell(row=row_idx, column=1, value=contact.get('id'))
        ws.cell(row=row_idx, column=2, value=contact.get('first_name'))
        ws.cell(row=row_idx, column=3, value=contact.get('last_name'))
        ws.cell(row=row_idx, column=4, value=contact.get('organization'))
        ws.cell(row=row_idx, column=5, value=contact.get('organization_type'))
        ws.cell(row=row_idx, column=6, value=contact.get('job_title'))
        ws.cell(row=row_idx, column=7, value=contact.get('country'))
        ws.cell(row=row_idx, column=8, value=contact.get('preferred_channel'))
        ws.cell(row=row_idx, column=9, value=contact.get('email_primary') or contact.get('email'))
        ws.cell(row=row_idx, column=10, value=contact.get('phone_primary') or contact.get('phone'))
        ws.cell(row=row_idx, column=11, value=contact.get('telegram_username') or contact.get('telegram_chat_id'))
        ws.cell(row=row_idx, column=12, value=contact.get('teams_chat_id'))
        ws.cell(row=row_idx, column=13, value=contact.get('whatsapp'))
        ws.cell(row=row_idx, column=14, value=contact.get('projects'))
        ws.cell(row=row_idx, column=15, value=contact.get('notes'))
        ws.cell(row=row_idx, column=16, value=contact.get('created_at'))
        ws.cell(row=row_idx, column=17, value=contact.get('updated_at'))
        
        # Apply borders
        for col in range(1, len(columns) + 1):
            ws.cell(row=row_idx, column=col).border = thin_border
    
    # Auto-adjust column widths
    for col in range(1, len(columns) + 1):
        max_length = len(columns[col-1])
        for row in range(2, len(contacts) + 2):
            cell_value = ws.cell(row=row, column=col).value
            if cell_value:
                max_length = max(max_length, min(len(str(cell_value)), 50))
        ws.column_dimensions[get_column_letter(col)].width = max_length + 2
    
    # Freeze header row
    ws.freeze_panes = 'A2'
    
    # Save file
    if not output_path:
        downloads = Path.home() / "Downloads"
        output_path = downloads / f"contacts_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    
    wb.save(output_path)
    
    return {
        'filepath': str(output_path),
        'contact_count': len(contacts),
        'filters_applied': filter_params,
        'generated_at': datetime.now().isoformat()
    }


def export_project_team_excel(
    project_id: int,
    output_path: str = None
) -> dict:
    """
    Export project team roster to Excel.
    
    Args:
        project_id: Project ID
        output_path: Custom output path
    
    Returns:
        Dict with filepath and export stats
    """
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Border, Side, Alignment
        from openpyxl.utils import get_column_letter
    except ImportError:
        return {"error": "openpyxl not installed. Run: pip install openpyxl"}
    
    # Get team data
    team_data = _report_project_team(project_id)
    if 'error' in team_data:
        return team_data
    
    project = team_data['project']
    members = team_data['members']
    
    # Create workbook
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"Team - {project['code']}"
    
    # Header styles
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")
    title_font = Font(bold=True, size=14)
    thin_border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )
    
    # Title
    ws.cell(row=1, column=1, value=f"Project Team: {project['code']} - {project.get('description', '')}").font = title_font
    ws.merge_cells('A1:H1')
    
    # Column headers
    columns = [
        'Name', 'Role', 'Category', 'Organization', 
        'Email', 'Phone', 'Telegram', 'Teams'
    ]
    
    for col, header in enumerate(columns, 1):
        cell = ws.cell(row=3, column=col, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.border = thin_border
        cell.alignment = Alignment(horizontal='center')
    
    # Write members
    for row_idx, member in enumerate(members, 4):
        name = f"{member.get('first_name', '')} {member.get('last_name', '')}".strip()
        ws.cell(row=row_idx, column=1, value=name)
        ws.cell(row=row_idx, column=2, value=member.get('role_name'))
        ws.cell(row=row_idx, column=3, value=member.get('role_category'))
        ws.cell(row=row_idx, column=4, value=member.get('organization'))
        
        # Extract channels
        channels = {ch['channel_type']: ch['channel_value'] for ch in member.get('channels', [])}
        ws.cell(row=row_idx, column=5, value=channels.get('email'))
        ws.cell(row=row_idx, column=6, value=channels.get('phone'))
        ws.cell(row=row_idx, column=7, value=channels.get('telegram_username') or channels.get('telegram_chat_id'))
        ws.cell(row=row_idx, column=8, value=channels.get('teams_chat_id'))
        
        for col in range(1, len(columns) + 1):
            ws.cell(row=row_idx, column=col).border = thin_border
    
    # Auto-adjust column widths
    for col in range(1, len(columns) + 1):
        max_length = len(columns[col-1])
        for row in range(4, len(members) + 4):
            cell_value = ws.cell(row=row, column=col).value
            if cell_value:
                max_length = max(max_length, min(len(str(cell_value)), 40))
        ws.column_dimensions[get_column_letter(col)].width = max_length + 2
    
    # Freeze header
    ws.freeze_panes = 'A4'
    
    # Save
    if not output_path:
        downloads = Path.home() / "Downloads"
        output_path = downloads / f"team_{project['code']}_{datetime.now().strftime('%Y%m%d')}.xlsx"
    
    wb.save(output_path)
    
    return {
        'filepath': str(output_path),
        'project': project,
        'member_count': len(members),
        'generated_at': datetime.now().isoformat()
    }

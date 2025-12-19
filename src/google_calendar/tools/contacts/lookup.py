"""
Contact lookup and resolution module.

Provides intelligent contact resolution from various identifiers
for use by mcp-orchestration and other modules.
"""

import re
from typing import Optional
from .database import (
    contact_get,
    contact_search,
    get_connection,
)


def _detect_identifier_type(identifier: str) -> str:
    """
    Detect the type of identifier provided.
    
    Returns one of:
        - 'email': Contains @ and looks like email
        - 'telegram': Starts with @ (username) or is numeric (chat_id)
        - 'phone': Starts with + or contains only digits
        - 'teams_chat': Starts with 19: (Teams chat ID format)
        - 'name': Default - treat as name search
    """
    identifier = identifier.strip()
    
    # Teams chat ID: starts with 19: (check first, before email)
    if identifier.startswith('19:'):
        return 'teams_chat'
    
    # Telegram username: starts with @ but no domain
    if identifier.startswith('@'):
        return 'telegram'
    
    # Email: contains @ with domain (but not Teams format)
    if '@' in identifier and '.' in identifier.split('@')[-1]:
        return 'email'
    
    # Phone: starts with + or is mostly digits
    if identifier.startswith('+'):
        return 'phone'
    
    # Numeric - could be telegram chat_id or phone
    digits_only = re.sub(r'\D', '', identifier)
    if len(digits_only) >= 7 and len(digits_only) == len(identifier.replace(' ', '').replace('-', '')):
        # If 10+ digits, likely phone; otherwise telegram chat_id
        if len(digits_only) >= 10:
            return 'phone'
        return 'telegram'
    
    # Default: name search
    return 'name'


def _get_contact_with_channels(contact_id: int) -> Optional[dict]:
    """Get full contact info with all channels."""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Get contact
        cursor.execute("""
            SELECT * FROM v_contacts_full WHERE id = ?
        """, (contact_id,))
        row = cursor.fetchone()
        if not row:
            return None
        
        contact = dict(row)
        
        # Get all channels
        cursor.execute("""
            SELECT 
                id,
                channel_type,
                channel_value,
                is_primary,
                channel_label,
                notes
            FROM contact_channels 
            WHERE contact_id = ?
            ORDER BY is_primary DESC, channel_type
        """, (contact_id,))
        
        contact['channels'] = [dict(ch) for ch in cursor.fetchall()]
        
        # Get project assignments
        cursor.execute("""
            SELECT 
                cp.id as assignment_id,
                cp.project_id,
                p.code as project_code,
                p.description as project_name,
                cp.role_code,
                pr.role_name_en as role_name,
                cp.start_date,
                cp.end_date,
                cp.workdays_allocated
            FROM contact_projects cp
            JOIN project_roles pr ON cp.role_code = pr.role_code
            LEFT JOIN projects p ON cp.project_id = p.id
            WHERE cp.contact_id = ? AND cp.is_active = 1
            ORDER BY cp.start_date DESC
        """, (contact_id,))
        
        contact['projects'] = [dict(proj) for proj in cursor.fetchall()]
        
        # Extract primary channels for convenience
        for ch in contact['channels']:
            if ch['is_primary']:
                contact[f"primary_{ch['channel_type']}"] = ch['channel_value']
        
        return contact


def _find_by_channel(channel_type: str, value: str) -> Optional[dict]:
    """Find contact by channel type and value."""
    # Clean value
    if channel_type == 'telegram' and value.startswith('@'):
        value = value[1:]  # Remove @ prefix
        channel_type = 'telegram_username'
    elif channel_type == 'telegram' and value.isdigit():
        channel_type = 'telegram_chat_id'
    
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Try exact match first
        cursor.execute("""
            SELECT contact_id FROM contact_channels
            WHERE channel_type = ? AND channel_value = ?
            LIMIT 1
        """, (channel_type, value))
        
        row = cursor.fetchone()
        if row:
            return _get_contact_with_channels(row['contact_id'])
        
        # Try case-insensitive match for email
        if channel_type == 'email':
            cursor.execute("""
                SELECT contact_id FROM contact_channels
                WHERE channel_type = 'email' 
                AND LOWER(channel_value) = LOWER(?)
                LIMIT 1
            """, (value,))
            row = cursor.fetchone()
            if row:
                return _get_contact_with_channels(row['contact_id'])
        
        # Try partial match for phone (remove formatting)
        if channel_type == 'phone':
            digits = re.sub(r'\D', '', value)
            cursor.execute("""
                SELECT contact_id FROM contact_channels
                WHERE channel_type = 'phone'
                AND REPLACE(REPLACE(REPLACE(channel_value, ' ', ''), '-', ''), '+', '') LIKE ?
                LIMIT 1
            """, (f'%{digits}%',))
            row = cursor.fetchone()
            if row:
                return _get_contact_with_channels(row['contact_id'])
    
    return None


def resolve_contact(
    identifier: str,
    context: Optional[dict] = None
) -> Optional[dict]:
    """
    Resolve contact from any identifier.
    
    Identifier types (auto-detected):
        - Email: john@example.com
        - Phone: +996555123456
        - Telegram: @username or 123456789 (chat_id)
        - Teams: 19:xxx@thread.v2
        - Name: "John Doe" or "Altynbek"
    
    Args:
        identifier: Any contact identifier
        context: Optional context for disambiguation:
            - project_id: Prefer contacts from this project
            - organization: Prefer contacts from this org
            - role_code: Prefer contacts with this role
    
    Returns:
        Full contact dict with:
        - Basic info (id, first_name, last_name, organization, etc.)
        - channels: List of all communication channels
        - projects: List of project assignments
        - primary_email, primary_phone, etc.: Convenient access to primary channels
        - None if not found
    
    Examples:
        resolve_contact("Altynbek")  # Name search
        resolve_contact("@altynbek_sydykov")  # Telegram username
        resolve_contact("a.sydykov@aiylbank.kg")  # Email
        resolve_contact("+996700123456")  # Phone
    """
    if not identifier or not identifier.strip():
        return None
    
    identifier = identifier.strip()
    id_type = _detect_identifier_type(identifier)
    
    # Direct channel lookup for specific identifiers
    if id_type == 'email':
        result = _find_by_channel('email', identifier)
        if result:
            result['resolved_by'] = 'email'
            return result
    
    elif id_type == 'telegram':
        result = _find_by_channel('telegram', identifier)
        if result:
            result['resolved_by'] = 'telegram'
            return result
    
    elif id_type == 'phone':
        result = _find_by_channel('phone', identifier)
        if result:
            result['resolved_by'] = 'phone'
            return result
    
    elif id_type == 'teams_chat':
        result = _find_by_channel('teams_chat_id', identifier)
        if result:
            result['resolved_by'] = 'teams'
            return result
    
    # Name search using fuzzy search
    results = contact_search(identifier, limit=5, threshold=70)
    
    if not results:
        return None
    
    # If context provided, try to find best match
    if context and len(results) > 1:
        project_id = context.get('project_id')
        organization = context.get('organization')
        role_code = context.get('role_code')
        
        for r in results:
            contact = _get_contact_with_channels(r['id'])
            if not contact:
                continue
            
            # Check project match
            if project_id:
                project_ids = [p['project_id'] for p in contact.get('projects', [])]
                if project_id in project_ids:
                    contact['resolved_by'] = 'name_with_project_context'
                    return contact
            
            # Check organization match
            if organization and contact.get('organization', '').lower() == organization.lower():
                contact['resolved_by'] = 'name_with_org_context'
                return contact
            
            # Check role match
            if role_code:
                roles = [p['role_code'] for p in contact.get('projects', [])]
                if role_code in roles:
                    contact['resolved_by'] = 'name_with_role_context'
                    return contact
    
    # Return best match (highest score)
    best_match = results[0]
    contact = _get_contact_with_channels(best_match['id'])
    if contact:
        contact['resolved_by'] = 'name'
        contact['match_score'] = best_match.get('match_score', 0)
        contact['matched_field'] = best_match.get('matched_field', 'unknown')
    
    return contact


def get_preferred_channel(
    contact: dict,
    channel_type: str = None,
    for_purpose: str = None
) -> Optional[dict]:
    """
    Get preferred channel for contacting.
    
    Args:
        contact: Contact dict from resolve_contact
        channel_type: Specific type wanted (email, telegram, phone, etc.)
        for_purpose: Purpose hint - 'booking', 'notification', 'visa'
    
    Returns:
        Channel dict with type, value, is_primary
    """
    channels = contact.get('channels', [])
    if not channels:
        return None
    
    # If specific type requested
    if channel_type:
        type_channels = [c for c in channels if c['channel_type'] == channel_type]
        if type_channels:
            # Return primary if exists, otherwise first
            primary = [c for c in type_channels if c['is_primary']]
            return primary[0] if primary else type_channels[0]
        return None
    
    # Check contact preferences
    preferred = contact.get('preferred_channel')
    if preferred:
        pref_channels = [c for c in channels if c['channel_type'] == preferred]
        if pref_channels:
            primary = [c for c in pref_channels if c['is_primary']]
            return primary[0] if primary else pref_channels[0]
    
    # Default priority: email > telegram > phone > teams
    priority = ['email', 'telegram_username', 'telegram_chat_id', 'phone', 'teams_chat_id', 'whatsapp']
    
    for ch_type in priority:
        type_channels = [c for c in channels if c['channel_type'] == ch_type]
        if type_channels:
            primary = [c for c in type_channels if c['is_primary']]
            return primary[0] if primary else type_channels[0]
    
    # Return any primary or first available
    primary = [c for c in channels if c['is_primary']]
    return primary[0] if primary else channels[0]


def resolve_multiple(
    identifiers: list[str],
    context: Optional[dict] = None
) -> dict:
    """
    Resolve multiple contacts at once.
    
    Args:
        identifiers: List of identifiers
        context: Optional context for disambiguation
    
    Returns:
        Dict with:
        - resolved: List of (identifier, contact) tuples
        - unresolved: List of identifiers that couldn't be resolved
        - duplicates: List of identifiers that resolved to same contact
    """
    resolved = []
    unresolved = []
    seen_ids = {}  # contact_id -> first identifier
    duplicates = []
    
    for identifier in identifiers:
        contact = resolve_contact(identifier, context)
        if contact:
            contact_id = contact['id']
            if contact_id in seen_ids:
                duplicates.append({
                    'identifier': identifier,
                    'duplicate_of': seen_ids[contact_id],
                    'contact_id': contact_id
                })
            else:
                seen_ids[contact_id] = identifier
                resolved.append({
                    'identifier': identifier,
                    'contact': contact
                })
        else:
            unresolved.append(identifier)
    
    return {
        'resolved': resolved,
        'unresolved': unresolved,
        'duplicates': duplicates,
        'stats': {
            'total': len(identifiers),
            'resolved_count': len(resolved),
            'unresolved_count': len(unresolved),
            'duplicate_count': len(duplicates)
        }
    }

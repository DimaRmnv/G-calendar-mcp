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


def suggest_enrichment(
    contact_id: int,
    sources: list[str] = None
) -> dict:
    """
    Analyze contact and suggest enrichment actions.
    
    Returns instructions for Claude to call other MCP tools
    (telegram, teams, gmail) to enrich contact data.
    
    Args:
        contact_id: Contact to analyze
        sources: Limit to specific sources ['telegram', 'teams', 'gmail']
                 Default: all available
    
    Returns:
        Dict with:
        - contact_id: Contact ID
        - contact_name: Display name
        - suggestions: List of enrichment instructions
        - already_complete: List of channels that don't need enrichment
    
    Each suggestion contains:
        - type: What will be added (e.g., 'telegram_chat_id')
        - reason: Why this enrichment is suggested
        - tool: MCP tool to call (e.g., 'telegram:search')
        - params: Parameters for the tool call
        - extract: JSONPath to extract value from result
        - save_as: channel_type to save as
    
    Example workflow for Claude:
        1. Call suggest_enrichment(contact_id=1)
        2. For each suggestion, call the specified tool with params
        3. Extract value using the extract path
        4. Call channel_add(contact_id, channel_type=save_as, channel_value=extracted)
    """
    contact = _get_contact_with_channels(contact_id)
    if not contact:
        return {"error": f"Contact {contact_id} not found"}
    
    if sources is None:
        sources = ['telegram', 'teams', 'gmail']
    
    # Build channel lookup
    channels_by_type = {}
    for ch in contact.get('channels', []):
        channels_by_type[ch['channel_type']] = ch['channel_value']
    
    suggestions = []
    already_complete = []
    
    # --- TELEGRAM ---
    if 'telegram' in sources:
        has_username = channels_by_type.get('telegram_username')
        has_chat_id = channels_by_type.get('telegram_chat_id')
        has_user_id = channels_by_type.get('telegram_id')
        
        if has_username and not has_chat_id:
            suggestions.append({
                'type': 'telegram_chat_id',
                'reason': f'Has telegram_username (@{has_username}) but no chat_id for sending messages',
                'tool': 'telegram:search',
                'params': {
                    'query': has_username,
                    'type': 'contacts',
                    'limit': 5
                },
                'extract': 'contacts[0].id',
                'extract_hint': 'Find contact where username matches, take id field',
                'save_as': 'telegram_chat_id'
            })
        
        # telegram_id (user_id) - for private chats same as chat_id
        if has_chat_id and not has_user_id:
            suggestions.append({
                'type': 'telegram_id',
                'reason': f'Has telegram_chat_id ({has_chat_id}) but no telegram_id (user_id)',
                'action': 'copy',
                'note': 'For private chats, user_id == chat_id. Copy the value.',
                'source_channel': 'telegram_chat_id',
                'save_as': 'telegram_id'
            })
        
        # Read recent messages for context
        chat_id_for_messages = has_chat_id or has_user_id
        if chat_id_for_messages:
            suggestions.append({
                'type': 'telegram_recent_messages',
                'reason': f'Read recent messages to understand context with this contact',
                'tool': 'telegram:read_chat',
                'params': {
                    'chat': int(chat_id_for_messages),
                    'limit': 20
                },
                'action': 'context',
                'extract_hint': 'Review messages for additional contact info (phone, email in text)'
            })
        
        # Complete when has all three
        if has_username and has_chat_id and has_user_id:
            already_complete.append('telegram')
    
    # --- TEAMS ---
    if 'teams' in sources:
        has_email = channels_by_type.get('email')
        has_teams_chat = channels_by_type.get('teams_chat_id')
        
        if has_email and not has_teams_chat:
            suggestions.append({
                'type': 'teams_chat_id',
                'reason': f'Has email ({has_email}) but no Teams chat_id for messaging',
                'tool': 'teams:chats',
                'params': {
                    'action': 'search',
                    'query': has_email,
                    'limit': 5
                },
                'extract': 'chats[0].id',
                'extract_hint': 'Find 1:1 chat with this person, take id field',
                'save_as': 'teams_chat_id'
            })
        elif has_teams_chat:
            already_complete.append('teams')
        
        # Also try by name if no email
        if not has_email and not has_teams_chat:
            display_name = contact.get('display_name')
            if display_name:
                suggestions.append({
                    'type': 'teams_chat_id',
                    'reason': f'No email, searching Teams by name ({display_name})',
                    'tool': 'teams:chats',
                    'params': {
                        'action': 'search',
                        'query': display_name,
                        'limit': 5
                    },
                    'extract': 'chats[0].id',
                    'extract_hint': 'Find 1:1 chat matching name, take id field',
                    'save_as': 'teams_chat_id'
                })
    
    # --- GMAIL (future: extract signature info) ---
    if 'gmail' in sources:
        has_email = channels_by_type.get('email')
        has_phone = channels_by_type.get('phone')
        
        # If has email but missing phone/other info, could scan signatures
        if has_email and not has_phone:
            suggestions.append({
                'type': 'phone_from_signature',
                'reason': f'Has email ({has_email}), can extract phone from email signatures',
                'tool': 'google-mail:find_context',
                'params': {
                    'topic': has_email,
                    'max_results': 10
                },
                'extract': 'manual',
                'extract_hint': 'Look for phone numbers in email signatures from this sender',
                'save_as': 'phone'
            })
    
    return {
        'contact_id': contact_id,
        'contact_name': contact.get('display_name'),
        'current_channels': list(channels_by_type.keys()),
        'suggestions': suggestions,
        'already_complete': already_complete,
        'suggestion_count': len(suggestions)
    }


def suggest_new_contacts(
    sources: list[str] = None,
    limit: int = 20,
    period: str = 'month'
) -> dict:
    """
    Suggest new contacts from communication channels.
    
    Returns instructions for Claude to scan Telegram chats, Teams chats,
    Gmail correspondents, and Calendar attendees to find people not yet
    in the contacts database.
    
    Args:
        sources: Which sources to scan ['telegram', 'teams', 'gmail', 'calendar']
                 Default: all available
        limit: Max suggestions per source (base limit, auto-scaled by period)
        period: Time period to scan:
                - 'day' or 'today': Last 24 hours
                - 'week': Last 7 days  
                - 'month': Last 30 days (default)
                - 'quarter' or '3months': Last 90 days
                - 'year': Last 365 days
                Note: Telegram/Teams don't support date filtering, so limit is
                      auto-increased for longer periods.
    
    Returns:
        Dict with scan instructions for each source.
        Claude should execute these, then call contact_add for new contacts.
    
    Workflow:
        1. Claude calls suggest_new_contacts()
        2. Claude executes each scan instruction
        3. For each result, Claude checks if contact exists (contact_resolve)
        4. If not exists, Claude calls contact_add + channel_add
    """
    if sources is None:
        sources = ['telegram', 'teams', 'gmail', 'calendar']
    
    # Normalize period
    period_map = {
        'day': 'today',
        'today': 'today',
        'week': 'week',
        'month': 'month',
        'quarter': 'quarter',
        '3months': 'quarter',
        'year': 'year'
    }
    period = period_map.get(period.lower(), 'month')
    
    # Auto-scale limit for sources without date filtering (Telegram, Teams)
    # Longer period = need more chats to cover timeframe
    limit_multiplier = {
        'today': 1,
        'week': 2,
        'month': 3,
        'quarter': 5,
        'year': 10
    }
    scaled_limit = min(limit * limit_multiplier.get(period, 3), 100)  # Cap at 100
    
    # Gmail/Calendar period mapping
    gmail_period = 'month' if period in ('quarter', 'year') else period
    # Note: Gmail analyze_inbox only supports today/week/month
    # For quarter/year, we'll use month and note limitation
    
    # Calendar uses time_min/time_max for precise control
    from datetime import datetime, timedelta
    now = datetime.now()
    period_days = {
        'today': 1,
        'week': 7,
        'month': 30,
        'quarter': 90,
        'year': 365
    }
    days_back = period_days.get(period, 30)
    time_min = (now - timedelta(days=days_back)).strftime('%Y-%m-%dT00:00:00')
    
    scans = []
    
    # --- TELEGRAM ---
    if 'telegram' in sources:
        scans.append({
            'source': 'telegram',
            'description': f'Scan recent Telegram chats ({period}, limit {scaled_limit})',
            'tool': 'telegram:list_chats',
            'params': {
                'limit': scaled_limit,
                'filter': 'private'  # Only 1:1 chats, not groups
            },
            'extract_fields': {
                'user_id': 'chats[].id',  # Same as chat_id for private chats
                'name': 'chats[].name',
                'username': 'chats[].username',
                'phone': 'chats[].phone'
            },
            'create_contact': {
                'channels_to_add': [
                    {'type': 'telegram_id', 'value_from': 'id', 'note': 'User ID'},
                    {'type': 'telegram_chat_id', 'value_from': 'id', 'note': 'Same as user_id for private'},
                    {'type': 'telegram_username', 'value_from': 'username', 'if_present': True}
                ],
                'first_name_from': 'name',
                'note': 'For private chats, user_id == chat_id'
            },
            'period_note': 'Telegram API has no date filter; using increased limit to cover period'
        })
    
    # --- TEAMS ---
    if 'teams' in sources:
        scans.append({
            'source': 'teams',
            'description': f'Scan recent Teams 1:1 chats ({period}, limit {scaled_limit})',
            'tool': 'teams:chats',
            'params': {
                'action': 'list',
                'filter': 'oneOnOne',
                'limit': scaled_limit
            },
            'extract_fields': {
                'chat_id': 'chats[].id',
                'name': 'chats[].name'
            },
            'create_contact': {
                'channels_to_add': [
                    {'type': 'teams_chat_id', 'value_from': 'id'}
                ],
                'first_name_from': 'name',
                'enrichment_step': 'Call manage_chat(action="info", chat_id=id) to get email'
            },
            'period_note': 'Teams API has no date filter; using increased limit to cover period'
        })
    
    # --- GMAIL ---
    if 'gmail' in sources:
        gmail_note = None
        if period in ('quarter', 'year'):
            gmail_note = f'Gmail analyze_inbox max period is month; requested {period}. Consider multiple calls or search_emails with date range.'
        
        scans.append({
            'source': 'gmail',
            'description': f'Scan email correspondents ({gmail_period})',
            'tool': 'google-mail:analyze_inbox',
            'params': {
                'period': gmail_period
            },
            'extract_fields': {
                'email': 'top_senders[].email',
                'name': 'top_senders[].name',
                'count': 'top_senders[].count'
            },
            'create_contact': {
                'channels_to_add': [
                    {'type': 'email', 'value_from': 'email', 'is_primary': True}
                ],
                'first_name_from': 'name',
                'enrichment_step': 'Check signatures via find_context for phone'
            },
            'period_note': gmail_note
        })
    
    # --- CALENDAR ---
    if 'calendar' in sources:
        # Calendar supports precise time_min for any period
        cal_max_results = min(50 * limit_multiplier.get(period, 3), 250)
        
        scans.append({
            'source': 'calendar',
            'description': f'Scan meeting attendees ({period}, last {days_back} days)',
            'tool': 'google-calendar:list_events',
            'params': {
                'time_min': time_min,
                'max_results': cal_max_results
            },
            'post_process': 'For each event with attendees>0, call get_event to get attendees list',
            'extract_fields': {
                'email': 'attendees[].email',
                'name': 'attendees[].displayName',
                'response': 'attendees[].responseStatus'
            },
            'create_contact': {
                'channels_to_add': [
                    {'type': 'email', 'value_from': 'email', 'is_primary': True}
                ],
                'first_name_from': 'displayName',
                'skip_conditions': ['Skip self email', 'Deduplicate across events']
            },
            'period_note': f'Calendar supports exact date range: {time_min} to now'
        })
    
    return {
        'scans': scans,
        'scan_count': len(scans),
        'period': period,
        'period_days': days_back,
        'scaled_limit': scaled_limit,
        'workflow': [
            '1. Execute each scan tool with params',
            '2. For each person found, call contact_resolve(email or name)',
            '3. If not found (null), create new contact:',
            '   - contact_add(first_name, last_name, ...)',
            '   - channel_add(contact_id, channel_type, channel_value)',
            '4. Return summary of new contacts created'
        ],
        'deduplication_note': 'Always check contact_resolve before creating to avoid duplicates',
        'retry_hint': 'If not enough results, retry with period="quarter" or period="year"'
    }


def contact_brief(
    contact_id: int,
    days_back: int = 7,
    days_forward: int = 7
) -> dict:
    """
    Generate activity brief for a contact across all communication channels.
    
    Provides a unified view of recent interactions:
    - Telegram: Recent messages from chat history
    - Teams: Recent messages from chat history
    - Gmail: Recent emails sent/received
    - Calendar: Past meetings + upcoming events with this contact
    
    Args:
        contact_id: Contact to brief
        days_back: Days to look back for activity (default 7)
        days_forward: Days to look forward for calendar events (default 7)
    
    Returns:
        Dict with:
        - contact: Basic contact info with all channels
        - available_channels: Channels grouped by type for fetching
        - fetch_instructions: List of tool calls for Claude to execute
        - aggregation_hints: How to present the aggregated data
    
    Workflow for Claude:
        1. Call contact_brief(contact_id, days_back, days_forward)
        2. Execute each fetch instruction in parallel
        3. Aggregate results into unified timeline
        4. Present summary: recent activity + upcoming events
    """
    contact = _get_contact_with_channels(contact_id)
    if not contact:
        return {"error": f"Contact {contact_id} not found"}
    
    from datetime import datetime, timedelta
    now = datetime.now()
    past_date = (now - timedelta(days=days_back)).strftime('%Y-%m-%dT00:00:00')
    future_date = (now + timedelta(days=days_forward)).strftime('%Y-%m-%dT23:59:59')
    past_date_iso = (now - timedelta(days=days_back)).strftime('%Y-%m-%d')
    
    # Group channels by type
    channels_by_type = {}
    for ch in contact.get('channels', []):
        ch_type = ch['channel_type']
        if ch_type not in channels_by_type:
            channels_by_type[ch_type] = []
        channels_by_type[ch_type].append(ch)
    
    # Build fetch instructions
    fetch_instructions = []
    
    # --- TELEGRAM ---
    telegram_chat_id = channels_by_type.get('telegram_chat_id', [{}])[0].get('channel_value')
    telegram_id = channels_by_type.get('telegram_id', [{}])[0].get('channel_value')
    chat_id_for_telegram = telegram_chat_id or telegram_id
    
    if chat_id_for_telegram:
        # Calculate message limit based on days_back
        msg_limit = min(days_back * 10, 100)  # ~10 messages per day, max 100
        fetch_instructions.append({
            'source': 'telegram',
            'priority': 1,
            'description': f'Recent Telegram messages (last {days_back} days)',
            'tool': 'telegram:read_chat',
            'params': {
                'chat': int(chat_id_for_telegram),
                'limit': msg_limit,
                'include_info': True
            },
            'filter_hint': f'Filter messages where date >= {past_date_iso}',
            'extract': {
                'messages': 'messages[]',
                'fields': ['id', 'date', 'text', 'out']
            },
            'presentation': 'Show as timeline with date, direction (in/out), snippet'
        })
    
    # --- TEAMS ---
    teams_chat_id = channels_by_type.get('teams_chat_id', [{}])[0].get('channel_value')
    
    if teams_chat_id:
        msg_limit = min(days_back * 5, 50)  # ~5 messages per day, max 50
        fetch_instructions.append({
            'source': 'teams',
            'priority': 1,
            'description': f'Recent Teams messages (last {days_back} days)',
            'tool': 'teams:read_messages',
            'params': {
                'chat_id': teams_chat_id,
                'limit': msg_limit
            },
            'filter_hint': f'Filter messages where date >= {past_date_iso}',
            'extract': {
                'messages': 'messages[]',
                'fields': ['id', 'date', 'sender', 'text']
            },
            'presentation': 'Show as timeline with date, sender, snippet'
        })
    
    # --- GMAIL ---
    emails = channels_by_type.get('email', [])
    primary_email = next((e['channel_value'] for e in emails if e.get('is_primary')), None)
    if not primary_email and emails:
        primary_email = emails[0]['channel_value']
    
    if primary_email:
        # Search for emails from/to this contact
        fetch_instructions.append({
            'source': 'gmail',
            'priority': 1,
            'description': f'Recent emails with {primary_email} (last {days_back} days)',
            'tool': 'google-mail:find_context',
            'params': {
                'topic': primary_email,
                'period_days': days_back,
                'max_results': 20,
                'include_sent': True
            },
            'extract': {
                'timeline': 'timeline[]',
                'fields': ['date', 'from', 'to', 'subject', 'snippet']
            },
            'presentation': 'Show as email thread summaries with subject and direction'
        })
        
        # Alternative: direct search if find_context not available
        fetch_instructions.append({
            'source': 'gmail_alt',
            'priority': 2,
            'description': f'Alternative: Search emails with {primary_email}',
            'tool': 'google-mail:search_emails',
            'params': {
                'query': f'from:{primary_email} OR to:{primary_email}',
                'period': 'week' if days_back <= 7 else 'month',
                'max_results': 20
            },
            'note': 'Use if find_context returns empty or errors'
        })
    
    # --- CALENDAR (past) ---
    if primary_email:
        fetch_instructions.append({
            'source': 'calendar_past',
            'priority': 1,
            'description': f'Past meetings with {contact.get("display_name")} (last {days_back} days)',
            'tool': 'google-calendar:search_events',
            'params': {
                'query': primary_email,
                'time_min': past_date,
                'time_max': now.strftime('%Y-%m-%dT%H:%M:%S'),
                'max_results': 20
            },
            'extract': {
                'events': 'events[]',
                'fields': ['id', 'summary', 'start', 'end', 'status']
            },
            'presentation': 'Show as "Past meetings" section with date and event title'
        })
        
        # --- CALENDAR (upcoming) ---
        fetch_instructions.append({
            'source': 'calendar_upcoming',
            'priority': 1,
            'description': f'Upcoming meetings with {contact.get("display_name")} (next {days_forward} days)',
            'tool': 'google-calendar:search_events',
            'params': {
                'query': primary_email,
                'time_min': now.strftime('%Y-%m-%dT%H:%M:%S'),
                'time_max': future_date,
                'max_results': 20
            },
            'extract': {
                'events': 'events[]',
                'fields': ['id', 'summary', 'start', 'end', 'status', 'htmlLink']
            },
            'presentation': 'Show as "Upcoming meetings" section with date, time, title, link'
        })
    else:
        # No email - search by name
        display_name = contact.get('display_name', '')
        if display_name:
            fetch_instructions.append({
                'source': 'calendar_past',
                'priority': 2,
                'description': f'Past meetings mentioning "{display_name}" (last {days_back} days)',
                'tool': 'google-calendar:search_events',
                'params': {
                    'query': display_name,
                    'time_min': past_date,
                    'time_max': now.strftime('%Y-%m-%dT%H:%M:%S'),
                    'max_results': 10
                },
                'note': 'Name-based search less reliable than email; may include false positives'
            })
            
            fetch_instructions.append({
                'source': 'calendar_upcoming',
                'priority': 2,
                'description': f'Upcoming meetings mentioning "{display_name}" (next {days_forward} days)',
                'tool': 'google-calendar:search_events',
                'params': {
                    'query': display_name,
                    'time_min': now.strftime('%Y-%m-%dT%H:%M:%S'),
                    'time_max': future_date,
                    'max_results': 10
                },
                'note': 'Name-based search less reliable than email'
            })
    
    # Count available channels
    available_sources = []
    if chat_id_for_telegram:
        available_sources.append('telegram')
    if teams_chat_id:
        available_sources.append('teams')
    if primary_email:
        available_sources.append('gmail')
        available_sources.append('calendar')
    
    return {
        'contact': {
            'id': contact['id'],
            'display_name': contact.get('display_name'),
            'organization': contact.get('organization'),
            'job_title': contact.get('job_title'),
            'country': contact.get('country'),
            'preferred_channel': contact.get('preferred_channel'),
            'projects': contact.get('projects', [])
        },
        'available_channels': channels_by_type,
        'available_sources': available_sources,
        'time_range': {
            'past': f'{days_back} days back ({past_date_iso})',
            'future': f'{days_forward} days forward',
            'past_date': past_date,
            'future_date': future_date
        },
        'fetch_instructions': fetch_instructions,
        'instruction_count': len([f for f in fetch_instructions if f.get('priority') == 1]),
        'workflow': [
            '1. Execute all priority=1 fetch instructions in parallel',
            '2. If any fail, try priority=2 alternatives',
            '3. Filter results by date range if tool doesn\'t support it natively',
            '4. Aggregate into unified brief with sections:',
            '   - Contact summary (from contact field)',
            '   - Upcoming events (calendar_upcoming)',
            '   - Recent activity timeline (merge telegram + teams + gmail by date)',
            '   - Past meetings (calendar_past)',
            '5. Highlight: last interaction date, next scheduled meeting, pending items'
        ],
        'aggregation_hints': {
            'timeline_merge': 'Sort all messages/emails by date descending',
            'highlight_unanswered': 'Flag incoming messages without outgoing response within 24h',
            'meeting_context': 'For upcoming meetings, include last email/message as context',
            'summary_stats': 'Count: messages exchanged, emails, meetings in period'
        }
    }


def contact_brief(
    contact_id: int,
    days_back: int = 7,
    days_forward: int = 7
) -> dict:
    """
    Generate activity brief for a contact across all communication channels.
    
    Provides a unified view of recent interactions:
    - Telegram: Recent messages from chat history
    - Teams: Recent messages from chat history
    - Gmail: Recent emails sent/received
    - Calendar: Past meetings + upcoming events with this contact
    
    Args:
        contact_id: Contact to brief
        days_back: Days to look back for activity (default 7)
        days_forward: Days to look forward for calendar events (default 7)
    
    Returns:
        Dict with:
        - contact: Basic contact info with all channels
        - available_channels: Channels grouped by type for fetching
        - fetch_instructions: List of tool calls for Claude to execute
        - aggregation_hints: How to present the aggregated data
    
    Workflow for Claude:
        1. Call contact_brief(contact_id, days_back, days_forward)
        2. Execute each fetch instruction in parallel
        3. Aggregate results into unified timeline
        4. Present summary: recent activity + upcoming events
    """
    contact = _get_contact_with_channels(contact_id)
    if not contact:
        return {"error": f"Contact {contact_id} not found"}
    
    from datetime import datetime, timedelta
    now = datetime.now()
    past_date = (now - timedelta(days=days_back)).strftime('%Y-%m-%dT00:00:00')
    future_date = (now + timedelta(days=days_forward)).strftime('%Y-%m-%dT23:59:59')
    past_date_iso = (now - timedelta(days=days_back)).strftime('%Y-%m-%d')
    
    # Group channels by type
    channels_by_type = {}
    for ch in contact.get('channels', []):
        ch_type = ch['channel_type']
        if ch_type not in channels_by_type:
            channels_by_type[ch_type] = []
        channels_by_type[ch_type].append(ch)
    
    # Build fetch instructions
    fetch_instructions = []
    
    # --- TELEGRAM ---
    telegram_chat_id = channels_by_type.get('telegram_chat_id', [{}])[0].get('channel_value')
    telegram_id = channels_by_type.get('telegram_id', [{}])[0].get('channel_value')
    chat_id_for_telegram = telegram_chat_id or telegram_id
    
    if chat_id_for_telegram:
        # Calculate message limit based on days_back
        msg_limit = min(days_back * 10, 100)  # ~10 messages per day, max 100
        fetch_instructions.append({
            'source': 'telegram',
            'priority': 1,
            'description': f'Recent Telegram messages (last {days_back} days)',
            'tool': 'telegram:read_chat',
            'params': {
                'chat': int(chat_id_for_telegram),
                'limit': msg_limit,
                'include_info': True
            },
            'filter_hint': f'Filter messages where date >= {past_date_iso}',
            'extract': {
                'messages': 'messages[]',
                'fields': ['id', 'date', 'text', 'out']
            },
            'presentation': 'Show as timeline with date, direction (in/out), snippet'
        })
    
    # --- TEAMS ---
    teams_chat_id = channels_by_type.get('teams_chat_id', [{}])[0].get('channel_value')
    
    if teams_chat_id:
        msg_limit = min(days_back * 5, 50)  # ~5 messages per day, max 50
        fetch_instructions.append({
            'source': 'teams',
            'priority': 1,
            'description': f'Recent Teams messages (last {days_back} days)',
            'tool': 'teams:read_messages',
            'params': {
                'chat_id': teams_chat_id,
                'limit': msg_limit
            },
            'filter_hint': f'Filter messages where date >= {past_date_iso}',
            'extract': {
                'messages': 'messages[]',
                'fields': ['id', 'date', 'sender', 'text']
            },
            'presentation': 'Show as timeline with date, sender, snippet'
        })
    
    # --- GMAIL ---
    emails = channels_by_type.get('email', [])
    primary_email = next((e['channel_value'] for e in emails if e.get('is_primary')), None)
    if not primary_email and emails:
        primary_email = emails[0]['channel_value']
    
    if primary_email:
        # Search for emails from/to this contact
        fetch_instructions.append({
            'source': 'gmail',
            'priority': 1,
            'description': f'Recent emails with {primary_email} (last {days_back} days)',
            'tool': 'google-mail:find_context',
            'params': {
                'topic': primary_email,
                'period_days': days_back,
                'max_results': 20,
                'include_sent': True
            },
            'extract': {
                'timeline': 'timeline[]',
                'fields': ['date', 'from', 'to', 'subject', 'snippet']
            },
            'presentation': 'Show as email thread summaries with subject and direction'
        })
        
        # Alternative: direct search if find_context not available
        fetch_instructions.append({
            'source': 'gmail_alt',
            'priority': 2,
            'description': f'Alternative: Search emails with {primary_email}',
            'tool': 'google-mail:search_emails',
            'params': {
                'query': f'from:{primary_email} OR to:{primary_email}',
                'period': 'week' if days_back <= 7 else 'month',
                'max_results': 20
            },
            'note': 'Use if find_context returns empty or errors'
        })
    
    # --- CALENDAR (past) ---
    if primary_email:
        fetch_instructions.append({
            'source': 'calendar_past',
            'priority': 1,
            'description': f'Past meetings with {contact.get("display_name")} (last {days_back} days)',
            'tool': 'google-calendar:search_events',
            'params': {
                'query': primary_email,
                'time_min': past_date,
                'time_max': now.strftime('%Y-%m-%dT%H:%M:%S'),
                'max_results': 20
            },
            'extract': {
                'events': 'events[]',
                'fields': ['id', 'summary', 'start', 'end', 'status']
            },
            'presentation': 'Show as "Past meetings" section with date and event title'
        })
        
        # --- CALENDAR (upcoming) ---
        fetch_instructions.append({
            'source': 'calendar_upcoming',
            'priority': 1,
            'description': f'Upcoming meetings with {contact.get("display_name")} (next {days_forward} days)',
            'tool': 'google-calendar:search_events',
            'params': {
                'query': primary_email,
                'time_min': now.strftime('%Y-%m-%dT%H:%M:%S'),
                'time_max': future_date,
                'max_results': 20
            },
            'extract': {
                'events': 'events[]',
                'fields': ['id', 'summary', 'start', 'end', 'status', 'htmlLink']
            },
            'presentation': 'Show as "Upcoming meetings" section with date, time, title, link'
        })
    else:
        # No email - search by name
        display_name = contact.get('display_name', '')
        if display_name:
            fetch_instructions.append({
                'source': 'calendar_past',
                'priority': 2,
                'description': f'Past meetings mentioning "{display_name}" (last {days_back} days)',
                'tool': 'google-calendar:search_events',
                'params': {
                    'query': display_name,
                    'time_min': past_date,
                    'time_max': now.strftime('%Y-%m-%dT%H:%M:%S'),
                    'max_results': 10
                },
                'note': 'Name-based search less reliable than email; may include false positives'
            })
            
            fetch_instructions.append({
                'source': 'calendar_upcoming',
                'priority': 2,
                'description': f'Upcoming meetings mentioning "{display_name}" (next {days_forward} days)',
                'tool': 'google-calendar:search_events',
                'params': {
                    'query': display_name,
                    'time_min': now.strftime('%Y-%m-%dT%H:%M:%S'),
                    'time_max': future_date,
                    'max_results': 10
                },
                'note': 'Name-based search less reliable than email'
            })
    
    # Count available channels
    available_sources = []
    if chat_id_for_telegram:
        available_sources.append('telegram')
    if teams_chat_id:
        available_sources.append('teams')
    if primary_email:
        available_sources.append('gmail')
        available_sources.append('calendar')
    
    return {
        'contact': {
            'id': contact['id'],
            'display_name': contact.get('display_name'),
            'organization': contact.get('organization'),
            'job_title': contact.get('job_title'),
            'country': contact.get('country'),
            'preferred_channel': contact.get('preferred_channel'),
            'projects': contact.get('projects', [])
        },
        'available_channels': channels_by_type,
        'available_sources': available_sources,
        'time_range': {
            'past': f'{days_back} days back ({past_date_iso})',
            'future': f'{days_forward} days forward',
            'past_date': past_date,
            'future_date': future_date
        },
        'fetch_instructions': fetch_instructions,
        'instruction_count': len([f for f in fetch_instructions if f.get('priority') == 1]),
        'workflow': [
            '1. Execute all priority=1 fetch instructions in parallel',
            '2. If any fail, try priority=2 alternatives',
            '3. Filter results by date range if tool doesn\'t support it natively',
            '4. Aggregate into unified brief with sections:',
            '   - Contact summary (from contact field)',
            '   - Upcoming events (calendar_upcoming)',
            '   - Recent activity timeline (merge telegram + teams + gmail by date)',
            '   - Past meetings (calendar_past)',
            '5. Highlight: last interaction date, next scheduled meeting, pending items'
        ],
        'aggregation_hints': {
            'timeline_merge': 'Sort all messages/emails by date descending',
            'highlight_unanswered': 'Flag incoming messages without outgoing response within 24h',
            'meeting_context': 'For upcoming meetings, include last email/message as context',
            'summary_stats': 'Count: messages exchanged, emails, meetings in period'
        }
    }

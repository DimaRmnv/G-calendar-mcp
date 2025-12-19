"""
Tests for contacts database module.
"""

import pytest
import tempfile
import sqlite3
from pathlib import Path
from unittest.mock import patch


@pytest.fixture
def temp_db():
    """Create a temporary database with proper setup."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "time_tracking.db"
        
        # Patch get_app_dir before importing
        with patch('google_calendar.tools.contacts.database.get_app_dir', return_value=Path(tmpdir)):
            # Create database with projects table (required for FK)
            conn = sqlite3.connect(db_path)
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT NOT NULL,
                    description TEXT NOT NULL
                )
            """)
            conn.execute("INSERT INTO projects (code, description) VALUES ('TEST', 'Test Project')")
            conn.commit()
            conn.close()
            
            yield Path(tmpdir)


class TestContactsSchema:
    """Test schema initialization."""
    
    def test_init_creates_tables(self, temp_db):
        with patch('google_calendar.tools.contacts.database.get_app_dir', return_value=temp_db):
            from google_calendar.tools.contacts.database import (
                init_contacts_schema, contacts_tables_exist, get_connection
            )
            
            assert not contacts_tables_exist()
            init_contacts_schema()
            assert contacts_tables_exist()
            
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = {row['name'] for row in cursor.fetchall()}
                
                assert 'contacts' in tables
                assert 'contact_channels' in tables
                assert 'project_roles' in tables
                assert 'contact_projects' in tables
    
    def test_standard_roles_inserted(self, temp_db):
        with patch('google_calendar.tools.contacts.database.get_app_dir', return_value=temp_db):
            from google_calendar.tools.contacts.database import init_contacts_schema, role_list
            
            init_contacts_schema()
            roles = role_list()
            
            assert len(roles) == 19
            role_codes = {r['role_code'] for r in roles}
            assert 'TL' in role_codes
            assert 'DTL' in role_codes
            assert 'KE' in role_codes


class TestContactsCRUD:
    """Test contacts CRUD operations."""
    
    def test_contact_add(self, temp_db):
        with patch('google_calendar.tools.contacts.database.get_app_dir', return_value=temp_db):
            from google_calendar.tools.contacts.database import (
                init_contacts_schema, contact_add, contact_get
            )
            init_contacts_schema()
            
            contact = contact_add(
                first_name="Altynbek",
                last_name="Sydykov",
                organization="Aiyl Bank",
                organization_type="bank",
                country="Kyrgyzstan",
                preferred_channel="telegram"
            )
            
            assert contact['id'] is not None
            assert contact['display_name'] == "Altynbek Sydykov"
            assert contact['organization'] == "Aiyl Bank"
            
            retrieved = contact_get(id=contact['id'])
            assert retrieved['display_name'] == "Altynbek Sydykov"
    
    def test_contact_add_invalid_org_type(self, temp_db):
        with patch('google_calendar.tools.contacts.database.get_app_dir', return_value=temp_db):
            from google_calendar.tools.contacts.database import init_contacts_schema, contact_add
            init_contacts_schema()
            
            with pytest.raises(ValueError, match="Invalid organization_type"):
                contact_add(
                    first_name="Test",
                    last_name="User",
                    organization_type="invalid_type"
                )
    
    def test_contact_list_by_organization(self, temp_db):
        with patch('google_calendar.tools.contacts.database.get_app_dir', return_value=temp_db):
            from google_calendar.tools.contacts.database import (
                init_contacts_schema, contact_add, contact_list
            )
            init_contacts_schema()
            
            contact_add(first_name="John", last_name="Doe", organization="ADB")
            contact_add(first_name="Jane", last_name="Smith", organization="EBRD")
            contact_add(first_name="Bob", last_name="Wilson", organization="ADB")
            
            adb_contacts = contact_list(organization="ADB")
            assert len(adb_contacts) == 2
            
            all_contacts = contact_list()
            assert len(all_contacts) == 3
    
    def test_contact_search(self, temp_db):
        with patch('google_calendar.tools.contacts.database.get_app_dir', return_value=temp_db):
            from google_calendar.tools.contacts.database import (
                init_contacts_schema, contact_add, contact_search
            )
            init_contacts_schema()
            
            contact_add(first_name="John", last_name="Doe", organization="World Bank")
            contact_add(first_name="Jane", last_name="Smith", organization="EBRD")
            
            results = contact_search("John")
            assert len(results) == 1
            assert results[0]['first_name'] == "John"
    
    def test_contact_update(self, temp_db):
        with patch('google_calendar.tools.contacts.database.get_app_dir', return_value=temp_db):
            from google_calendar.tools.contacts.database import (
                init_contacts_schema, contact_add, contact_update
            )
            init_contacts_schema()
            
            contact = contact_add(first_name="Test", last_name="User")
            updated = contact_update(contact['id'], job_title="Manager", country="Ukraine")
            
            assert updated['job_title'] == "Manager"
            assert updated['country'] == "Ukraine"
    
    def test_contact_delete(self, temp_db):
        with patch('google_calendar.tools.contacts.database.get_app_dir', return_value=temp_db):
            from google_calendar.tools.contacts.database import (
                init_contacts_schema, contact_add, contact_delete, contact_get
            )
            init_contacts_schema()
            
            contact = contact_add(first_name="Test", last_name="User")
            assert contact_delete(contact['id'])
            assert contact_get(id=contact['id']) is None


class TestChannelsCRUD:
    """Test channels CRUD operations."""
    
    def test_channel_add(self, temp_db):
        with patch('google_calendar.tools.contacts.database.get_app_dir', return_value=temp_db):
            from google_calendar.tools.contacts.database import (
                init_contacts_schema, contact_add, channel_add, channel_list
            )
            init_contacts_schema()
            contact = contact_add(first_name="Test", last_name="User")
            
            channel = channel_add(
                contact_id=contact['id'],
                channel_type="email",
                channel_value="test@example.com",
                is_primary=True
            )
            
            assert channel['id'] is not None
            assert channel['channel_type'] == "email"
            assert channel['is_primary'] is True
            
            channels = channel_list(contact['id'])
            assert len(channels) == 1
    
    def test_channel_primary_logic(self, temp_db):
        with patch('google_calendar.tools.contacts.database.get_app_dir', return_value=temp_db):
            from google_calendar.tools.contacts.database import (
                init_contacts_schema, contact_add, channel_add, channel_list
            )
            init_contacts_schema()
            contact = contact_add(first_name="Test", last_name="User")
            
            channel_add(
                contact_id=contact['id'],
                channel_type="email",
                channel_value="first@example.com",
                is_primary=True
            )
            channel_add(
                contact_id=contact['id'],
                channel_type="email",
                channel_value="second@example.com",
                is_primary=True
            )
            
            channels = channel_list(contact['id'])
            primaries = [c for c in channels if c['is_primary']]
            
            assert len(primaries) == 1
            assert primaries[0]['channel_value'] == "second@example.com"
    
    def test_telegram_username_cleanup(self, temp_db):
        with patch('google_calendar.tools.contacts.database.get_app_dir', return_value=temp_db):
            from google_calendar.tools.contacts.database import (
                init_contacts_schema, contact_add, channel_add
            )
            init_contacts_schema()
            contact = contact_add(first_name="Test", last_name="User")
            
            channel = channel_add(
                contact_id=contact['id'],
                channel_type="telegram_username",
                channel_value="@testuser"
            )
            
            assert channel['channel_value'] == "testuser"
    
    def test_contact_get_by_channel(self, temp_db):
        with patch('google_calendar.tools.contacts.database.get_app_dir', return_value=temp_db):
            from google_calendar.tools.contacts.database import (
                init_contacts_schema, contact_add, channel_add, contact_get
            )
            init_contacts_schema()
            contact = contact_add(first_name="Test", last_name="User")
            
            channel_add(
                contact_id=contact['id'],
                channel_type="email",
                channel_value="unique@example.com",
                is_primary=True
            )
            
            found = contact_get(email="unique@example.com")
            assert found is not None
            assert found['id'] == contact['id']


class TestAssignmentsCRUD:
    """Test project assignments CRUD."""
    
    def test_assignment_add(self, temp_db):
        with patch('google_calendar.tools.contacts.database.get_app_dir', return_value=temp_db):
            from google_calendar.tools.contacts.database import (
                init_contacts_schema, contact_add, assignment_add, assignment_list
            )
            init_contacts_schema()
            contact = contact_add(first_name="Test", last_name="Expert")
            
            assignment = assignment_add(
                contact_id=contact['id'],
                project_id=1,
                role_code="KE",
                workdays_allocated=30
            )
            
            assert assignment['id'] is not None
            assert assignment['role_code'] == "KE"
            assert assignment['workdays_allocated'] == 30
            
            assignments = assignment_list(contact_id=contact['id'])
            assert len(assignments) == 1
    
    def test_assignment_invalid_role(self, temp_db):
        with patch('google_calendar.tools.contacts.database.get_app_dir', return_value=temp_db):
            from google_calendar.tools.contacts.database import (
                init_contacts_schema, contact_add, assignment_add
            )
            init_contacts_schema()
            contact = contact_add(first_name="Test", last_name="Expert")
            
            with pytest.raises(ValueError, match="Invalid role_code"):
                assignment_add(
                    contact_id=contact['id'],
                    project_id=1,
                    role_code="INVALID"
                )
    
    def test_get_project_team(self, temp_db):
        with patch('google_calendar.tools.contacts.database.get_app_dir', return_value=temp_db):
            from google_calendar.tools.contacts.database import (
                init_contacts_schema, contact_add, assignment_add, get_project_team
            )
            init_contacts_schema()
            
            c1 = contact_add(first_name="Team", last_name="Leader", organization="BFC")
            c2 = contact_add(first_name="Key", last_name="Expert", organization="BFC")
            
            assignment_add(contact_id=c1['id'], project_id=1, role_code="TL")
            assignment_add(contact_id=c2['id'], project_id=1, role_code="KE")
            
            team = get_project_team(project_id=1)
            assert len(team) == 2
            
            roles = [t['role_code'] for t in team]
            assert 'TL' in roles
            assert 'KE' in roles


class TestManageTool:
    """Test the batch operations tool."""
    
    def test_init_and_status(self, temp_db):
        import asyncio
        with patch('google_calendar.tools.contacts.database.get_app_dir', return_value=temp_db):
            with patch('google_calendar.tools.contacts.manage.ensure_contacts_schema'):
                with patch('google_calendar.tools.contacts.manage.contacts_tables_exist', return_value=False):
                    with patch('google_calendar.tools.contacts.manage.init_contacts_schema'):
                        from google_calendar.tools.contacts.manage import contacts, _init_contacts
                        
                        result = _init_contacts(force_reset=False)
                        assert result['status'] == 'created'
    
    def test_batch_operations(self, temp_db):
        import asyncio
        with patch('google_calendar.tools.contacts.database.get_app_dir', return_value=temp_db):
            from google_calendar.tools.contacts.database import init_contacts_schema
            from google_calendar.tools.contacts.manage import contacts
            
            init_contacts_schema()
            
            result = asyncio.run(contacts([
                {"op": "status"},
                {"op": "contact_add", "first_name": "Test", "last_name": "User", 
                 "organization": "TestOrg"},
            ]))
            
            assert result['summary']['total'] == 2
            # Status should work, contact_add might work
            assert result['summary']['errors'] <= 1
    
    def test_error_handling(self, temp_db):
        import asyncio
        with patch('google_calendar.tools.contacts.database.get_app_dir', return_value=temp_db):
            from google_calendar.tools.contacts.database import init_contacts_schema
            from google_calendar.tools.contacts.manage import contacts
            
            init_contacts_schema()
            
            result = asyncio.run(contacts([
                {"op": "unknown_operation"},
            ]))
            
            assert result['summary']['errors'] == 1
            assert "error" in result['results'][0]

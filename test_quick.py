#!/usr/bin/env python
"""Quick test script for contacts module."""

import tempfile
import sqlite3
from pathlib import Path
from unittest.mock import patch

# Create temp dir and db
tmpdir = tempfile.mkdtemp()
db_path = Path(tmpdir) / 'time_tracking.db'

print(f"Using temp dir: {tmpdir}")

# Create projects table first
conn = sqlite3.connect(db_path)
conn.execute('CREATE TABLE projects (id INTEGER PRIMARY KEY, code TEXT, description TEXT)')
conn.execute('INSERT INTO projects VALUES (1, "TEST", "Test")')
conn.commit()
conn.close()

print("Created projects table")

# Now patch and test
with patch('google_calendar.utils.config.get_app_dir', return_value=Path(tmpdir)):
    with patch('google_calendar.tools.contacts.database.get_app_dir', return_value=Path(tmpdir)):
        from google_calendar.tools.contacts.database import (
            init_contacts_schema, contact_add, contact_get, contacts_tables_exist
        )
        
        print(f"Tables exist before init: {contacts_tables_exist()}")
        init_contacts_schema()
        print(f"Tables exist after init: {contacts_tables_exist()}")
        
        c = contact_add(first_name='Test', last_name='User', organization='Org')
        print(f'Created contact: {c}')
        
        if c:
            retrieved = contact_get(id=c['id'])
            print(f'Retrieved: {retrieved}')
        
print("Test complete!")

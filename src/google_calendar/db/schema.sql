-- Google Calendar MCP PostgreSQL Schema v2
-- Database: google_calendar_mcp
--
-- Schema v2 changes:
-- - Organizations table with M:N relationship to projects
-- - Tasks linked to phases (not projects) for proper hierarchy: PROJECT → PHASE → TASK
-- - Extended project fields (full_name, country, sector, dates, contract info)
-- - Extended contacts with organization_id FK and relationship tracking

-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO schema_version (version) VALUES (2) ON CONFLICT (version) DO NOTHING;

-- =============================================================================
-- ORGANIZATIONS
-- =============================================================================

CREATE TABLE IF NOT EXISTS organizations (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    short_name TEXT,
    name_local TEXT,
    organization_type TEXT CHECK(organization_type IN
        ('donor', 'client', 'partner', 'consultant', 'government', 'bank', 'mfi', 'nbfi', 'dfi', 'ngo', 'other')),
    parent_org_id INTEGER REFERENCES organizations(id),
    country TEXT,
    city TEXT,
    website TEXT,
    context TEXT,
    relationship_status TEXT CHECK(relationship_status IN
        ('prospect', 'active', 'dormant', 'former')),
    first_contact_date DATE,
    is_active BOOLEAN DEFAULT TRUE,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_organizations_type ON organizations(organization_type);
CREATE INDEX IF NOT EXISTS idx_organizations_country ON organizations(country);
CREATE INDEX IF NOT EXISTS idx_organizations_status ON organizations(relationship_status);

-- =============================================================================
-- PROJECTS (Extended with business fields)
-- =============================================================================

CREATE TABLE IF NOT EXISTS projects (
    id SERIAL PRIMARY KEY,
    code TEXT NOT NULL,
    full_name TEXT,
    description TEXT NOT NULL,
    country TEXT,
    sector TEXT,
    is_billable BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    structure_level INTEGER NOT NULL DEFAULT 1,
    start_date DATE,
    end_date DATE,
    contract_value DECIMAL(15,2),
    currency TEXT DEFAULT 'EUR',
    context TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_projects_code ON projects(code);
CREATE INDEX IF NOT EXISTS idx_projects_active ON projects(is_active);
CREATE INDEX IF NOT EXISTS idx_projects_country ON projects(country);

-- Migration: Drop deprecated position column
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name = 'projects' AND column_name = 'position') THEN
        ALTER TABLE projects DROP COLUMN position;
    END IF;
END $$;

-- =============================================================================
-- PROJECT-ORGANIZATION M:N Relationship
-- =============================================================================

CREATE TABLE IF NOT EXISTS project_organizations (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    organization_id INTEGER NOT NULL REFERENCES organizations(id),
    org_role TEXT NOT NULL CHECK(org_role IN
        ('donor', 'client', 'implementing_agency', 'partner', 'subcontractor', 'beneficiary')),
    contract_value DECIMAL(15,2),
    currency TEXT DEFAULT 'EUR',
    is_lead BOOLEAN DEFAULT FALSE,
    start_date DATE,
    end_date DATE,
    notes TEXT,
    UNIQUE(project_id, organization_id, org_role)
);

CREATE INDEX IF NOT EXISTS idx_project_orgs_project ON project_organizations(project_id);
CREATE INDEX IF NOT EXISTS idx_project_orgs_org ON project_organizations(organization_id);

-- =============================================================================
-- PHASES
-- =============================================================================

CREATE TABLE IF NOT EXISTS phases (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    code TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(project_id, code)
);

CREATE INDEX IF NOT EXISTS idx_phases_project ON phases(project_id);

-- =============================================================================
-- TASKS
-- Two modes:
--   1. phase_id set → task linked to specific phase
--   2. project_id set, phase_id null → universal task for all phases of project
-- =============================================================================

CREATE TABLE IF NOT EXISTS tasks (
    id SERIAL PRIMARY KEY,
    phase_id INTEGER REFERENCES phases(id) ON DELETE CASCADE,
    project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    code TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Either phase_id or project_id must be set
    CONSTRAINT tasks_parent_check CHECK (
        (phase_id IS NOT NULL AND project_id IS NULL) OR
        (phase_id IS NULL AND project_id IS NOT NULL)
    ),
    -- Unique code within phase or within project (for universal tasks)
    UNIQUE(phase_id, code),
    UNIQUE(project_id, code)
);

CREATE INDEX IF NOT EXISTS idx_tasks_phase ON tasks(phase_id);

-- Migration: Add project_id to existing tasks table and make phase_id nullable
DO $$
BEGIN
    -- Add project_id column if not exists
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'tasks' AND column_name = 'project_id') THEN
        ALTER TABLE tasks ADD COLUMN project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE;
    END IF;

    -- Make phase_id nullable if it's NOT NULL
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name = 'tasks' AND column_name = 'phase_id' AND is_nullable = 'NO') THEN
        ALTER TABLE tasks ALTER COLUMN phase_id DROP NOT NULL;
    END IF;

    -- Add check constraint if not exists
    IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints
                   WHERE table_name = 'tasks' AND constraint_name = 'tasks_parent_check') THEN
        ALTER TABLE tasks ADD CONSTRAINT tasks_parent_check CHECK (
            (phase_id IS NOT NULL AND project_id IS NULL) OR
            (phase_id IS NULL AND project_id IS NOT NULL)
        );
    END IF;
END $$;

-- Create index after column exists
CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id);

-- =============================================================================
-- NORMS, EXCLUSIONS, SETTINGS
-- =============================================================================

CREATE TABLE IF NOT EXISTS norms (
    id SERIAL PRIMARY KEY,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL,
    hours REAL NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(year, month)
);

CREATE INDEX IF NOT EXISTS idx_norms_year_month ON norms(year, month);

CREATE TABLE IF NOT EXISTS exclusions (
    id SERIAL PRIMARY KEY,
    pattern TEXT NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Default settings
INSERT INTO settings (key, value) VALUES
    ('work_calendar', 'primary'),
    ('billable_target_type', 'percent'),
    ('billable_target_value', '75'),
    ('base_location', '')
ON CONFLICT (key) DO NOTHING;

-- Default exclusions
INSERT INTO exclusions (pattern) VALUES
    ('Away'),
    ('Lunch'),
    ('Offline'),
    ('Out of office')
ON CONFLICT (pattern) DO NOTHING;

-- =============================================================================
-- EXPORT FILES (temporary file storage with TTL)
-- =============================================================================

CREATE TABLE IF NOT EXISTS export_files (
    id SERIAL PRIMARY KEY,
    uuid VARCHAR(32) NOT NULL UNIQUE,
    filename VARCHAR(255) NOT NULL,
    file_path VARCHAR(512) NOT NULL,
    file_type VARCHAR(20) DEFAULT 'xlsx',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    downloaded_at TIMESTAMPTZ,
    is_deleted BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_export_files_uuid ON export_files(uuid);
CREATE INDEX IF NOT EXISTS idx_export_files_expires ON export_files(expires_at) WHERE NOT is_deleted;

-- =============================================================================
-- CONTACTS (Extended with organization FK and relationship tracking)
-- =============================================================================

CREATE TABLE IF NOT EXISTS contacts (
    id SERIAL PRIMARY KEY,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    display_name TEXT GENERATED ALWAYS AS (first_name || ' ' || last_name) STORED,
    -- Organization (v2: FK to organizations table)
    organization_id INTEGER REFERENCES organizations(id),
    organization TEXT,  -- Legacy text name
    organization_type TEXT CHECK(organization_type IN
        ('donor', 'client', 'partner', 'consultant', 'government', 'bank', 'mfi', 'nbfi', 'dfi', 'ngo', 'other')),
    job_title TEXT,
    department TEXT,
    country TEXT,
    city TEXT,
    timezone TEXT,
    preferred_channel TEXT DEFAULT 'email' CHECK(preferred_channel IN
        ('email', 'telegram', 'teams', 'phone', 'whatsapp')),
    preferred_language TEXT DEFAULT 'en',
    -- Relationship tracking (v2)
    context TEXT,
    relationship_type TEXT CHECK(relationship_type IN ('professional', 'personal', 'referral')),
    relationship_strength TEXT CHECK(relationship_strength IN ('weak', 'moderate', 'strong')),
    last_interaction_date DATE,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_contacts_name ON contacts(first_name, last_name);
CREATE INDEX IF NOT EXISTS idx_contacts_org ON contacts(organization);
CREATE INDEX IF NOT EXISTS idx_contacts_org_id ON contacts(organization_id);
CREATE INDEX IF NOT EXISTS idx_contacts_display ON contacts(display_name);
CREATE INDEX IF NOT EXISTS idx_contacts_country ON contacts(country);

-- =============================================================================
-- CONTACT CHANNELS (with last_used_at)
-- =============================================================================

CREATE TABLE IF NOT EXISTS contact_channels (
    id SERIAL PRIMARY KEY,
    contact_id INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    channel_type TEXT NOT NULL CHECK(channel_type IN (
        'email', 'phone', 'telegram_id', 'telegram_username', 'telegram_chat_id',
        'teams_id', 'teams_chat_id', 'whatsapp', 'linkedin', 'skype', 'google_calendar'
    )),
    channel_value TEXT NOT NULL,
    channel_label TEXT,
    is_primary BOOLEAN DEFAULT FALSE,
    last_used_at TIMESTAMP,
    notes TEXT,
    UNIQUE(contact_id, channel_type, channel_value)
);

CREATE INDEX IF NOT EXISTS idx_channels_type ON contact_channels(channel_type);
CREATE INDEX IF NOT EXISTS idx_channels_value ON contact_channels(channel_value);
CREATE INDEX IF NOT EXISTS idx_channels_contact ON contact_channels(contact_id);

-- =============================================================================
-- PROJECT ROLES
-- =============================================================================

CREATE TABLE IF NOT EXISTS project_roles (
    id SERIAL PRIMARY KEY,
    role_code TEXT UNIQUE NOT NULL,
    role_name_en TEXT NOT NULL,
    role_name_ru TEXT,
    role_category TEXT CHECK(role_category IN ('consultant', 'client', 'donor', 'partner')),
    description TEXT
);

-- Insert standard roles
INSERT INTO project_roles (role_code, role_name_en, role_name_ru, role_category, description) VALUES
    ('TL', 'Team Leader', 'Руководитель группы', 'consultant', 'Overall project leadership'),
    ('DTL', 'Deputy Team Leader', 'Заместитель руководителя', 'consultant', 'Supports TL'),
    ('KE', 'Key Expert', 'Ключевой эксперт', 'consultant', 'Named expert in contract'),
    ('NKE', 'Non-Key Expert', 'Неключевой эксперт', 'consultant', 'Short-term expert'),
    ('PM', 'Project Manager', 'Менеджер проекта', 'consultant', 'Administrative management'),
    ('BSM', 'Backstopping Manager', 'Бэкстоппинг менеджер', 'consultant', 'HQ support'),
    ('JE', 'Junior Expert', 'Младший эксперт', 'consultant', 'Entry-level'),
    ('LA', 'Local Assistant', 'Локальный ассистент', 'consultant', 'In-country support'),
    ('INT', 'Interpreter/Translator', 'Переводчик', 'consultant', 'Language support'),
    ('CD', 'Client Director', 'Директор клиента', 'client', 'Decision maker'),
    ('CPM', 'Client Project Manager', 'Менеджер проекта клиента', 'client', 'Day-to-day contact'),
    ('PIU', 'PIU Coordinator', 'Координатор ГРП', 'client', 'Implementation unit lead'),
    ('CP', 'Counterpart', 'Контрагент', 'client', 'Working-level staff'),
    ('BEN', 'Beneficiary', 'Бенефициар', 'client', 'End beneficiary'),
    ('DO', 'Donor Officer', 'Представитель донора', 'donor', 'Main donor contact'),
    ('DPM', 'Donor Project Manager', 'Менеджер проекта донора', 'donor', 'Donor staff'),
    ('TA', 'Technical Advisor', 'Технический советник', 'donor', 'Technical oversight'),
    ('PC', 'Partner Consultant', 'Консультант-партнер', 'partner', 'Partner organization'),
    ('SUB', 'Subcontractor', 'Субподрядчик', 'partner', 'Subcontracted entity')
ON CONFLICT (role_code) DO NOTHING;

-- =============================================================================
-- CONTACT-PROJECT ASSIGNMENTS
-- =============================================================================

CREATE TABLE IF NOT EXISTS contact_projects (
    id SERIAL PRIMARY KEY,
    contact_id INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    role_code TEXT NOT NULL REFERENCES project_roles(role_code),
    start_date DATE,
    end_date DATE,
    is_active BOOLEAN DEFAULT TRUE,
    workdays_allocated INTEGER,
    notes TEXT,
    UNIQUE(contact_id, project_id, role_code)
);

CREATE INDEX IF NOT EXISTS idx_contact_projects_project ON contact_projects(project_id);
CREATE INDEX IF NOT EXISTS idx_contact_projects_contact ON contact_projects(contact_id);

-- =============================================================================
-- TRIGGERS for updated_at
-- =============================================================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply trigger to all tables with updated_at
DO $$
DECLARE
    tables TEXT[] := ARRAY['organizations', 'projects', 'phases', 'tasks', 'contacts', 'settings'];
    t TEXT;
BEGIN
    FOREACH t IN ARRAY tables
    LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS tr_%s_updated_at ON %s', t, t);
        EXECUTE format(
            'CREATE TRIGGER tr_%s_updated_at BEFORE UPDATE ON %s
             FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()',
            t, t
        );
    END LOOP;
END $$;

-- =============================================================================
-- VIEWS
-- =============================================================================

-- Full project view with organizations
CREATE OR REPLACE VIEW v_project_full AS
SELECT
    p.id,
    p.code,
    p.full_name,
    p.description,
    p.country,
    p.sector,
    p.is_billable,
    p.is_active,
    p.start_date,
    p.end_date,
    p.contract_value,
    p.currency,
    p.context,
    p.structure_level,
    -- Lead donor
    (SELECT o.name FROM organizations o
     JOIN project_organizations po ON o.id = po.organization_id
     WHERE po.project_id = p.id AND po.org_role = 'donor' AND po.is_lead = TRUE
     LIMIT 1) as lead_donor,
    -- Lead client
    (SELECT o.name FROM organizations o
     JOIN project_organizations po ON o.id = po.organization_id
     WHERE po.project_id = p.id AND po.org_role = 'client' AND po.is_lead = TRUE
     LIMIT 1) as lead_client,
    -- Phase count
    (SELECT COUNT(*) FROM phases WHERE project_id = p.id) as phase_count,
    -- Task count (via phases)
    (SELECT COUNT(*) FROM tasks t
     JOIN phases ph ON t.phase_id = ph.id
     WHERE ph.project_id = p.id) as task_count,
    -- Team size
    (SELECT COUNT(DISTINCT contact_id) FROM contact_projects
     WHERE project_id = p.id AND is_active = TRUE) as team_size
FROM projects p;

-- Full contact view with primary channels and organization
CREATE OR REPLACE VIEW v_contacts_full AS
SELECT
    c.id,
    c.first_name,
    c.last_name,
    c.display_name,
    c.organization_id,
    o.name as organization_name,
    o.organization_type as org_type,
    c.organization,  -- Legacy
    c.organization_type,
    c.job_title,
    c.department,
    c.country,
    c.city,
    c.timezone,
    c.preferred_channel,
    c.preferred_language,
    c.context,
    c.relationship_type,
    c.relationship_strength,
    c.last_interaction_date,
    (SELECT channel_value FROM contact_channels WHERE contact_id = c.id
     AND channel_type = 'email' AND is_primary = TRUE LIMIT 1) as primary_email,
    (SELECT channel_value FROM contact_channels WHERE contact_id = c.id
     AND channel_type = 'phone' AND is_primary = TRUE LIMIT 1) as primary_phone,
    (SELECT channel_value FROM contact_channels WHERE contact_id = c.id
     AND channel_type = 'telegram_chat_id' LIMIT 1) as telegram_chat_id,
    (SELECT channel_value FROM contact_channels WHERE contact_id = c.id
     AND channel_type = 'telegram_username' LIMIT 1) as telegram_username,
    (SELECT channel_value FROM contact_channels WHERE contact_id = c.id
     AND channel_type = 'teams_chat_id' LIMIT 1) as teams_chat_id,
    c.notes,
    c.created_at,
    c.updated_at
FROM contacts c
LEFT JOIN organizations o ON c.organization_id = o.id
WHERE c.is_active = TRUE;

-- Project team view
CREATE OR REPLACE VIEW v_project_team AS
SELECT
    cp.project_id,
    c.id as contact_id,
    c.display_name,
    o.name as organization,
    c.job_title,
    pr.role_code,
    pr.role_name_en as project_role,
    pr.role_category,
    c.preferred_channel,
    c.preferred_language,
    (SELECT channel_value FROM contact_channels WHERE contact_id = c.id
     AND channel_type = 'email' AND is_primary = TRUE LIMIT 1) as email,
    (SELECT channel_value FROM contact_channels WHERE contact_id = c.id
     AND channel_type = 'telegram_chat_id' LIMIT 1) as telegram_chat_id,
    (SELECT channel_value FROM contact_channels WHERE contact_id = c.id
     AND channel_type = 'teams_chat_id' LIMIT 1) as teams_chat_id
FROM contact_projects cp
JOIN contacts c ON cp.contact_id = c.id
LEFT JOIN organizations o ON c.organization_id = o.id
JOIN project_roles pr ON cp.role_code = pr.role_code
WHERE cp.is_active = TRUE AND c.is_active = TRUE
ORDER BY
    CASE pr.role_category
        WHEN 'donor' THEN 1
        WHEN 'client' THEN 2
        WHEN 'consultant' THEN 3
        WHEN 'partner' THEN 4
    END;

-- Contact projects view
CREATE OR REPLACE VIEW v_contact_projects AS
SELECT
    cp.id,
    cp.contact_id,
    c.display_name as contact_name,
    o.name as organization,
    cp.project_id,
    p.code as project_code,
    p.full_name as project_name,
    cp.role_code,
    pr.role_name_en,
    pr.role_name_ru,
    pr.role_category,
    cp.is_active,
    cp.workdays_allocated,
    cp.start_date,
    cp.end_date,
    cp.notes
FROM contact_projects cp
JOIN contacts c ON cp.contact_id = c.id
LEFT JOIN organizations o ON c.organization_id = o.id
JOIN project_roles pr ON cp.role_code = pr.role_code
JOIN projects p ON cp.project_id = p.id;

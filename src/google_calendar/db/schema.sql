-- Google Calendar MCP PostgreSQL Schema
-- Database: google_calendar_mcp

-- =============================================================================
-- TIME TRACKING TABLES
-- =============================================================================

-- Projects table
CREATE TABLE IF NOT EXISTS projects (
    id SERIAL PRIMARY KEY,
    code TEXT NOT NULL,
    description TEXT NOT NULL,
    is_billable BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    position TEXT,
    structure_level INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_projects_code ON projects(code);
CREATE INDEX IF NOT EXISTS idx_projects_active ON projects(is_active);

-- Phases table
CREATE TABLE IF NOT EXISTS phases (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    code TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(project_id, code)
);

CREATE INDEX IF NOT EXISTS idx_phases_project ON phases(project_id);

-- Tasks table
CREATE TABLE IF NOT EXISTS tasks (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    code TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(project_id, code)
);

CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id);

-- Workday norms table
CREATE TABLE IF NOT EXISTS norms (
    id SERIAL PRIMARY KEY,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL,
    hours REAL NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(year, month)
);

CREATE INDEX IF NOT EXISTS idx_norms_year_month ON norms(year, month);

-- Exclusions table (event patterns to skip)
CREATE TABLE IF NOT EXISTS exclusions (
    id SERIAL PRIMARY KEY,
    pattern TEXT NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Settings table (key-value)
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
-- CONTACTS TABLES
-- =============================================================================

-- Contacts table
CREATE TABLE IF NOT EXISTS contacts (
    id SERIAL PRIMARY KEY,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    display_name TEXT GENERATED ALWAYS AS (first_name || ' ' || last_name) STORED,
    organization TEXT,
    organization_type TEXT CHECK(organization_type IN
        ('donor', 'client', 'partner', 'bfc', 'government', 'bank', 'mfi', 'other')),
    job_title TEXT,
    department TEXT,
    country TEXT,
    city TEXT,
    timezone TEXT,
    preferred_channel TEXT DEFAULT 'email' CHECK(preferred_channel IN
        ('email', 'telegram', 'teams', 'phone', 'whatsapp')),
    preferred_language TEXT DEFAULT 'en',
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_contacts_name ON contacts(first_name, last_name);
CREATE INDEX IF NOT EXISTS idx_contacts_org ON contacts(organization);
CREATE INDEX IF NOT EXISTS idx_contacts_display ON contacts(display_name);
CREATE INDEX IF NOT EXISTS idx_contacts_country ON contacts(country);

-- Contact channels table
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
    notes TEXT,
    UNIQUE(contact_id, channel_type, channel_value)
);

CREATE INDEX IF NOT EXISTS idx_channels_type ON contact_channels(channel_type);
CREATE INDEX IF NOT EXISTS idx_channels_value ON contact_channels(channel_value);
CREATE INDEX IF NOT EXISTS idx_channels_contact ON contact_channels(contact_id);

-- Project roles table (standard consulting roles)
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

-- Contact-project assignments table
CREATE TABLE IF NOT EXISTS contact_projects (
    id SERIAL PRIMARY KEY,
    contact_id INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    project_id INTEGER NOT NULL REFERENCES projects(id),
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
-- VIEWS
-- =============================================================================

-- Full contact view with primary channels
CREATE OR REPLACE VIEW v_contacts_full AS
SELECT
    c.id,
    c.first_name,
    c.last_name,
    c.display_name,
    c.organization,
    c.organization_type,
    c.job_title,
    c.department,
    c.country,
    c.city,
    c.timezone,
    c.preferred_channel,
    c.preferred_language,
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
WHERE c.is_active = TRUE;

-- Project team view
CREATE OR REPLACE VIEW v_project_team AS
SELECT
    cp.project_id,
    c.id as contact_id,
    c.display_name,
    c.organization,
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
    c.organization,
    cp.project_id,
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
JOIN project_roles pr ON cp.role_code = pr.role_code;

"""Every projects / contacts operation refuses a parameter it does not read.

Issues #6, #7, #8 were one bug class: the dispatchers ignored any key an operation did
not read, so a mistyped or wrongly documented filter returned an unfiltered list that
looked filtered. The fix is one check in each dispatcher against a per-operation table
(_OP_KEYS). These tests keep that table honest from both sides:
- it equals the keys _execute_operation actually reads (parsed from the source), plus
  the update columns the *_update operations pass through;
- the docstring never teaches a key the table refuses;
- each operation refuses an unknown key before it runs and accepts all of its own keys.
"""
from __future__ import annotations

import ast
import inspect
import re

import pytest

import google_calendar.tools.contacts.database as contacts_db
import google_calendar.tools.contacts.manage as contacts
import google_calendar.tools.projects.database as projects_db
import google_calendar.tools.projects.manage as projects
from google_calendar.tools.operation_keys import COMMON_KEYS

# Operations that pass every other key to an update function, and the columns it takes.
PASSTHROUGH = {
    projects: {
        "project_update": projects_db.PROJECT_UPDATE_FIELDS,
        "phase_update": projects_db.PHASE_UPDATE_FIELDS,
        "task_update": projects_db.TASK_UPDATE_FIELDS,
        "org_update": projects_db.ORG_UPDATE_FIELDS,
        "project_org_update": projects_db.PROJECT_ORG_UPDATE_FIELDS,
        "role_update": projects.ROLE_UPDATE_FIELDS,
    },
    contacts: {
        "contact_update": contacts_db.CONTACT_UPDATE_FIELDS,
        "channel_update": contacts_db.CHANNEL_UPDATE_FIELDS,
        "assignment_update": contacts_db.ASSIGNMENT_UPDATE_FIELDS,
    },
}
TOOL = {projects: projects.projects, contacts: contacts.contacts}
MODULES = [pytest.param(projects, id="projects"), pytest.param(contacts, id="contacts")]


def _keys_read_per_operation(module) -> dict[str, set[str]]:
    """{op: keys} read by each `op == "…"` branch of _execute_operation (p.get / p[…])."""
    tree = ast.parse(inspect.getsource(module))
    execute = next(n for n in ast.walk(tree)
                   if isinstance(n, ast.AsyncFunctionDef) and n.name == "_execute_operation")
    reads: dict[str, set[str]] = {}
    for node in ast.walk(execute):
        if not (isinstance(node, ast.If) and isinstance(node.test, ast.Compare)
                and isinstance(node.test.left, ast.Name) and node.test.left.id == "op"
                and isinstance(node.test.comparators[0], ast.Constant)):
            continue
        keys: set[str] = set()
        for stmt in node.body:
            for n in ast.walk(stmt):
                if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                        and isinstance(n.func.value, ast.Name) and n.func.value.id == "p"
                        and n.func.attr == "get" and isinstance(n.args[0], ast.Constant)):
                    keys.add(n.args[0].value)
                if (isinstance(n, ast.Subscript) and isinstance(n.value, ast.Name)
                        and n.value.id == "p" and isinstance(n.slice, ast.Constant)):
                    keys.add(n.slice.value)
        reads[node.test.comparators[0].value] = keys
    return reads


@pytest.mark.parametrize("module", MODULES)
def test_the_key_table_equals_what_each_operation_reads(module):
    reads = _keys_read_per_operation(module)

    assert set(module._OP_KEYS) == set(reads)
    for op, keys in reads.items():
        expected = (keys | set(PASSTHROUGH[module].get(op, ()))) - COMMON_KEYS
        assert set(module._OP_KEYS[op]) == expected, op


_ENTRY = re.compile(r"^\s{4,}([a-z_/]+)\s*:\s*(.+(?:\n\s{20,}.+)*)", re.M)


@pytest.mark.parametrize("module", MODULES)
def test_the_docstring_teaches_no_key_the_table_refuses(module):
    doc = inspect.getdoc(TOOL[module])
    vocabulary = set().union(*module._OP_KEYS.values())
    taught: list[tuple[str, str]] = []
    for names, text in _ENTRY.findall(doc):
        for segment in re.findall(r"(?:Requires|Params|Filters):\s*([^.]+)", text):
            for word in re.findall(r"\b[a-z_]+\b", segment):
                if word in vocabulary or "_" in word:
                    taught += [(op, word) for op in names.split("/") if op in module._OP_KEYS]
    for op, payload in re.findall(r'\{"op": "([a-z_]+)"(.*?)\}', doc):
        taught += [(op, key) for key in re.findall(r'"([a-z_]+)":', payload)]

    assert taught, "the docstring parser found nothing; the test would be vacuous"
    refused = [(op, key) for op, key in taught
               if op in module._OP_KEYS and key not in module._OP_KEYS[op] | COMMON_KEYS]
    assert refused == []


# The tool API: which columns each update operation may change. Pinned here so a field
# cannot silently drop out of (or creep into) the updatable set.
UPDATABLE = {
    "projects": (projects_db.PROJECT_UPDATE_FIELDS, {
        "code", "description", "is_billable", "is_active", "structure_level", "full_name",
        "country", "sector", "start_date", "end_date", "contract_value", "currency", "context"}),
    "phases": (projects_db.PHASE_UPDATE_FIELDS, {"code", "description"}),
    "tasks": (projects_db.TASK_UPDATE_FIELDS, {"code", "description", "phase_id", "project_id"}),
    "organizations": (projects_db.ORG_UPDATE_FIELDS, {
        "name", "short_name", "name_local", "organization_type", "parent_org_id", "country",
        "city", "website", "context", "relationship_status", "first_contact_date", "is_active",
        "notes"}),
    "project_organizations": (projects_db.PROJECT_ORG_UPDATE_FIELDS, {
        "org_role", "contract_value", "currency", "is_lead", "start_date", "end_date", "notes"}),
    "project_roles": (projects.ROLE_UPDATE_FIELDS, {
        "role_name_en", "role_name_ru", "role_category", "description"}),
    "contacts": (contacts_db.CONTACT_UPDATE_FIELDS, {
        "first_name", "last_name", "organization_id", "org_notes", "job_title", "department",
        "country", "city", "timezone", "preferred_channel", "preferred_language", "context",
        "relationship_type", "relationship_strength", "last_interaction_date", "notes",
        "is_active"}),
    "contact_channels": (contacts_db.CHANNEL_UPDATE_FIELDS, {
        "channel_value", "channel_label", "is_primary", "notes"}),
    "contact_projects": (contacts_db.ASSIGNMENT_UPDATE_FIELDS, {
        "role_name", "start_date", "end_date", "is_active", "workdays_allocated", "notes"}),
}


def _schema_columns(table: str) -> set[str]:
    from pathlib import Path

    import google_calendar.db as db
    schema = (Path(db.__file__).parent / "schema.sql").read_text()
    body = re.search(rf"CREATE TABLE IF NOT EXISTS {table} \((.*?)\n\);", schema, re.S).group(1)
    return {line.split()[0] for line in body.splitlines()
            if line.strip() and not line.strip().startswith(("--", "CONSTRAINT", "UNIQUE", "PRIMARY", "CHECK", "FOREIGN"))}


@pytest.mark.parametrize("table", sorted(UPDATABLE))
def test_updatable_fields_are_the_pinned_set_of_real_columns(table):
    fields, pinned = UPDATABLE[table]

    assert set(fields) == pinned
    assert set(fields) <= _schema_columns(table)


@pytest.fixture
def ran(monkeypatch):
    """Database checks pass; _execute_operation records the operations that reached it."""
    calls: list[str] = []

    async def yes():
        return True

    async def execute(op, p):
        calls.append(op)
        return {}

    for module in (projects, contacts):
        monkeypatch.setattr(module, "database_exists", yes)
        monkeypatch.setattr(module, "_execute_operation", execute)
    monkeypatch.setattr(contacts, "contacts_tables_exist", yes)
    return calls


@pytest.mark.parametrize("module, op", [
    pytest.param(m, op, id=f"{name}:{op}")
    for m, name in ((projects, "projects"), (contacts, "contacts"))
    for op in sorted(m._OP_KEYS)
])
async def test_each_operation_refuses_an_unknown_key_before_it_runs(ran, module, op):
    result = await TOOL[module]([{"op": op, "zz_not_a_parameter": 1}])

    error = result["results"][0]["error"]
    assert error.startswith(f"{op}: unknown parameter(s) zz_not_a_parameter; supported: ")
    assert ran == []


@pytest.mark.parametrize("module, op", [
    pytest.param(m, op, id=f"{name}:{op}")
    for m, name in ((projects, "projects"), (contacts, "contacts"))
    for op in sorted(m._OP_KEYS)
])
async def test_each_operation_accepts_all_of_its_own_keys(ran, module, op):
    params = {key: None for key in module._OP_KEYS[op]}

    result = await TOOL[module]([{"op": op, "account": "work", **params}])

    assert "error" not in result["results"][0], result["results"][0]
    assert ran == [op]

"""Every projects / contacts operation refuses a parameter it does not read.

Issues #6, #7, #8 were one bug class: the dispatchers ignored any key an operation did
not read, so a mistyped or wrongly documented filter returned an unfiltered list that
looked filtered. The fix is one check in each dispatcher against a per-operation table
(_OP_KEYS, plus _NESTED_KEYS for dict-valued parameters). These tests keep the tables
honest from every side:
- the tables equal the keys the code actually reads (parsed with ast), and an operation
  missing from the table cannot run;
- every column an update operation accepts reaches its UPDATE statement;
- the docstrings never teach a key the tables refuse;
- each operation refuses an unknown key (or inner key) before it runs and accepts all
  of its own.
"""
from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path

import pytest

import google_calendar.db as db_package
import google_calendar.tools.contacts.database as contacts_db
import google_calendar.tools.contacts.lookup as contacts_lookup
import google_calendar.tools.contacts.manage as contacts
import google_calendar.tools.contacts.report as contacts_report
import google_calendar.tools.projects.database as projects_db
import google_calendar.tools.projects.manage as projects
from google_calendar.tools.operation_keys import COMMON_KEYS

# Operations that pass every other key to an update, and the columns that update takes.
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
ALL_OPS = [pytest.param(m, op, id=f"{m.__name__.split('.')[-2]}:{op}")
           for m in (projects, contacts) for op in sorted(m._OP_KEYS)]


def test_only_op_and_account_are_accepted_everywhere():
    assert COMMON_KEYS == {"op", "account"}


# ---------------------------------------------------------------------------
# The tables equal what the code reads
# ---------------------------------------------------------------------------

def _function(module, name):
    tree = ast.parse(inspect.getsource(module))
    return next(n for n in ast.walk(tree)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)


def _keys_read(nodes, var: str) -> set[str]:
    """Constant keys read from `var` via var.get("k") or var["k"]."""
    keys: set[str] = set()
    for stmt in nodes:
        for n in ast.walk(stmt):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                    and isinstance(n.func.value, ast.Name) and n.func.value.id == var
                    and n.func.attr == "get" and isinstance(n.args[0], ast.Constant)):
                keys.add(n.args[0].value)
            if (isinstance(n, ast.Subscript) and isinstance(n.value, ast.Name)
                    and n.value.id == var and isinstance(n.slice, ast.Constant)):
                keys.add(n.slice.value)
    return keys


def _branch_ops(test) -> list[str]:
    """Ops a branch test selects: `op == "x"` or `op in ("x", "y")`; [] otherwise."""
    if not (isinstance(test, ast.Compare) and isinstance(test.left, ast.Name) and test.left.id == "op"):
        return []
    right = test.comparators[0]
    if isinstance(test.ops[0], ast.Eq) and isinstance(right, ast.Constant):
        return [right.value]
    if isinstance(test.ops[0], ast.In) and isinstance(right, (ast.Tuple, ast.List, ast.Set)):
        return [e.value for e in right.elts if isinstance(e, ast.Constant)]
    raise AssertionError(f"unrecognised op branch: {ast.unparse(test)}")


def _keys_read_per_operation(module) -> dict[str, set[str]]:
    reads: dict[str, set[str]] = {}
    for node in ast.walk(_function(module, "_execute_operation")):
        if isinstance(node, ast.If):
            for op in _branch_ops(node.test):
                reads[op] = _keys_read(node.body, "p")
    return reads


@pytest.mark.parametrize("module", MODULES)
def test_the_key_table_equals_what_each_operation_reads(module):
    reads = _keys_read_per_operation(module)

    assert set(module._OP_KEYS) == set(reads)
    for op, keys in reads.items():
        expected = (keys | set(PASSTHROUGH[module].get(op, ()))) - COMMON_KEYS
        assert set(module._OP_KEYS[op]) == expected, op


def test_the_nested_key_tables_equal_what_the_code_reads():
    export = _keys_read(_function(contacts_report, "export_contacts_excel").body, "filter_params")
    context = _keys_read(_function(contacts_lookup, "resolve_contact").body, "context")

    assert contacts._NESTED_KEYS == {
        ("export_contacts", "filter_params"): export,
        ("contact_resolve", "context"): context,
        ("contact_resolve_multiple", "context"): context,
    }
    assert export and context


# ---------------------------------------------------------------------------
# Every accepted update column reaches the SQL
# ---------------------------------------------------------------------------

class _Row(dict):
    def __missing__(self, key):
        return None


@pytest.fixture
def recorded_sql(monkeypatch):
    sent: list[str] = []

    class Conn:
        async def execute(self, query, *args):
            sent.append(query)
            return "UPDATE 1"

        async def fetchrow(self, query, *args):
            sent.append(query)
            return _Row(id=1, contact_id=1, project_id=1, is_primary=False, role_code="PM",
                        channel_type="email")

        async def fetch(self, query, *args):
            sent.append(query)
            return []

        async def fetchval(self, query, *args):
            sent.append(query)
            return 1

    class Db:
        async def __aenter__(self):
            return Conn()

        async def __aexit__(self, *_):
            return False

    for module in (projects_db, contacts_db, projects):
        monkeypatch.setattr(module, "get_db", Db)
    return sent


def _value(column: str):
    if column.endswith("_date"):
        return "2026-01-01"
    if column.startswith("is_"):
        return True
    if column.endswith("_id") or column in ("structure_level", "workdays_allocated", "contract_value"):
        return 1
    return {"preferred_channel": "email", "relationship_strength": "moderate",
            "organization_type": "donor", "role_category": "management",
            "relationship_status": "active"}.get(column, "x")


@pytest.mark.parametrize("module, op", [
    pytest.param(m, op, id=op) for m in (projects, contacts) for op in sorted(PASSTHROUGH[m])
])
async def test_every_accepted_update_column_reaches_the_sql(recorded_sql, module, op):
    columns = PASSTHROUGH[module][op]
    target = {"role_update": {"role_code": "pm"}}.get(op, {"id": 1})

    await module._execute_operation(op, {"op": op, **target, **{c: _value(c) for c in columns}})

    updates = " ".join(q for q in recorded_sql if q.lstrip().upper().startswith("UPDATE"))
    missing = sorted(c for c in columns if not re.search(rf"\b{c}\s*=\s*\$", updates))
    assert missing == []


@pytest.mark.parametrize("table", sorted({
    "projects", "phases", "tasks", "organizations", "project_organizations", "project_roles",
    "contacts", "contact_channels", "contact_projects"}))
def test_updatable_columns_exist_in_the_schema(table):
    fields = {
        "projects": projects_db.PROJECT_UPDATE_FIELDS, "phases": projects_db.PHASE_UPDATE_FIELDS,
        "tasks": projects_db.TASK_UPDATE_FIELDS, "organizations": projects_db.ORG_UPDATE_FIELDS,
        "project_organizations": projects_db.PROJECT_ORG_UPDATE_FIELDS,
        "project_roles": projects.ROLE_UPDATE_FIELDS, "contacts": contacts_db.CONTACT_UPDATE_FIELDS,
        "contact_channels": contacts_db.CHANNEL_UPDATE_FIELDS,
        "contact_projects": contacts_db.ASSIGNMENT_UPDATE_FIELDS,
    }[table]
    schema = (Path(db_package.__file__).parent / "schema.sql").read_text()
    body = re.search(rf"CREATE TABLE IF NOT EXISTS {table} \((.*?)\n\);", schema, re.S).group(1)
    columns = {line.split()[0] for line in body.splitlines() if line.strip()
               and not line.strip().startswith(("--", "CONSTRAINT", "UNIQUE", "PRIMARY", "CHECK", "FOREIGN"))}

    assert set(fields) <= columns


# ---------------------------------------------------------------------------
# The docstrings teach no key the tables refuse
# ---------------------------------------------------------------------------

_ENTRY = re.compile(r"^\s{4,}([a-z_/]+)\s*:\s*(.+(?:\n\s{20,}.+)*)", re.M)
# Prose inside Requires/Params/Filters segments. Anything else there must be a real key:
# add a word here only if it is English, never a parameter name.
_PROSE = {
    "or", "and", "default", "true", "false", "both", "partial", "match", "name", "fuzzy",
    "score", "to", "look", "up", "as", "above", "an", "object", "of", "used", "pick", "among",
    "several", "matches", "for", "that", "project", "s", "team", "the", "two", "groups", "do",
    "not", "combine", "give", "at", "least", "one", "unless", "you", "want", "all", "them",
}


def _taught(module) -> list[tuple[str, str]]:
    doc = inspect.getdoc(TOOL[module])
    taught: list[tuple[str, str]] = []
    for names, text in _ENTRY.findall(doc):
        ops = [op for op in names.split("/") if op in module._OP_KEYS]
        for segment in re.findall(r"(?:Requires|Params|Filters):\s*([^.]+)", text):
            for word in re.findall(r"\b[a-z_]+\b", segment):
                if word not in _PROSE:
                    taught += [(op, word) for op in ops]
    for op, payload in re.findall(r'\{"op": "([a-z_]+)"(.*?)\}', doc):
        taught += [(op, key) for key in re.findall(r'"([a-z_]+)":', payload)]
    for op, args in re.findall(r"\b([a-z_]+)\(([^()]*)\)", doc):
        if op in module._OP_KEYS:
            args = re.sub(r'"[^"]*"', "", args)
            taught += [(op, word) for word in re.findall(r"\b([a-z_]+)\b(?:\s*=)?", args)
                       if word not in {"true", "false", "True", "False"}]
    return taught


def _accepted(module, op) -> set[str]:
    """Top-level keys of `op`, plus the inner keys of its dict-valued parameters."""
    nested = getattr(module, "_NESTED_KEYS", {})
    inner = set().union(*(keys for (nested_op, _), keys in nested.items() if nested_op == op))
    return set(module._OP_KEYS[op]) | inner | COMMON_KEYS


@pytest.mark.parametrize("module", MODULES)
def test_the_docstring_teaches_no_key_the_table_refuses(module):
    taught = _taught(module)

    assert len(taught) > 20, "the docstring parser found almost nothing; the test would be vacuous"
    refused = sorted({(op, key) for op, key in taught if key not in _accepted(module, op)})
    assert refused == []


# ---------------------------------------------------------------------------
# Behaviour through the dispatchers
# ---------------------------------------------------------------------------

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


@pytest.mark.parametrize("module, op", ALL_OPS)
async def test_each_operation_refuses_an_unknown_key_before_it_runs(ran, module, op):
    result = await TOOL[module]([{"op": op, "zz_not_a_parameter": 1}])

    error = result["results"][0]["error"]
    assert error.startswith(f"{op}: unknown parameter(s) zz_not_a_parameter; supported: ")
    assert ran == []


@pytest.mark.parametrize("module, op", ALL_OPS)
async def test_each_operation_accepts_all_of_its_own_keys(ran, module, op):
    params = {key: None for key in module._OP_KEYS[op]}

    result = await TOOL[module]([{"op": op, "account": "work", **params}])

    assert "error" not in result["results"][0], result["results"][0]
    assert ran == [op]


@pytest.mark.parametrize("module", MODULES)
@pytest.mark.parametrize("op", ["nonexistent", "PROJECT_LIST", 5, ["project_list"]])
async def test_an_unknown_operation_never_runs(ran, module, op):
    result = await TOOL[module]([{"op": op}])

    assert result["results"][0]["error"] == f"Unknown operation: {op}"
    assert ran == []


@pytest.mark.parametrize("op, param", sorted(contacts._NESTED_KEYS))
async def test_nested_parameters_refuse_unknown_inner_keys(ran, op, param):
    required = {"contact_resolve": {"identifier": "x"},
                "contact_resolve_multiple": {"identifiers": ["x"]}}.get(op, {})
    known = dict.fromkeys(contacts._NESTED_KEYS[(op, param)], 1)

    bad_key = await contacts.contacts([{"op": op, **required, param: {"organization_id": 5}}])
    not_an_object = await contacts.contacts([{"op": op, **required, param: "UNDP"}])
    good = await contacts.contacts([{"op": op, **required, param: known}])

    assert bad_key["results"][0]["error"].startswith(
        f"{op}: unknown {param} key(s) organization_id; supported: ")
    assert not_an_object["results"][0]["error"].startswith(f"{op}: {param} must be an object")
    assert "error" not in good["results"][0]
    assert ran == [op]

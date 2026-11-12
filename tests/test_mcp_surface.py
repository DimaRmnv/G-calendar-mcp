"""Guard for the MCP surface the clients actually see.

The rest of the suite tests helpers and the OAuth endpoints; nothing else drives the
server through the MCP protocol itself. That is the layer a fastmcp / mcp SDK upgrade
can break silently (tool registration, schemas, the streamable-HTTP mount), so these
tests pin it: the 7 tools are listed, a tool is callable end to end, and the HTTP
endpoint completes an `initialize` handshake at the protocol version claude.ai's
connector sends, then lists the tools.

No Google or database access: `calendars(action="list_accounts")` only reads the local
config, which is pointed at an empty temp HOME.
"""
from __future__ import annotations

import inspect
import json

import pytest
from fastmcp import Client

from google_calendar.server import mcp
from google_calendar.settings import settings

EXPECTED_TOOLS = {
    "calendars", "availability", "events", "attendees",
    "weekly_brief", "projects", "contacts",
}
API_KEY = "test-api-key-surface"
# The protocol revision claude.ai's custom connector negotiates with. Kept explicit
# so an SDK that drops it fails here, not in production.
CONNECTOR_PROTOCOL = "2025-06-18"


@pytest.fixture(autouse=True)
def _empty_home(tmp_path, monkeypatch):
    # utils/config.py resolves ~/.mcp/google-calendar via Path.home() -> $HOME.
    monkeypatch.setenv("HOME", str(tmp_path))


async def test_all_tools_are_listed_with_schemas():
    async with Client(mcp) as client:
        tools = {t.name: t for t in await client.list_tools()}

    assert set(tools) == EXPECTED_TOOLS
    for name in ("calendars", "availability", "events", "attendees"):
        assert "action" in tools[name].input_schema["properties"], name


async def test_tools_carry_their_full_docstring():
    # The docstrings are the model's only manual (actions, account rules, examples).
    # fastmcp 4 keeps just the text before the first section header unless told otherwise.
    import google_calendar.server as server

    async with Client(mcp) as client:
        tools = {t.name: t for t in await client.list_tools()}

    for name in sorted(EXPECTED_TOOLS):
        assert tools[name].description == inspect.getdoc(getattr(server, name)), name
        assert tools[name].output_schema is not None, name


async def test_tool_call_round_trip():
    async with Client(mcp) as client:
        result = await client.call_tool("calendars", {"action": "list_accounts"})

    assert result.data == {"accounts": [], "default_account": None}


def _rpc(client, payload, session_id=None):
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        "MCP-Protocol-Version": CONNECTOR_PROTOCOL,
    }
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    r = client.post("/mcp/calendar/mcp", json=payload, headers=headers)
    assert r.status_code == 200, r.text
    body = r.text
    if r.headers.get("content-type", "").startswith("text/event-stream"):
        # One JSON-RPC message per `data:` line.
        body = next(
            line[len("data:"):].strip() for line in body.splitlines() if line.startswith("data:")
        )
    return r, json.loads(body)


def test_http_initialize_and_list_tools(monkeypatch):
    from starlette.testclient import TestClient

    from google_calendar.server import create_http_app

    monkeypatch.setattr(settings, "api_key", API_KEY, raising=False)

    # `with` runs the lifespan: the streamable-HTTP session manager only serves
    # requests once it has started.
    with TestClient(create_http_app()) as client:
        r, init = _rpc(client, {
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": CONNECTOR_PROTOCOL,
                "capabilities": {},
                "clientInfo": {"name": "surface-test", "version": "0"},
            },
        })
        assert init["result"]["protocolVersion"] == CONNECTOR_PROTOCOL
        assert init["result"]["serverInfo"]["name"] == "google-calendar"
        session_id = r.headers.get("mcp-session-id")

        client.post(
            "/mcp/calendar/mcp",
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
                "MCP-Protocol-Version": CONNECTOR_PROTOCOL,
                **({"Mcp-Session-Id": session_id} if session_id else {}),
            },
        )

        _, listed = _rpc(
            client, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, session_id
        )
        assert {t["name"] for t in listed["result"]["tools"]} == EXPECTED_TOOLS

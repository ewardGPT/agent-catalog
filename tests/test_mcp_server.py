"""Tests for the MCP server module — compact output format."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
import yaml

from agent_catalog.storage import CatalogStore


@pytest.fixture
def store():
    with tempfile.TemporaryDirectory() as td:
        s = CatalogStore(root=td)
        manifest = {
            "name": "MCP Test Agent",
            "slug": "mcp-test",
            "description": "For MCP testing",
            "version": "1.0",
            "capabilities": [
                {"id": "ping", "description": "Ping", "tools": [], "surfaces": ["cli"]}
            ],
            "tools": [
                {
                    "name": "ping",
                    "description": "Ping tool",
                    "parameters": {"type": "object", "properties": {}},
                    "side_effects": ["none"],
                    "idempotent": True,
                }
            ],
        }
        path = Path(td) / "mcp-test.yaml"
        path.write_text(yaml.dump(manifest))
        s.register(path)
        yield s


class TestMCPServerHelpers:
    def test_truncate_short_string(self):
        from agent_catalog.mcp_server import _truncate

        assert _truncate("hello") == "hello"

    def test_truncate_long_string(self):
        from agent_catalog.mcp_server import _truncate

        long = "a" * 2000
        result = _truncate(long, limit=100)
        assert len(result) < 2000
        assert "more chars" in result

    def test_empty_list(self):
        with tempfile.TemporaryDirectory() as td:
            s = CatalogStore(root=td)
            from agent_catalog.mcp_server import _list_agents

            result = _list_agents(s)
            assert result[0]["text"] == "[]"

    def test_list_agents(self, store):
        from agent_catalog.mcp_server import _list_agents

        result = _list_agents(store)
        data = json.loads(result[0]["text"])
        assert len(data) == 1
        assert data[0]["s"] == "mcp-test"
        assert data[0]["n"] == "MCP Test Agent"

    def test_list_agents_filtered(self, store):
        from agent_catalog.mcp_server import _list_agents

        result = _list_agents(store, env="production")
        assert "mcp-test" in result[0]["text"]

        result2 = _list_agents(store, env="staging")
        assert result2[0]["text"] == "[]"

    def test_get_agent(self, store):
        from agent_catalog.mcp_server import _get_agent

        result = _get_agent(store, "mcp-test")
        data = json.loads(result[0]["text"])
        assert data["slug"] == "mcp-test"
        assert data["name"] == "MCP Test Agent"

    def test_get_agent_not_found(self, store):
        from agent_catalog.mcp_server import _get_agent

        result = _get_agent(store, "nonexistent")
        assert "E:" in result[0]["text"]

    def test_search_by_capability(self, store):
        from agent_catalog.mcp_server import _search_agents

        result = _search_agents(store, capability="ping")
        data = json.loads(result[0]["text"])
        assert "mcp-test" in data

        result2 = _search_agents(store, capability="nonexistent")
        assert result2[0]["text"] == "[]"

    def test_search_with_no_args(self, store):
        from agent_catalog.mcp_server import _search_agents

        result = _search_agents(store)
        data = json.loads(result[0]["text"])
        assert len(data) == 1

    def test_invoke_missing_metadata(self, store):
        """Agent registered from YAML has no python_module — expect error."""
        from agent_catalog.mcp_server import _invoke_agent

        result = _invoke_agent(store, "mcp-test", "ping")
        assert "E:" in result[0]["text"]

    def test_invoke_bad_json_params(self, store):
        from agent_catalog.mcp_server import _invoke_agent

        result = _invoke_agent(store, "mcp-test", "ping", params="not-json")
        assert "E:" in result[0]["text"]

    def test_agent_brief(self, store):
        from agent_catalog.mcp_server import _agent_brief

        agent = store.get("mcp-test")
        brief = _agent_brief(agent)
        assert brief["s"] == "mcp-test"
        assert brief["n"] == "MCP Test Agent"


class TestMCPCreateServer:
    def test_server_has_tools(self, store):
        from agent_catalog.mcp_server import create_server

        server = create_server(store)
        assert server.name == "agent-catalog"
        assert hasattr(server, "list_tools")
        assert hasattr(server, "call_tool")

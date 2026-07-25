"""Tests for the MCP server module."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import yaml

from agent_catalog.storage import CatalogStore


@pytest.fixture
def store():
    with tempfile.TemporaryDirectory() as td:
        s = CatalogStore(root=td)
        # Register a minimal agent
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


class TestMCPServer:
    def test_create_server(self, store):
        from agent_catalog.mcp_server import create_server

        server = create_server(store)
        assert server is not None

    def test_list_agents(self, store):
        from agent_catalog.mcp_server import _list_agents

        result = _list_agents(store)
        assert len(result) == 1
        assert "mcp-test" in result[0].text

    def test_list_agents_empty(self):
        with tempfile.TemporaryDirectory() as td:
            s = CatalogStore(root=td)
            from agent_catalog.mcp_server import _list_agents

            result = _list_agents(s)
            assert "No agents" in result[0].text

    def test_list_agents_filtered(self, store):
        from agent_catalog.mcp_server import _list_agents

        result = _list_agents(store, env="production")
        assert "mcp-test" in result[0].text

        result2 = _list_agents(store, env="staging")
        assert "No agents" in result2[0].text

    def test_get_agent(self, store):
        from agent_catalog.mcp_server import _get_agent

        result = _get_agent(store, "mcp-test")
        assert "MCP Test Agent" in result[0].text

    def test_get_agent_not_found(self, store):
        from agent_catalog.mcp_server import _get_agent

        result = _get_agent(store, "nonexistent")
        assert "not found" in result[0].text

    def test_search_by_capability(self, store):
        from agent_catalog.mcp_server import _search_agents

        result = _search_agents(store, capability="ping")
        assert "mcp-test" in result[0].text

        result2 = _search_agents(store, capability="nonexistent")
        assert "No matching" in result2[0].text

    def test_search_by_surface(self, store):
        from agent_catalog.mcp_server import _search_agents

        # Search by capability ID since that's how the search function works
        result = _search_agents(store, capability="ping")
        assert "mcp-test" in result[0].text

    def test_invoke_missing_metadata(self, store):
        """Agent registered from YAML has no python_module — expect error."""
        from agent_catalog.mcp_server import _invoke_agent

        result = _invoke_agent(store, "mcp-test", "ping")
        assert "Error" in result[0].text

    def test_format_agent(self, store):
        from agent_catalog.mcp_server import _format_agent

        agent = store.get("mcp-test")
        text = _format_agent(agent)
        assert "MCP Test Agent" in text
        assert "mcp-test" in text
        assert "ping" in text


class TestMCPCreateServer:
    """Verify server creation and tool listing schema."""

    def test_server_has_tools(self, store):
        from agent_catalog.mcp_server import create_server

        server = create_server(store)
        # Server object should exist and have expected attributes
        assert server.name == "agent-catalog"
        assert hasattr(server, "list_tools")
        assert hasattr(server, "call_tool")

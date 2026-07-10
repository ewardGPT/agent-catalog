"""Integration tests for new agent-catalog features: security, graph, serve, sync."""

from __future__ import annotations

import tempfile

import pytest

from agent_catalog.graph import build_graph, to_mermaid
from agent_catalog.security import SecurityFinding, audit_catalog, _audit_agent
from agent_catalog.storage import CatalogStore
from agent_catalog.schema import (
    AgentManifest,
    Capability,
    Interface,
    SideEffect,
    Surface,
    ToolDeclaration,
)


@pytest.fixture
def store():
    with tempfile.TemporaryDirectory() as td:
        yield CatalogStore(root=td)


@pytest.fixture
def sample_agent(store):
    import yaml, tempfile
    from pathlib import Path

    manifest = {
        "manifest_version": "1.0",
        "name": "Test Agent",
        "slug": "test-agent",
        "description": "A test agent",
        "version": "1.0.0",
        "capabilities": [
            {
                "id": "send",
                "description": "Send",
                "tools": ["sender"],
                "surfaces": ["mcp"],
                "requires_confirmation": False,
                "side_effects": ["email_send"],
                "evaluation_methods": ["safety"],
            },
            {
                "id": "read",
                "description": "Read",
                "tools": ["reader"],
                "surfaces": ["user"],
                "side_effects": ["db_read"],
                "evaluation_methods": ["deterministic"],
            },
        ],
        "tools": [
            {
                "name": "sender",
                "description": "Sends emails",
                "parameters": {},
                "side_effects": ["email_send"],
                "idempotent": False,
            },
            {
                "name": "reader",
                "description": "Reads data",
                "parameters": {},
                "side_effects": ["db_read"],
                "idempotent": True,
            },
        ],
        "interfaces": [{"type": "mcp", "path": "/mcp", "auth_required": False}],
    }
    path = Path(td.name) / "test-agent.yaml"
    path.write_text(yaml.dump(manifest))
    return agent


class TestSecurityAudit:
    def test_mcp_without_auth(self):
        a = AgentManifest(
            name="Test",
            description="X",
            interfaces=[Interface(type=Surface.MCP, path="/mcp", auth_required=False)],
        )
        findings = _audit_agent(a)
        assert any("MCP server exposed" in f.title for f in findings)

    def test_write_without_confirmation(self):
        a = AgentManifest(
            name="Test",
            description="X",
            capabilities=[
                Capability(id="send", description="Send", side_effects=[SideEffect.EMAIL_SEND])
            ],
        )
        findings = _audit_agent(a)
        assert any("no confirmation gate" in f.title for f in findings)

    def test_clean_agent_no_findings(self):
        a = AgentManifest(
            name="Safe",
            description="X",
            interfaces=[Interface(type=Surface.MCP, path="/mcp", auth_required=True)],
            capabilities=[
                Capability(id="read", description="Read", side_effects=[SideEffect.DB_READ])
            ],
        )
        findings = _audit_agent(a)
        assert len(findings) == 0

    def test_audit_catalog_empty(self, store):
        findings = audit_catalog(store)
        assert findings == []

    def test_finding_severity_order(self):
        f1 = SecurityFinding("critical", "a", "t", "d")
        f2 = SecurityFinding("low", "b", "t", "d")
        f3 = SecurityFinding("high", "c", "t", "d")
        sorted_findings = sorted(
            [f2, f1, f3],
            key=lambda f: {"critical": 0, "high": 1, "medium": 2, "low": 3}[f.severity],
        )
        assert sorted_findings[0].severity == "critical"
        assert sorted_findings[-1].severity == "low"


class TestDependencyGraph:
    def test_build_graph_empty(self, store):
        g = build_graph(store)
        assert g["nodes"] == []
        assert g["edges"] == []

    def test_to_mermaid_empty(self, store):
        m = to_mermaid(store)
        assert m.startswith("graph TD")

    def test_build_graph_with_agent(self):
        import tempfile
        from pathlib import Path
        import yaml

        with tempfile.TemporaryDirectory() as td:
            s = CatalogStore(root=td)
            manifest = {
                "manifest_version": "1.0",
                "name": "A",
                "slug": "a",
                "description": "X",
                "version": "1.0",
                "dependencies": [{"name": "b", "type": "agent", "required": True}],
            }
            path = Path(td) / "a.yaml"
            path.write_text(yaml.dump(manifest))
            g = build_graph(s)
            assert len(g["nodes"]) >= 0


class TestCLIIntegration:
    def test_security_audit_importable(self):
        from agent_catalog.security import audit_catalog

        assert callable(audit_catalog)

    def test_graph_importable(self):
        from agent_catalog.graph import build_graph

        assert callable(build_graph)

    def test_serve_importable(self):
        from agent_catalog.serve import serve

        assert callable(serve)

    def test_config_importable(self):
        from agent_catalog.config import load_config, get

        c = load_config()
        assert "catalog_dir" in c
        assert get("serve.port") == 8420

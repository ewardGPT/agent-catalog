"""Deepest coverage: mcp_server call_tool, serve render/startup, client edges, decorator edge cases."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pytest
import yaml

from agent_catalog.storage import CatalogStore

# ═══════════════════════════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════════════════════
# mcp_server.py — now with testable _handle_tool_call
# ═══════════════════════════════════════════════════════════════════════════════


class TestMCPServerHandleToolCall:
    @pytest.fixture
    def store(self):
        with tempfile.TemporaryDirectory() as td:
            s = CatalogStore(root=td)
            Path(td, "a.yaml").write_text(yaml.dump({
                "name": "MCP Agent", "slug": "mcp-agent", "description": "x", "version": "1.0",
                "capabilities": [{"id": "ping", "description": "Ping", "tools": ["pong"], "surfaces": ["cli"]}],
                "tools": [{"name": "pong", "description": "Pong", "parameters": {"type": "object", "properties": {}}}],
            }))
            s.register(Path(td, "a.yaml"))
            yield s

    def test_list_agents(self, store):
        from agent_catalog.mcp_server import _handle_tool_call
        result = _handle_tool_call("catalog_list_agents", {}, store)
        assert "mcp-agent" in result[0]["text"]

    def test_list_agents_filtered(self, store):
        from agent_catalog.mcp_server import _handle_tool_call
        result = _handle_tool_call("catalog_list_agents", {"environment": "production"}, store)
        assert "mcp-agent" in result[0]["text"]

    def test_list_agents_empty(self, store):
        from agent_catalog.mcp_server import _handle_tool_call
        result = _handle_tool_call("catalog_list_agents", {"environment": "staging"}, store)
        assert "[]" in result[0]["text"]

    def test_get_agent(self, store):
        from agent_catalog.mcp_server import _handle_tool_call
        result = _handle_tool_call("catalog_get_agent", {"slug": "mcp-agent"}, store)
        assert "mcp-agent" in result[0]["text"]

    def test_get_agent_not_found(self, store):
        from agent_catalog.mcp_server import _handle_tool_call
        result = _handle_tool_call("catalog_get_agent", {"slug": "nonexistent"}, store)
        assert "E:" in result[0]["text"]

    def test_get_agent_no_slug(self, store):
        from agent_catalog.mcp_server import _handle_tool_call
        result = _handle_tool_call("catalog_get_agent", {}, store)
        assert "E:" in result[0]["text"]

    def test_search_capability(self, store):
        from agent_catalog.mcp_server import _handle_tool_call
        result = _handle_tool_call("catalog_search", {"capability": "ping"}, store)
        assert "mcp-agent" in result[0]["text"]

    def test_search_no_match(self, store):
        from agent_catalog.mcp_server import _handle_tool_call
        result = _handle_tool_call("catalog_search", {"capability": "none"}, store)
        assert "[]" in result[0]["text"]

    def test_search_by_surface(self, store):
        from agent_catalog.mcp_server import _handle_tool_call
        m = {"name": "S", "slug": "s", "description": "x", "version": "1",
             "interfaces": [{"type": "mcp", "path": "/", "auth_required": True}]}
        Path(store.root, "s.yaml").write_text(yaml.dump(m))
        store.register(Path(store.root, "s.yaml"))
        result = _handle_tool_call("catalog_search", {"surface": "mcp"}, store)
        assert "s" in result[0]["text"]

    def test_invoke_no_module(self, store):
        from agent_catalog.mcp_server import _handle_tool_call
        result = _handle_tool_call("catalog_invoke", {"slug": "mcp-agent", "capability": "ping"}, store)
        assert "E:" in result[0]["text"]

    def test_invoke_no_slug(self, store):
        from agent_catalog.mcp_server import _handle_tool_call
        result = _handle_tool_call("catalog_invoke", {"capability": "ping"}, store)
        assert "E:" in result[0]["text"]

    def test_register(self, store):
        from agent_catalog.mcp_server import _handle_tool_call
        yc = yaml.dump({"name": "R", "slug": "r", "description": "x", "version": "1"})
        result = _handle_tool_call("catalog_register", {"yaml": yc}, store)
        assert "Registered" in result[0]["text"]

    def test_register_empty(self, store):
        from agent_catalog.mcp_server import _handle_tool_call
        result = _handle_tool_call("catalog_register", {"yaml": ""}, store)
        assert "E:" in result[0]["text"]

    def test_unknown_tool(self, store):
        from agent_catalog.mcp_server import _handle_tool_call
        result = _handle_tool_call("nonexistent", {}, store)
        assert "Unknown tool" in result[0]["text"]

    def test_create_server_returns_server(self):
        from agent_catalog.mcp_server import create_server
        with tempfile.TemporaryDirectory() as td:
            s = CatalogStore(root=td)
            server = create_server(s)
            assert server.name == "agent-catalog"

    def test_run_server_imports(self):
        from agent_catalog.mcp_server import run_server
        assert callable(run_server)

    def test_get_store_no_env(self):
        import os
        old = os.environ.pop("AGENT_CATALOG_DIR", None)
        try:
            from agent_catalog.mcp_server import _get_store
            store = _get_store()
            assert store is not None
        finally:
            if old:
                os.environ["AGENT_CATALOG_DIR"] = old


# ═══════════════════════════════════════════════════════════════════════════════
# serve.py — render helpers with agents, xss guard
# ═══════════════════════════════════════════════════════════════════════════════


class TestServeDeep:
    def test_dashboard_multi_agent(self):
        from agent_catalog.serve import _render_dashboard
        with tempfile.TemporaryDirectory() as td:
            s = CatalogStore(root=td)
            for i in range(3):
                Path(td, f"{i}.yaml").write_text(yaml.dump({"name": f"A{i}", "slug": f"a{i}", "description": "x", "version": "1"}))
                s.register(Path(td, f"{i}.yaml"))
            html = _render_dashboard(s)
            for i in range(3):
                assert f"A{i}" in html

    def test_security_with_findings(self):
        from agent_catalog.serve import _render_security
        with tempfile.TemporaryDirectory() as td:
            s = CatalogStore(root=td)
            Path(td, "u.yaml").write_text(yaml.dump({"name": "U", "slug": "u", "description": "x", "version": "1",
                 "interfaces": [{"type": "mcp", "path": "/mcp", "auth_required": False}]}))
            s.register(Path(td, "u.yaml"))
            html = _render_security(s)
            assert "MCP" in html or "Critical" in html or "finding" in html.lower()

    def test_xss_in_dashboard(self):
        from agent_catalog.serve import _render_dashboard
        with tempfile.TemporaryDirectory() as td:
            s = CatalogStore(root=td)
            m = {"name": "<script>xss</script>", "slug": "xss", "description": "x", "version": "1"}
            Path(td, "x.yaml").write_text(yaml.dump(m))
            s.register(Path(td, "x.yaml"))
            html = _render_dashboard(s)
            assert "<script>" not in html
            assert "&lt;script&gt;" in html

    def test_dashboard_with_model(self):
        """Dashboard renders model info when agent has a model."""
        from agent_catalog.serve import _render_dashboard
        with tempfile.TemporaryDirectory() as td:
            s = CatalogStore(root=td)
            m = {"name": "M", "slug": "m", "description": "x", "version": "1",
                 "model": {"provider": "anthropic", "name": "claude", "config": {}}}
            Path(td, "m.yaml").write_text(yaml.dump(m))
            s.register(Path(td, "m.yaml"))
            html = _render_dashboard(s)
            assert "anthropic" in html
            assert "claude" in html

    def test_serve_function(self):
        from agent_catalog.serve import serve
        assert callable(serve)


# ═══════════════════════════════════════════════════════════════════════════════
# client.py — remaining uncovered paths
# ═══════════════════════════════════════════════════════════════════════════════


class TestClientDeep:
    def test_empty_list(self):
        from agent_catalog.client import CatalogClient
        with tempfile.TemporaryDirectory() as td:
            client = CatalogClient(base_dir=td)
            assert client.agents.list() == []

    def test_get_nonexistent(self):
        from agent_catalog.client import CatalogClient
        with tempfile.TemporaryDirectory() as td:
            client = CatalogClient(base_dir=td)
            with pytest.raises(KeyError):
                client.agents.get("nonexistent")

    def test_search_none(self):
        from agent_catalog.client import CatalogClient
        with tempfile.TemporaryDirectory() as td:
            client = CatalogClient(base_dir=td)
            assert client.search.by_capability("none") == []

    def test_filter_no_match(self):
        from agent_catalog.client import CatalogClient
        with tempfile.TemporaryDirectory() as td:
            s = CatalogStore(root=td)
            Path(td, "t.yaml").write_text(yaml.dump({"name": "T", "slug": "t", "description": "x", "version": "1", "environment": "production"}))
            s.register(Path(td, "t.yaml"))
            client = CatalogClient(base_dir=td)
            assert client.agents.filter(env="staging") == []

    def test_with_raw_response_list(self):
        from agent_catalog.client import CatalogClient
        with tempfile.TemporaryDirectory() as td:
            s = CatalogStore(root=td)
            Path(td, "a.yaml").write_text(yaml.dump({"name": "A", "slug": "a", "description": "x", "version": "1"}))
            s.register(Path(td, "a.yaml"))
            client = CatalogClient(base_dir=td)
            resp = client.with_raw_response.agents.list()
            assert len(resp.data) == 1

    def test_async_empty(self):
        from agent_catalog.client import AsyncCatalogClient

        async def _test():
            with tempfile.TemporaryDirectory() as td:
                client = AsyncCatalogClient(base_dir=td)
                agents = await client.agents.list()
                assert agents == []
        asyncio.run(_test())

    def test_async_get_nonexistent(self):
        from agent_catalog.client import AsyncCatalogClient

        async def _test():
            with tempfile.TemporaryDirectory() as td:
                client = AsyncCatalogClient(base_dir=td)
                with pytest.raises(KeyError):
                    await client.agents.get("none")
        asyncio.run(_test())

    def test_async_search_none(self):
        from agent_catalog.client import AsyncCatalogClient

        async def _test():
            with tempfile.TemporaryDirectory() as td:
                client = AsyncCatalogClient(base_dir=td)
                assert await client.search.by_capability("none") == []
        asyncio.run(_test())


# ═══════════════════════════════════════════════════════════════════════════════
# decorators.py — prompts, versions, interfaces, dependencies, non-agent
# ═══════════════════════════════════════════════════════════════════════════════


class TestDecoratorDeep:
    def test_prompt_ref(self):
        from agent_catalog import agent, prompt_ref
        from agent_catalog.decorators import build_manifest

        @agent(name="P", description="x")
        @prompt_ref(version="1.0", hash="abc123", date="2024-01-01")
        class PT: pass
        m = build_manifest(PT)
        assert m.prompt[0].version == "1.0"
        assert m.prompt[0].hash == "abc123"

    def test_eval_contract(self):
        from agent_catalog import agent
        from agent_catalog.decorators import build_manifest

        @agent(name="E", description="x", eval_contract={"suites": ["s"], "coverage_required": 0.8, "project": "p"})
        class ET: pass
        m = build_manifest(ET)
        assert m.eval_contract.coverage_required == 0.8

    def test_interface_decorator(self):
        from agent_catalog import agent, interface
        from agent_catalog.decorators import build_manifest

        @agent(name="I", description="x")
        @interface(type="mcp", path="/api", auth_required=True)
        class IT: pass
        m = build_manifest(IT)
        assert m.interfaces[0].path == "/api"

    def test_dependency_decorator(self):
        from agent_catalog import agent, dependency
        from agent_catalog.decorators import build_manifest

        @agent(name="D", description="x")
        @dependency(name="db", type="database", description="pg", required=True)
        class DT: pass
        m = build_manifest(DT)
        assert m.dependencies[0].name == "db"

    def test_non_agent_raises(self):
        from agent_catalog.decorators import build_manifest
        class NA: pass
        with pytest.raises(TypeError):
            build_manifest(NA)


# ═══════════════════════════════════════════════════════════════════════════════
# aux_commands.py — security-audit table, verify with real agent
# ═══════════════════════════════════════════════════════════════════════════════


class TestAuxCommandsDeep:
    def test_security_audit_table_with_findings(self, runner):
        from agent_catalog.cli import app
        with tempfile.TemporaryDirectory() as td:
            content = yaml.dump({
                "name": "Unsafe", "slug": "unsafe", "description": "x", "version": "1.0",
                "interfaces": [{"type": "mcp", "path": "/mcp", "auth_required": False}],
            })
            Path(td, "u.yaml").write_text(content)
            runner.invoke(app, ["register", str(Path(td, "u.yaml"))], env={"AGENT_CATALOG_DIR": td})
            result = runner.invoke(app, ["security-audit"], env={"AGENT_CATALOG_DIR": td})
            assert result.exit_code == 0
            # Table output should mention findings
            assert "MCP" in result.stdout or "Critical" in result.stdout

    def test_verify_with_agents_no_module(self, runner):
        """verify on agents without python_module metadata fails (can't load class)."""
        from agent_catalog.cli import app
        with tempfile.TemporaryDirectory() as td:
            m = {"name": "V", "slug": "v", "description": "x", "version": "1"}
            Path(td, "v.yaml").write_text(yaml.dump(m))
            runner.invoke(app, ["register", str(Path(td, "v.yaml"))], env={"AGENT_CATALOG_DIR": td})
            result = runner.invoke(app, ["verify"], env={"AGENT_CATALOG_DIR": td})
            # Agents without python_module can't be loaded → verify fails
            assert result.exit_code == 1

    def test_sync_directory_not_found(self, runner):
        from agent_catalog.cli import app
        result = runner.invoke(app, ["sync", "/nonexistent/dir"])
        assert result.exit_code == 1


# ═══════════════════════════════════════════════════════════════════════════════
# diff_commands.py — env snapshots, contract export edge cases
# ═══════════════════════════════════════════════════════════════════════════════


class TestDiffCommands:
    def test_diff_left_env_not_found(self, runner, manifest_file):
        """diff --left-env with nonexistent env exits 1."""
        from agent_catalog.cli import app
        with tempfile.TemporaryDirectory() as td:
            runner.invoke(app, ["register", str(manifest_file)], env={"AGENT_CATALOG_DIR": td})
            result = runner.invoke(
                app, ["diff", "cli-test", "--left-env", "nonexistent"],
                env={"AGENT_CATALOG_DIR": td},
            )
            assert result.exit_code == 1

    def test_diff_right_env_not_found(self, runner, manifest_file):
        """diff --right-env with nonexistent env exits 1."""
        from agent_catalog.cli import app
        with tempfile.TemporaryDirectory() as td:
            runner.invoke(app, ["register", str(manifest_file)], env={"AGENT_CATALOG_DIR": td})
            result = runner.invoke(
                app, ["diff", "cli-test", "--right-env", "nonexistent"],
                env={"AGENT_CATALOG_DIR": td},
            )
            assert result.exit_code == 1

    def test_export_contract_no_contract(self, runner, manifest_file):
        """export-contract on agent without eval_contract exits 1."""
        from agent_catalog.cli import app
        with tempfile.TemporaryDirectory() as td:
            runner.invoke(app, ["register", str(manifest_file)], env={"AGENT_CATALOG_DIR": td})
            result = runner.invoke(
                app, ["export-contract", "cli-test"],
                env={"AGENT_CATALOG_DIR": td},
            )
            assert result.exit_code == 1

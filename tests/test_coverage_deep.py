"""Deep coverage: aux_commands, mcp_server call_tool, remote git, discovery fallbacks, decorators edge cases."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import yaml

from agent_catalog.storage import CatalogStore

# ═══════════════════════════════════════════════════════════════════════════════
# CLI aux commands — docs, publish, pull, verify, sync, watch
# ═══════════════════════════════════════════════════════════════════════════════


class TestAuxCommandsCLI:
    def test_docs_stdout(self, runner, manifest_file):
        from agent_catalog.cli import app

        with tempfile.TemporaryDirectory() as td:
            runner.invoke(app, ["register", str(manifest_file)], env={"AGENT_CATALOG_DIR": td})
            result = runner.invoke(app, ["docs"], env={"AGENT_CATALOG_DIR": td})
            assert result.exit_code == 0
            assert "CLI Test Agent" in result.stdout

    def test_docs_to_file(self, runner, manifest_file):
        from agent_catalog.cli import app

        with tempfile.TemporaryDirectory() as td:
            runner.invoke(app, ["register", str(manifest_file)], env={"AGENT_CATALOG_DIR": td})
            out = Path(td) / "AGENTS.md"
            result = runner.invoke(app, ["docs", "--output", str(out)], env={"AGENT_CATALOG_DIR": td})
            assert result.exit_code == 0
            assert out.exists()
            assert "CLI Test Agent" in out.read_text()

    def test_verify_no_agents(self, runner):
        from agent_catalog.cli import app

        with tempfile.TemporaryDirectory() as td:
            result = runner.invoke(app, ["verify"], env={"AGENT_CATALOG_DIR": td})
            assert result.exit_code == 0

    def test_publish_no_remote(self, runner):
        from agent_catalog.cli import app

        with tempfile.TemporaryDirectory() as td:
            result = runner.invoke(
                app, ["publish"], env={"AGENT_CATALOG_DIR": td},
            )
            assert result.exit_code == 1  # no remote configured

    def test_pull_no_remote(self, runner):
        from agent_catalog.cli import app

        with tempfile.TemporaryDirectory() as td:
            result = runner.invoke(
                app, ["pull"], env={"AGENT_CATALOG_DIR": td},
            )
            assert result.exit_code == 1

    def test_sync_watch_not_found(self, runner):
        """sync --watch on nonexistent dir exits 1."""
        from agent_catalog.cli import app

        result = runner.invoke(app, ["sync", "/nonexistent/watch/dir", "--watch"])
        # typer may exit 1 or 2 depending on how the error propagates
        assert result.exit_code != 0

    def test_sync_directory_not_found(self, runner):
        """sync on nonexistent dir exits 1."""
        from agent_catalog.cli import app

        result = runner.invoke(app, ["sync", "/nonexistent/dir"])
        assert result.exit_code == 1

    def test_security_audit_json_with_findings(self, runner):
        from agent_catalog.cli import app

        with tempfile.TemporaryDirectory() as td:
            # Register an agent with an exposed MCP endpoint (no auth)
            content = yaml.dump({
                "name": "Unsafe", "slug": "unsafe", "description": "x", "version": "1.0",
                "interfaces": [{"type": "mcp", "path": "/mcp", "auth_required": False}],
            })
            Path(td, "u.yaml").write_text(content)
            runner.invoke(app, ["register", str(Path(td, "u.yaml"))], env={"AGENT_CATALOG_DIR": td})
            result = runner.invoke(app, ["security-audit", "--format", "json"], env={"AGENT_CATALOG_DIR": td})
            assert result.exit_code == 0
            import json
            data = json.loads(result.stdout)
            assert len(data) > 0

    def test_run_bad_json_params(self, runner, manifest_file):
        from agent_catalog.cli import app

        with tempfile.TemporaryDirectory() as td:
            runner.invoke(app, ["register", str(manifest_file)], env={"AGENT_CATALOG_DIR": td})
            result = runner.invoke(
                app, ["run", "cli-test", "test_cap", "--params", "not-json"],
                env={"AGENT_CATALOG_DIR": td},
            )
            assert result.exit_code == 1

    def test_run_nonexistent_agent(self, runner):
        from agent_catalog.cli import app

        with tempfile.TemporaryDirectory() as td:
            result = runner.invoke(
                app, ["run", "nonexistent-slug", "ping"],
                env={"AGENT_CATALOG_DIR": td},
            )
            assert result.exit_code == 1


# ═══════════════════════════════════════════════════════════════════════════════
# remote.py — git-based publish/pull with temp git repos
# ═══════════════════════════════════════════════════════════════════════════════


class TestRemotePublishPull:
    def _create_git_repo(self, path: Path) -> None:
        """Initialize a bare git repo at *path* (no initial commit — publish creates one)."""
        subprocess.run(["git", "init", "--bare", "--initial-branch=main", str(path)], capture_output=True, check=True)

    def test_publish_to_remote(self, monkeypatch):
        from agent_catalog.remote import publish

        with tempfile.TemporaryDirectory() as remote_td:
            remote = Path(remote_td) / "remote.git"
            self._create_git_repo(remote)

            # Create a local catalog directory with a manifest
            catalog = Path(remote_td) / "catalog"
            catalog.mkdir()
            s = CatalogStore(root=catalog)
            m = {"name": "Git Test", "slug": "git-test", "description": "x", "version": "1.0"}
            Path(catalog, "a.yaml").write_text(yaml.dump(m))
            s.register(Path(catalog, "a.yaml"))

            monkeypatch.setenv("AGENT_CATALOG_REMOTE", str(remote))
            publish(store_dir=str(catalog))

            # Verify remote has the commit
            log = subprocess.run(
                ["git", "log", "--oneline"],
                capture_output=True, text=True, cwd=remote, check=False,
            )
            # Bare repo has no working tree, but we can clone
            clone_dir = Path(remote_td) / "clone"
            subprocess.run(
                ["git", "clone", str(remote), str(clone_dir)],
                capture_output=True, check=True,
            )
            assert (clone_dir / "a.yaml").exists()

    def test_pull_from_remote(self, monkeypatch):
        from agent_catalog.remote import pull

        with tempfile.TemporaryDirectory() as td:
            remote = Path(td) / "remote.git"
            self._create_git_repo(remote)

            # Create a catalog, publish it
            catalog = Path(td) / "catalog"
            catalog.mkdir()
            s = CatalogStore(root=catalog)
            m = {"name": "Pull Test", "slug": "pull-test", "description": "x", "version": "1.0"}
            Path(catalog, "a.yaml").write_text(yaml.dump(m))
            s.register(Path(catalog, "a.yaml"))

            monkeypatch.setenv("AGENT_CATALOG_REMOTE", str(remote))
            from agent_catalog.remote import publish as _publish
            _publish(store_dir=str(catalog))

            # Create a second catalog and pull
            catalog2 = Path(td) / "catalog2"
            catalog2.mkdir()
            monkeypatch.setenv("AGENT_CATALOG_DIR", str(catalog2))
            pull(store_dir=str(catalog2))

            assert (catalog2 / "a.yaml").exists()

    def test_publish_nothing_to_commit(self, monkeypatch):
        from agent_catalog.remote import publish

        with tempfile.TemporaryDirectory() as td:
            remote = Path(td) / "remote.git"
            self._create_git_repo(remote)

            catalog = Path(td) / "catalog"
            catalog.mkdir()
            s = CatalogStore(root=catalog)
            m = {"name": "N", "slug": "n", "description": "x", "version": "1.0"}
            Path(catalog, "a.yaml").write_text(yaml.dump(m))
            s.register(Path(catalog, "a.yaml"))

            monkeypatch.setenv("AGENT_CATALOG_REMOTE", str(remote))
            publish(store_dir=str(catalog))
            # Second publish with no changes
            publish(store_dir=str(catalog))
            # Should not crash — prints "nothing to publish"

    def test_get_remote_from_config(self, monkeypatch):
        """_get_remote falls back to config when env var is not set."""
        from agent_catalog.remote import _get_remote

        monkeypatch.delenv("AGENT_CATALOG_REMOTE", raising=False)
        # No config either — returns None
        assert _get_remote() is None


# ═══════════════════════════════════════════════════════════════════════════════
# mcp_server.py — handlers coverage
# ═══════════════════════════════════════════════════════════════════════════════


class TestMCPServerHandlers:
    def test_agent_brief_full(self):
        from agent_catalog.mcp_server import _agent_brief
        from agent_catalog.schema import AgentManifest

        a = AgentManifest(
            name="Full Agent",
            slug="full",
            description="desc",
            version="2.0",
            environment="staging",
            status="active",
            model={"provider": "anthropic", "name": "claude", "config": {}},
        )
        b = _agent_brief(a)
        assert b["s"] == "full"
        assert b["n"] == "Full Agent"
        assert b["v"] == "2.0"
        assert b["e"] == "staging"
        assert b["st"] == "active"

    def test_agent_brief_minimal(self):
        from agent_catalog.mcp_server import _agent_brief
        from agent_catalog.schema import AgentManifest

        a = AgentManifest(name="Min", slug="min", description="x", version="1")
        b = _agent_brief(a)
        assert b["s"] == "min"
        assert b["n"] == "Min"

    def test_list_agents_filtered_env(self):
        from agent_catalog.mcp_server import _list_agents

        with tempfile.TemporaryDirectory() as td:
            s = CatalogStore(root=td)
            m1 = {"name": "Prod", "slug": "prod", "description": "x", "version": "1", "environment": "production"}
            m2 = {"name": "Dev", "slug": "dev", "description": "x", "version": "1", "environment": "development"}
            Path(td, "p.yaml").write_text(yaml.dump(m1))
            Path(td, "d.yaml").write_text(yaml.dump(m2))
            s.register(Path(td, "p.yaml"))
            s.register(Path(td, "d.yaml"))

            result = _list_agents(s, env="production")
            assert len(result) == 1
            assert "prod" in result[0]["text"]

            result_all = _list_agents(s)
            assert len(result_all) == 1  # _list_agents returns aggregated text
            # Both agents should be in the combined result

    def test_search_agents_by_surface(self):
        from agent_catalog.mcp_server import _search_agents

        with tempfile.TemporaryDirectory() as td:
            s = CatalogStore(root=td)
            m = {"name": "S", "slug": "s", "description": "x", "version": "1",
                 "interfaces": [{"type": "mcp", "path": "/", "auth_required": True}]}
            Path(td, "s.yaml").write_text(yaml.dump(m))
            s.register(Path(td, "s.yaml"))

            result = _search_agents(s, surface="mcp")
            assert "s" in result[0]["text"]

    def test_invoke_agent_no_module(self):
        """Invoking an agent registered from YAML returns error (no module metadata)."""
        from agent_catalog.mcp_server import _invoke_agent

        with tempfile.TemporaryDirectory() as td:
            s = CatalogStore(root=td)
            m = {"name": "Inv", "slug": "inv", "description": "x", "version": "1",
                 "capabilities": [{"id": "ping", "description": "Ping", "tools": [], "surfaces": ["cli"]}]}
            Path(td, "i.yaml").write_text(yaml.dump(m))
            s.register(Path(td, "i.yaml"))

            result = _invoke_agent(s, "inv", "ping")
            assert "E:" in result[0]["text"]

    def test_invoke_bad_params(self):
        from agent_catalog.mcp_server import _invoke_agent

        with tempfile.TemporaryDirectory() as td:
            s = CatalogStore(root=td)
            m = {"name": "Inv", "slug": "inv2", "description": "x", "version": "1",
                 "capabilities": [{"id": "ping", "description": "Ping", "tools": [], "surfaces": ["cli"]}]}
            Path(td, "i.yaml").write_text(yaml.dump(m))
            s.register(Path(td, "i.yaml"))

            result = _invoke_agent(s, "inv2", "ping", params="not-json")
            assert "E:" in result[0]["text"]


# ═══════════════════════════════════════════════════════════════════════════════
# discovery.py — sys.path, fallback paths, scan_module errors
# ═══════════════════════════════════════════════════════════════════════════════


class TestDiscoveryErrors:
    def test_scan_module_not_python(self):
        from agent_catalog.discovery import scan_module

        with tempfile.NamedTemporaryFile(suffix=".txt", mode="w") as f:
            f.write("not python")
            results = scan_module(f.name)
            assert results == []

    def test_scan_module_nonexistent(self):
        from agent_catalog.discovery import scan_module

        results = scan_module("/nonexistent/file.py")
        assert results == []

    def test_scan_module_syntax_error(self):
        from agent_catalog.discovery import scan_module

        with tempfile.NamedTemporaryFile(suffix=".py", mode="w") as f:
            f.write("def broken( ")
            results = scan_module(f.name)
            assert results == []

    def test_scan_module_empty_file(self):
        from agent_catalog.discovery import scan_module

        with tempfile.NamedTemporaryFile(suffix=".py", mode="w") as f:
            f.write("# just a comment\n")
            results = scan_module(f.name)
            assert results == []

    def test_find_manifest_files_non_existent(self):
        from agent_catalog.discovery import find_manifest_files

        results = find_manifest_files("/nonexistent/path", "*.yaml")
        assert results == []

    def test_find_manifest_files_pattern_no_match(self):
        from agent_catalog.discovery import find_manifest_files

        with tempfile.TemporaryDirectory() as td:
            Path(td, "data.json").write_text("{}")
            results = find_manifest_files(td, "*.yaml")
            assert results == []

    def test_discover_and_register_with_agents(self):
        from agent_catalog.discovery import discover_and_register

        with tempfile.TemporaryDirectory() as td:
            s = CatalogStore(root=td)
            # Create a valid agent Python file
            code = """from agent_catalog import agent, capability, tool
@agent(name="DiscAgent", description="x")
class DiscAgent:
    @capability(id="ping", description="Ping")
    @tool(name="ping", description="Ping")
    def ping(self) -> str: return "pong"
"""
            Path(td, "agent_module.py").write_text(code)
            results = discover_and_register(td, store=s)
            assert len(results) == 1
            assert results[0].slug == "discagent"


# ═══════════════════════════════════════════════════════════════════════════════
# decorators.py — build_manifest edge cases
# ═══════════════════════════════════════════════════════════════════════════════


class TestDecoratorEdgeCases:
    def test_build_manifest_no_capabilities(self):
        from agent_catalog import agent
        from agent_catalog.decorators import build_manifest

        @agent(name="NoCap", description="x")
        class NoCapAgent:
            pass

        m = build_manifest(NoCapAgent)
        assert m.slug == "nocap"
        assert m.capabilities == []

    def test_build_manifest_with_python_metadata(self):
        from agent_catalog import agent, capability, tool
        from agent_catalog.decorators import build_manifest

        @agent(name="Meta", description="x")
        class MetaAgent:
            @capability(id="doit", description="Do it")
            @tool(name="doit", description="Do it")
            def do_it(self) -> str:
                return "done"

        m = build_manifest(MetaAgent)
        assert m.slug == "meta"
        assert len(m.capabilities) == 1
        assert m.capabilities[0].id == "doit"
        assert len(m.tools) == 1
        assert m.tools[0].name == "doit"

    def test_build_manifest_no_tools(self):
        from agent_catalog import agent, capability
        from agent_catalog.decorators import build_manifest

        @agent(name="CapOnly", description="x")
        class CapOnlyAgent:
            @capability(id="c", description="c")
            def do_c(self) -> str:
                return "c"

        m = build_manifest(CapOnlyAgent)
        assert len(m.capabilities) == 1
        assert m.capabilities[0].tools == []

    def test_build_manifest_with_labels(self):
        from agent_catalog import agent
        from agent_catalog.decorators import build_manifest

        @agent(name="Labeled", description="x", labels=["db", "production"])
        class LabeledAgent:
            pass

        m = build_manifest(LabeledAgent)
        assert "db" in m.labels
        assert "production" in m.labels

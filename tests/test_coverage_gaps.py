"""Targeted tests for low-coverage modules: config, graph, serve, diff, storage."""

from __future__ import annotations

import tempfile
from http.server import BaseHTTPRequestHandler
from pathlib import Path

import pytest
import yaml

from agent_catalog.config import _deep_merge, get, load_config
from agent_catalog.diff import compare_environments, diff_manifests
from agent_catalog.graph import build_graph, to_mermaid
from agent_catalog.schema import AgentManifest, Capability
from agent_catalog.storage import CatalogStore

# ═══════════════════════════════════════════════════════════════════════════════
# config.py
# ═══════════════════════════════════════════════════════════════════════════════


class TestConfig:
    def test_deep_merge_base_override(self):
        base = {"a": 1, "b": {"c": 2}}
        override = {"b": {"d": 3}}
        merged = _deep_merge(base, override)
        assert merged == {"a": 1, "b": {"c": 2, "d": 3}}

    def test_deep_merge_new_key(self):
        base = {"a": 1}
        override = {"b": 2}
        merged = _deep_merge(base, override)
        assert merged == {"a": 1, "b": 2}

    def test_deep_merge_replaces_non_dict(self):
        base = {"a": {"b": 1}}
        override = {"a": 2}
        merged = _deep_merge(base, override)
        assert merged == {"a": 2}

    def test_get_default(self):
        assert get("nonexistent.key", "fallback") == "fallback"

    def test_get_nested(self):
        val = get("serve.port")
        assert val == 8420

    def test_load_config_has_keys(self):
        c = load_config()
        assert "catalog_dir" in c
        assert "default_environment" in c


# ═══════════════════════════════════════════════════════════════════════════════
# graph.py
# ═══════════════════════════════════════════════════════════════════════════════


class TestGraph:
    @pytest.fixture
    def store(self):
        with tempfile.TemporaryDirectory() as td:
            s = CatalogStore(root=td)
            manifest = {
                "name": "Alpha",
                "slug": "alpha",
                "description": "Test agent A",
                "version": "1.0",
                "dependencies": [{"name": "bravo", "type": "agent", "required": True}],
            }
            path = Path(td) / "alpha.yaml"
            path.write_text(yaml.dump(manifest))
            s.register(path)

            manifest2 = {
                "name": "Bravo",
                "slug": "bravo",
                "description": "Test agent B",
                "version": "1.0",
            }
            path2 = Path(td) / "bravo.yaml"
            path2.write_text(yaml.dump(manifest2))
            s.register(path2)
            yield s

    def test_build_graph_with_deps(self, store):
        g = build_graph(store)
        assert len(g["nodes"]) == 2
        slugs = [n["id"] for n in g["nodes"]]
        assert "alpha" in slugs
        assert "bravo" in slugs

    def test_to_mermaid_with_agents(self, store):
        m = to_mermaid(store)
        assert "graph TD" in m
        assert "Alpha" in m
        assert "Bravo" in m

    def test_to_mermaid_empty(self):
        with tempfile.TemporaryDirectory() as td:
            s = CatalogStore(root=td)
            m = to_mermaid(s)
            assert m == "graph TD"


# ═══════════════════════════════════════════════════════════════════════════════
# diff.py (uncovered paths)
# ═══════════════════════════════════════════════════════════════════════════════


class TestDiff:
    def test_compare_environments_no_snapshot(self):
        m = AgentManifest(name="Test", description="X", metadata={"environments": {}})
        report = compare_environments(m, "nonexistent")
        assert not report.has_changes

    def test_compare_environments_with_snapshot(self):
        m = AgentManifest(
            name="Test",
            description="X",
            version="1.0.0",
            metadata={
                "environments": {
                    "staging": {"version": "2.0.0"},
                }
            },
        )
        report = compare_environments(m, "staging")
        assert report.has_changes

    def test_diff_capabilities_added(self):
        left = AgentManifest(name="A", description="X", capabilities=[])
        right = AgentManifest(
            name="A",
            description="X",
            capabilities=[Capability(id="new_cap", description="Added")],
        )
        report = diff_manifests(left, right)
        assert "capabilities" in report.summary


# ═══════════════════════════════════════════════════════════════════════════════
# serve.py (render functions + HTTP handler)
# ═══════════════════════════════════════════════════════════════════════════════


class TestServe:
    @pytest.fixture
    def store(self):
        with tempfile.TemporaryDirectory() as td:
            s = CatalogStore(root=td)
            manifest = {
                "name": "ServeTest",
                "slug": "serve-test",
                "description": "For serve testing",
                "version": "1.0",
                "capabilities": [
                    {"id": "test_cap", "description": "A cap", "tools": [], "surfaces": ["cli"]}
                ],
                "interfaces": [{"type": "mcp", "path": "/mcp", "auth_required": True}],
            }
            path = Path(td) / "serve-test.yaml"
            path.write_text(yaml.dump(manifest))
            s.register(path)
            yield s

    # ── HTML helpers ───────────────────────────────────────────────────────

    def test_h_escapes_html(self):
        from agent_catalog.serve import _h

        assert _h("<script>") == "&lt;script&gt;"
        assert _h('"') == "&quot;"
        assert _h("safe") == "safe"
        assert _h(42) == "42"
        assert _h(None) == "None"

    def test_render_dashboard_returns_html(self, store):
        from agent_catalog.serve import _render_dashboard

        html = _render_dashboard(store)
        assert "ServeTest" in html
        assert "test_cap" in html
        # Verify XSS protection: values are escaped
        assert "&lt;" not in html  # no double-escape
        assert "<script>" not in html  # raw script not in output

    def test_render_dashboard_empty(self):
        from agent_catalog.serve import _render_dashboard

        with tempfile.TemporaryDirectory() as td:
            s = CatalogStore(root=td)
            html = _render_dashboard(s)
            assert isinstance(html, str)

    def test_render_security_clean(self):
        from agent_catalog.serve import _render_security

        with tempfile.TemporaryDirectory() as td:
            s = CatalogStore(root=td)
            html = _render_security(s)
            assert "No issues" in html

    def test_render_graph_empty(self):
        from agent_catalog.serve import _render_graph

        with tempfile.TemporaryDirectory() as td:
            s = CatalogStore(root=td)
            html = _render_graph(s)
            assert "graph TD" in html

    # ── _build_html_page ───────────────────────────────────────────────────

    def test_build_html_page_dashboard(self, store):
        from agent_catalog.serve import _build_html_page

        page = _build_html_page(store, dashboard=True)
        assert "ServeTest" in page
        assert "<!--AGENTS_SECTION-->" not in page

    def test_build_html_page_security(self, store):
        from agent_catalog.serve import _build_html_page

        page = _build_html_page(store, security=True)
        assert "Security Audit" in page

    def test_build_html_page_graph(self, store):
        from agent_catalog.serve import _build_html_page

        page = _build_html_page(store, graph=True)
        assert "Dependency Graph" in page
        assert "graph TD" in page

    # ── _make_handler ──────────────────────────────────────────────────────

    def test_make_handler_returns_class(self, store):
        from agent_catalog.serve import _make_handler

        cls = _make_handler(store)
        assert issubclass(cls, BaseHTTPRequestHandler)

    def test_handler_routes_via_getattr(self, store):
        """Verify the handler class has expected route methods."""
        from agent_catalog.serve import _make_handler

        cls = _make_handler(store)
        for method in (
            "_handle_health",
            "_handle_json_all",
            "_handle_json_graph",
            "_handle_mermaid",
            "_handle_dashboard",
            "_handle_security",
            "_handle_graph_page",
        ):
            assert hasattr(cls, method), f"Handler missing {method}"


# ═══════════════════════════════════════════════════════════════════════════════
# storage.py (consistency, atomic write, slug safety)
# ═══════════════════════════════════════════════════════════════════════════════


class TestStorage:
    def test_consistency_clean(self):
        with tempfile.TemporaryDirectory() as td:
            s = CatalogStore(root=td)
            # Register a manifest directly (not from file inside catalog dir)
            manifest = AgentManifest(name="Consistent", description="test", version="1.0")
            s.register_manifest(manifest)
            issues = s.check_consistency()
            assert issues == []

    def test_consistency_orphaned_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            s = CatalogStore(root=td)
            # Create an extra YAML file not in the index
            orphan = Path(td) / "orphan.yaml"
            orphan.write_text(yaml.dump({"name": "O", "slug": "o", "description": "x", "version": "1.0"}))
            issues = s.check_consistency()
            assert issues
            assert any("ORPHAN" in i for i in issues)

    def test_consistency_missing_indexed(self):
        with tempfile.TemporaryDirectory() as td:
            s = CatalogStore(root=td)
            # Register, then remove the file behind the store's back
            manifest = {
                "name": "Goner",
                "slug": "goner",
                "description": "test",
                "version": "1.0",
            }
            path = Path(td) / "g.yaml"
            path.write_text(yaml.dump(manifest))
            s.register(path)
            # Delete the manifest file
            (Path(td) / "goner.yaml").unlink()
            issues = s.check_consistency()
            assert issues
            assert any("MISSING" in i for i in issues)

    def test_slug_filename_strips_dangerous_chars(self):
        assert CatalogStore._slug_filename("safe-slug") == "safe-slug.yaml"
        assert CatalogStore._slug_filename("hello.world_123") == "hello.world_123.yaml"
        # Slugs with path chars get those chars stripped
        safe = CatalogStore._slug_filename("bad/slug:name")
        assert "/" not in safe
        assert safe.endswith(".yaml")

    def test_slug_filename_rejects_empty(self):
        with pytest.raises(ValueError):
            CatalogStore._slug_filename("")

    def test_slug_filename_rejects_dot(self):
        with pytest.raises(ValueError):
            CatalogStore._slug_filename(".")
        with pytest.raises(ValueError):
            CatalogStore._slug_filename("..")

    def test_atomic_write_survives_interruption(self):
        """_atomic_write writes content and cleans up temp files."""
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "out.yaml"
            CatalogStore._atomic_write(target, "hello: world\n")
            assert target.read_text() == "hello: world\n"
            # Temp files are cleaned up
            temps = list(Path(td).glob(".*.tmp"))
            assert len(temps) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# schema.py (slug validation)
# ═══════════════════════════════════════════════════════════════════════════════


class TestSlugValidation:
    def test_rejects_path_traversal(self):
        for bad in ["../../etc", "foo/bar", "a\\b", "/etc/passwd"]:
            with pytest.raises((ValueError,)):
                AgentManifest(name="X", slug=bad, description="test")

    def test_rejects_dangerous_names(self):
        for bad in [".", ".."]:
            with pytest.raises((ValueError,)):
                AgentManifest(name="X", slug=bad, description="test")

    def test_accepts_valid_slugs(self):
        for good in ["my-agent", "my.agent", "my_agent", "a", "123", "v1.2.3"]:
            m = AgentManifest(name="X", slug=good, description="test")
            assert m.slug == good.lower()

    def test_auto_derived_slug_is_safe(self):
        m = AgentManifest(name="Test Agent!!@#$", description="test")
        # Special chars are stripped from auto-derived slug
        assert m.slug
        assert "/" not in m.slug
        assert ".." not in m.slug
        assert all(c.isalnum() or c in "._-" for c in m.slug)

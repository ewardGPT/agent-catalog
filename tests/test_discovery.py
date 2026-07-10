"""Tests for agent class discovery and auto-registration."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from agent_catalog.decorators import agent, build_manifest


# ── Helpers ──────────────────────────────────────────────────────────────


def _write_agent_module(directory: Path, filename: str, code: str) -> Path:
    """Write a Python module with @agent-decorated classes to a temp dir."""
    path = directory / filename
    path.write_text(code)
    return path


SIMPLE_AGENT = """
from agent_catalog import agent, capability, tool

@agent(name="SimpleAgent", version="1.0.0")
class SimpleAgent:
    @capability(id="ping", description="Ping the agent")
    @tool(name="ping")
    def ping(self) -> str:
        return "pong"
"""

MULTI_AGENT = """
from agent_catalog import agent, capability, tool

@agent(name="Alpha", version="1.0.0")
class Alpha:
    @capability(id="greet")
    @tool(name="greet")
    def greet(self, name: str) -> str:
        return f"Hi {name}"

@agent(name="Beta", version="2.0.0")
class Beta:
    @capability(id="count")
    @tool(name="count")
    def count(self, n: int = 10) -> int:
        return n
"""

INVALID_MODULE = """
this is not valid python @@
"""

NO_DECORATOR = """
class PlainClass:
    pass
"""


# ── scan_module ──────────────────────────────────────────────────────────


class TestScanModule:
    def test_scan_single_agent(self):
        with tempfile.TemporaryDirectory() as td:
            path = _write_agent_module(Path(td), "simple_agent.py", SIMPLE_AGENT)
            from agent_catalog.discovery import scan_module

            classes = scan_module(path)
            assert len(classes) == 1
            assert classes[0].__name__ == "SimpleAgent"

            m = build_manifest(classes[0])
            assert m.name == "SimpleAgent"
            assert m.version == "1.0.0"

    def test_scan_multi_agent_module(self):
        with tempfile.TemporaryDirectory() as td:
            path = _write_agent_module(Path(td), "multi_agent.py", MULTI_AGENT)
            from agent_catalog.discovery import scan_module

            classes = scan_module(path)
            assert len(classes) == 2
            names = {c.__name__ for c in classes}
            assert names == {"Alpha", "Beta"}

    def test_scan_invalid_module(self):
        with tempfile.TemporaryDirectory() as td:
            path = _write_agent_module(Path(td), "invalid.py", INVALID_MODULE)
            from agent_catalog.discovery import scan_module

            classes = scan_module(path)
            assert classes == []

    def test_scan_no_decorator(self):
        with tempfile.TemporaryDirectory() as td:
            path = _write_agent_module(Path(td), "plain.py", NO_DECORATOR)
            from agent_catalog.discovery import scan_module

            classes = scan_module(path)
            assert classes == []

    def test_scan_nonexistent_file(self):
        from agent_catalog.discovery import scan_module

        classes = scan_module("/nonexistent/path.py")
        assert classes == []

    def test_scan_non_py_file(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "data.txt"
            path.write_text("not python")
            from agent_catalog.discovery import scan_module

            classes = scan_module(path)
            assert classes == []


# ── scan_directory ───────────────────────────────────────────────────────


class TestScanDirectory:
    def test_scan_directory(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_agent_module(root, "agent_a.py", SIMPLE_AGENT)
            _write_agent_module(root, "agent_b.py,", MULTI_AGENT)  # typo: comma
            _write_agent_module(root, "agent_b.py", MULTI_AGENT)

            from agent_catalog.discovery import scan_directory

            results = scan_directory(root)
            # Should find SimpleAgent + Alpha + Beta = 3 classes
            assert len(results) >= 3
            class_names = {cls.__name__ for _path, cls in results}
            assert "SimpleAgent" in class_names
            assert "Alpha" in class_names
            assert "Beta" in class_names

    def test_scan_skips_test_files(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_agent_module(root, "test_agent.py", SIMPLE_AGENT)
            _write_agent_module(root, "_private.py", SIMPLE_AGENT)

            from agent_catalog.discovery import scan_directory

            results = scan_directory(root)
            # test_ and _ prefix files should be skipped
            assert len(results) == 0

    def test_scan_empty_directory(self):
        with tempfile.TemporaryDirectory() as td:
            from agent_catalog.discovery import scan_directory

            results = scan_directory(td)
            assert results == []


# ── discover_and_register ────────────────────────────────────────────────


class TestDiscoverAndRegister:
    def test_discover_and_register(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_agent_module(root, "svc.py", SIMPLE_AGENT)

            from agent_catalog.discovery import discover_and_register
            from agent_catalog.storage import CatalogStore

            store = CatalogStore(root=root / "catalog")
            manifests = discover_and_register(root, store=store)

            assert len(manifests) == 1
            assert manifests[0].name == "SimpleAgent"

            # Verify it's in the store
            retrieved = store.get("simpleagent")
            assert retrieved.name == "SimpleAgent"

    def test_discover_and_register_dry_run(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_agent_module(root, "svc.py", SIMPLE_AGENT)

            from agent_catalog.discovery import discover_and_register
            from agent_catalog.storage import CatalogStore

            store = CatalogStore(root=root / "catalog")
            manifests = discover_and_register(root, store=store, dry_run=True)

            assert len(manifests) == 1
            # Dry run: store should be empty
            assert store.list_all() == []

    def test_discover_and_register_empty(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)

            from agent_catalog.discovery import discover_and_register
            from agent_catalog.storage import CatalogStore

            store = CatalogStore(root=root / "catalog")
            manifests = discover_and_register(root, store=store)
            assert manifests == []

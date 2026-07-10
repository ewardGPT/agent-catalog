"""Tests for runtime agent loading and invocation."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from agent_catalog.decorators import build_manifest
from agent_catalog.storage import CatalogStore

SAMPLE_AGENT_CODE = """
from typing import Any
from agent_catalog import agent, capability, tool

@agent(name="TestRunner", version="1.0.0")
class TestRunner:
    \"\"\"Test agent for loader tests.\"\"\"

    def __init__(self, **kwargs: Any) -> None:
        self._init_kwargs = kwargs

    @capability(id="greet", description="Greets someone")
    @tool(name="greet")
    def greet(self, name: str, greeting: str = "Hello") -> str:
        return f"{greeting}, {name}!"

    @capability(id="double", description="Doubles a number")
    @tool(name="double")
    def double(self, x: int) -> int:
        return x * 2

    @capability(id="noop", description="Does nothing")
    def noop(self) -> None:
        return None
"""


@pytest.fixture
def agent_file():
    """Create a temp Python file with an @agent-decorated class."""
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "test_runner_agent.py"
        path.write_text(SAMPLE_AGENT_CODE)
        yield path


@pytest.fixture
def registered_slug(agent_file):
    """Register the agent from the temp file and return its slug."""
    from agent_catalog.discovery import scan_module

    with tempfile.TemporaryDirectory() as td:
        store = CatalogStore(root=td)
        classes = scan_module(agent_file)
        assert len(classes) == 1
        cls = classes[0]
        manifest = build_manifest(cls)
        meta = dict(manifest.metadata)
        meta["python_module"] = str(agent_file.resolve())
        meta["python_class"] = cls.__name__
        manifest.metadata = meta
        store.register_manifest(manifest)
        yield manifest.slug, store


# ── load_agent_class ────────────────────────────────────────────────────


class TestLoadAgentClass:
    def test_load_class(self, registered_slug):
        slug, store = registered_slug
        from agent_catalog.loader import load_agent_class

        cls = load_agent_class(slug, store=store)
        assert cls.__name__ == "TestRunner"

    def test_load_class_then_instantiate(self, registered_slug):
        slug, store = registered_slug
        from agent_catalog.loader import load_agent_class

        cls = load_agent_class(slug, store=store)
        instance = cls()
        assert instance.greet("World") == "Hello, World!"

    def test_load_missing_slug(self):

        with tempfile.TemporaryDirectory() as td:
            store = CatalogStore(root=td)
            with pytest.raises(KeyError):
                from agent_catalog.loader import load_agent_class

                load_agent_class("nonexistent", store=store)

    def test_load_no_metadata(self):
        from agent_catalog.schema import AgentManifest

        with tempfile.TemporaryDirectory() as td:
            store = CatalogStore(root=td)
            manifest = AgentManifest(name="Bare", description="no metadata")
            store.register_manifest(manifest)

            from agent_catalog.loader import LoaderError, load_agent_class

            with pytest.raises(LoaderError, match="no python_module"):
                load_agent_class("bare", store=store)

    def test_load_missing_file(self, registered_slug):
        slug, store = registered_slug
        from agent_catalog.loader import LoaderError, load_agent_class

        # Register with a non-existent path
        manifest = store.get(slug)
        meta = dict(manifest.metadata)
        meta["python_module"] = "/nonexistent/path.py"
        manifest.metadata = meta
        store.update(slug, manifest)

        with pytest.raises(LoaderError, match="not found"):
            load_agent_class(slug, store=store)


# ── create_agent ────────────────────────────────────────────────────────


class TestCreateAgent:
    def test_create(self, registered_slug):
        slug, store = registered_slug
        from agent_catalog.loader import create_agent

        agent = create_agent(slug, store=store)
        assert agent.greet("World") == "Hello, World!"

    def test_create_with_kwargs(self, registered_slug):
        slug, store = registered_slug
        # Test that extra kwargs pass through to constructor
        from agent_catalog.loader import create_agent

        agent = create_agent(slug, store=store, extra_arg="value")
        assert hasattr(agent, "greet")


# ── get_capability ──────────────────────────────────────────────────────


class TestGetCapability:
    def test_get_greet_capability(self, registered_slug):
        slug, store = registered_slug
        from agent_catalog.loader import get_capability

        method = get_capability(slug, "greet", store=store)
        assert callable(method)
        assert method("World") == "Hello, World!"

    def test_get_capability_with_params(self, registered_slug):
        slug, store = registered_slug
        from agent_catalog.loader import get_capability

        method = get_capability(slug, "greet", store=store)
        assert method("World", greeting="Hi") == "Hi, World!"

    def test_get_double_capability(self, registered_slug):
        slug, store = registered_slug
        from agent_catalog.loader import get_capability

        method = get_capability(slug, "double", store=store)
        assert method(x=21) == 42

    def test_get_missing_capability(self, registered_slug):
        slug, store = registered_slug
        from agent_catalog.loader import LoaderError, get_capability

        with pytest.raises(LoaderError, match="not found"):
            get_capability(slug, "nonexistent", store=store)

    def test_get_capability_no_tool_fallback(self, registered_slug):
        """Capability without explicit tool should fall back to method name."""
        slug, store = registered_slug
        from agent_catalog.loader import get_capability

        method = get_capability(slug, "noop", store=store)
        assert method() is None


# ── invoke_capability ───────────────────────────────────────────────────


class TestInvokeCapability:
    def test_invoke_greet(self, registered_slug):
        slug, store = registered_slug
        from agent_catalog.loader import invoke_capability

        result = invoke_capability(slug, "greet", store=store, name="World")
        assert result == "Hello, World!"

    def test_invoke_greet_custom_greeting(self, registered_slug):
        slug, store = registered_slug
        from agent_catalog.loader import invoke_capability

        result = invoke_capability(slug, "greet", store=store, name="World", greeting="Howdy")
        assert result == "Howdy, World!"

    def test_invoke_double(self, registered_slug):
        slug, store = registered_slug
        from agent_catalog.loader import invoke_capability

        result = invoke_capability(slug, "double", store=store, x=7)
        assert result == 14

    def test_invoke_noop(self, registered_slug):
        slug, store = registered_slug
        from agent_catalog.loader import invoke_capability

        result = invoke_capability(slug, "noop", store=store)
        assert result is None

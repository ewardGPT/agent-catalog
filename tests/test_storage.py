"""Storage backend tests."""

from __future__ import annotations

import tempfile
from textwrap import dedent

import pytest

from agent_catalog.storage import CatalogStore


@pytest.fixture
def store():
    with tempfile.TemporaryDirectory() as td:
        yield CatalogStore(root=td)


@pytest.fixture
def sample_manifest(tmp_path):
    content = dedent("""\
    manifest_version: "1.0"
    name: "Test Agent"
    description: "A test agent"
    version: "1.0.0"
    environment: production
    status: active
    capabilities:
      - id: do_thing
        description: "Does a thing"
    """)
    path = tmp_path / "test-agent.yaml"
    path.write_text(content)
    return path


class TestCatalogStore:
    def test_register(self, store, sample_manifest):
        agent = store.register(sample_manifest)
        assert agent.slug == "test-agent"
        assert agent.environment == "production"
        assert agent.registered_at is not None

    def test_register_creates_index(self, store, sample_manifest):
        store.register(sample_manifest)
        idx = store.index()
        assert "test-agent" in idx.agents

    def test_get(self, store, sample_manifest):
        store.register(sample_manifest)
        agent = store.get("test-agent")
        assert agent.name == "Test Agent"

    def test_get_missing_raises(self, store):
        with pytest.raises(KeyError, match="nonexistent"):
            store.get("nonexistent")

    def test_list_all(self, store, sample_manifest):
        store.register(sample_manifest)
        agents = store.list_all()
        assert len(agents) == 1
        assert agents[0].slug == "test-agent"

    def test_unregister(self, store, sample_manifest):
        store.register(sample_manifest)
        assert store.unregister("test-agent") is True
        assert len(store.list_all()) == 0

    def test_unregister_missing(self, store):
        assert store.unregister("nope") is False

    def test_search_by_capability(self, store, sample_manifest):
        store.register(sample_manifest)
        results = store.search(capability="do_thing")
        assert len(results) == 1

        results = store.search(capability="nonexistent")
        assert len(results) == 0

    def test_register_twice_overwrites(self, store, sample_manifest):
        first = store.register(sample_manifest)
        second = store.register(sample_manifest)
        assert first.slug == second.slug
        assert first.name == second.name
        assert len(store.list_all()) == 1

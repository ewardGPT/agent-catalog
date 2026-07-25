"""Tests for new v0.4.0 features: docs, remote, labels, MCP register, verify, watch."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import yaml

from agent_catalog.docs import generate_docs
from agent_catalog.schema import AgentManifest
from agent_catalog.storage import CatalogStore


@pytest.fixture
def store():
    with tempfile.TemporaryDirectory() as td:
        s = CatalogStore(root=td)
        manifest = {
            "name": "Docs Test",
            "slug": "docs-test",
            "description": "An agent for docs testing",
            "version": "1.0",
            "labels": ["testing", "documentation"],
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
        path = Path(td) / "docs-test.yaml"
        path.write_text(yaml.dump(manifest))
        s.register(path)
        yield s


class TestLabels:
    def test_labels_in_manifest(self):
        m = AgentManifest(name="Label Test", description="x", labels=["db", "production"])
        assert "db" in m.labels
        assert "production" in m.labels

    def test_search_by_label(self, store):
        results = store.search(label="testing")
        assert len(results) == 1
        assert results[0].slug == "docs-test"

    def test_search_by_label_no_match(self, store):
        results = store.search(label="nonexistent")
        assert len(results) == 0

    def test_search_by_label_and_env(self, store):
        results = store.search(label="testing", environment="production")
        assert len(results) == 1


class TestDocs:
    def test_generate_docs(self, store):
        md = generate_docs(store)
        assert "## Docs Test" in md
        assert "`docs-test`" in md
        assert "ping" in md
        assert "testing" in md  # labels
        assert "documentation" in md

    def test_generate_docs_empty(self):
        with tempfile.TemporaryDirectory() as td:
            s = CatalogStore(root=td)
            md = generate_docs(s)
            assert "No agents registered" in md

    def test_generate_docs_includes_capabilities_table(self, store):
        md = generate_docs(store)
        assert "| ID | Description | Tools | Surfaces | Confirmation | Side Effects" in md


class TestRemote:
    def test_get_remote_config(self):
        """remote module loads without error."""
        from agent_catalog import remote

        assert hasattr(remote, "publish")
        assert hasattr(remote, "pull")


class TestMCPServerRegister:
    def test_catalog_register_imports(self):
        """The create_server function imports mcp lazily."""
        from agent_catalog.mcp_server import create_server

        with tempfile.TemporaryDirectory() as td:
            s = CatalogStore(root=td)
            server = create_server(s)
            assert server is not None


class TestVerifyCommand:
    def test_verify_imports(self):
        from agent_catalog.cli.aux_commands import verify

        assert callable(verify)


class TestDocsCommand:
    def test_docs_imports(self):
        from agent_catalog.cli.aux_commands import docs

        assert callable(docs)


class TestPublishCommand:
    def test_publish_imports(self):
        from agent_catalog.cli.aux_commands import publish

        assert callable(publish)


class TestPullCommand:
    def test_pull_imports(self):
        from agent_catalog.cli.aux_commands import pull

        assert callable(pull)


class TestSyncWatch:
    def test_sync_watch_function_exists(self):
        from agent_catalog.cli.aux_commands import _sync_watch

        assert callable(_sync_watch)

"""Coverage deep-dive: serve.py HTTP handler, client.py SDK, discovery edge cases."""

from __future__ import annotations

import http.client
import json as _json
import socket
import threading
import time
from pathlib import Path

import pytest
import yaml

from agent_catalog.storage import CatalogStore


@pytest.fixture
def store_with_agent():
    """CatalogStore with one registered agent, using a temp directory."""
    import tempfile

    td = tempfile.mkdtemp()
    s = CatalogStore(root=td)
    manifest = {
        "name": "HTTP Test Agent",
        "slug": "http-test",
        "description": "For HTTP testing",
        "version": "1.0",
        "capabilities": [
            {
                "id": "test_cap",
                "description": "A test capability",
                "tools": [],
                "surfaces": ["cli"],
            }
        ],
        "tools": [
            {
                "name": "test_tool",
                "description": "A test tool",
                "parameters": {"type": "object", "properties": {}},
                "side_effects": ["none"],
                "idempotent": True,
            }
        ],
    }
    m_path = Path(td) / "agent.yaml"
    m_path.write_text(yaml.dump(manifest))
    s.register(m_path)
    yield s


# ═══════════════════════════════════════════════════════════════════════════════
# serve.py — HTTP endpoint integration tests
# ═══════════════════════════════════════════════════════════════════════════════


# Use a module-scoped server: start once, run all tests, shut down at end.
SERVER_PORT = 18420
_server_ref: dict = {"thread": None, "server": None}


def _find_free_port() -> int:
    """Ask the OS for a free port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def serve_server():
    """Start the HTTP server once per module, yield, then stop."""
    import tempfile

    from agent_catalog.serve import serve

    td = tempfile.mkdtemp()
    s = CatalogStore(root=td)
    manifest = {
        "name": "Module Test Agent",
        "slug": "module-test",
        "description": "For module-scoped HTTP testing",
        "version": "1.0",
    }
    m_path = Path(td) / "agent.yaml"
    m_path.write_text(yaml.dump(manifest))
    s.register(m_path)

    port = _find_free_port()
    # Store the store on the class so tests can access it
    TestServeHTTP.store = s
    TestServeHTTP.port = port
    server_args = {"store": s, "port": port, "host": "127.0.0.1"}

    t = threading.Thread(target=serve, kwargs=server_args, daemon=True)
    t.start()
    time.sleep(0.3)
    yield
    # Daemon thread dies with test process — no explicit shutdown needed


class TestServeHTTP:
    """Start a real HTTP server thread and test all endpoints."""

    store: CatalogStore = None  # set by fixture
    port: int = 18420  # set by fixture

    @pytest.fixture(autouse=True)
    def _ensure_server(self, serve_server):
        pass  # ensure module-scoped server is started

    def _get(self, path: str) -> http.client.HTTPResponse:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            conn.request("GET", path)
            return conn.getresponse()
        finally:
            conn.close()

    def _get(self, path: str) -> http.client.HTTPResponse:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            conn.request("GET", path)
            return conn.getresponse()
        finally:
            conn.close()

    def test_health_endpoint(self):
        resp = self._get("/health")
        assert resp.status == 200
        data = _json.loads(resp.read())
        assert data["status"] == "ok"
        assert data["agents"] >= 1

    def test_json_all_endpoint(self):
        resp = self._get("/json")
        assert resp.status == 200
        assert resp.getheader("Content-Type", "").startswith("application/json")
        data = _json.loads(resp.read())
        assert "agents" in data
        assert len(data["agents"]) >= 1
        assert data["agents"][0]["slug"] == "module-test"

    def test_json_graph_endpoint(self):
        resp = self._get("/json/graph")
        assert resp.status == 200
        data = _json.loads(resp.read())
        assert "nodes" in data
        assert "edges" in data

    def test_mermaid_endpoint(self):
        resp = self._get("/mermaid")
        assert resp.status == 200
        assert resp.getheader("Content-Type", "").startswith("text/plain")
        text = resp.read().decode()
        assert "graph TD" in text

    def test_dashboard_endpoint(self):
        resp = self._get("/")
        assert resp.status == 200
        assert resp.getheader("Content-Type", "").startswith("text/html")
        html = resp.read().decode()
        assert "Module Test Agent" in html
        assert "Agent Marketplace" in html

    def test_dashboard_explicit_path(self):
        resp = self._get("/dashboard")
        assert resp.status == 200
        html = resp.read().decode()
        assert "Agent Marketplace" in html

    def test_security_endpoint(self):
        resp = self._get("/security")
        assert resp.status == 200
        html = resp.read().decode()
        assert "Security Audit" in html

    def test_graph_page_endpoint(self):
        resp = self._get("/graph")
        assert resp.status == 200
        html = resp.read().decode()
        assert "Dependency Graph" in html

    def test_404_endpoint(self):
        resp = self._get("/nonexistent")
        assert resp.status == 404
        data = _json.loads(resp.read())
        assert "Not found" in data["error"]

    def test_cors_on_json(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            conn.request("OPTIONS", "/json")
            resp = conn.getresponse()
            assert resp.status == 204
            assert resp.getheader("Access-Control-Allow-Origin") == "*"
        finally:
            conn.close()

    def test_security_headers(self):
        resp = self._get("/")
        assert resp.getheader("X-Content-Type-Options") == "nosniff"
        assert resp.getheader("X-Frame-Options") == "DENY"


# ═══════════════════════════════════════════════════════════════════════════════
# client.py — SDK integration tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestCatalogClient:
    def test_client_list(self, store_with_agent):
        from agent_catalog.client import CatalogClient

        client = CatalogClient(base_dir=str(store_with_agent.root))
        agents = client.agents.list()
        assert len(agents) >= 1
        assert agents[0].slug == "http-test"

    def test_client_get(self, store_with_agent):
        from agent_catalog.client import CatalogClient

        client = CatalogClient(base_dir=str(store_with_agent.root))
        agent = client.agents.get("http-test")
        assert agent.name == "HTTP Test Agent"

    def test_client_search(self, store_with_agent):
        from agent_catalog.client import CatalogClient

        client = CatalogClient(base_dir=str(store_with_agent.root))
        results = client.agents.search(capability="test_cap")
        assert len(results) >= 1

    def test_client_search_resource(self, store_with_agent):
        from agent_catalog.client import CatalogClient

        client = CatalogClient(base_dir=str(store_with_agent.root))
        results = client.search.by_capability("test_cap")
        assert len(results) >= 1

    def test_client_filter(self, store_with_agent):
        from agent_catalog.client import CatalogClient

        client = CatalogClient(base_dir=str(store_with_agent.root), env="production")
        agents = client.agents.filter(env="production")
        assert len(agents) >= 1

    def test_client_list_slugs(self, store_with_agent):
        from agent_catalog.client import CatalogClient

        client = CatalogClient(base_dir=str(store_with_agent.root))
        slugs = client.list_slugs()
        assert "http-test" in slugs

    def test_client_with_raw_response_get(self, store_with_agent):
        from agent_catalog.client import CatalogClient

        client = CatalogClient(base_dir=str(store_with_agent.root))
        response = client.with_raw_response.agents.get("http-test")
        assert response.data.slug == "http-test"

    def test_client_with_raw_response_list(self, store_with_agent):
        from agent_catalog.client import CatalogClient

        client = CatalogClient(base_dir=str(store_with_agent.root))
        response = client.with_raw_response.agents.list()
        assert len(response.data) >= 1

    def test_client_with_raw_response_search(self, store_with_agent):
        from agent_catalog.client import CatalogClient

        client = CatalogClient(base_dir=str(store_with_agent.root))
        response = client.with_raw_response.search.by_capability("test_cap")
        assert len(response.data) >= 1


class TestAsyncCatalogClient:
    def test_async_list(self, store_with_agent):
        import asyncio

        from agent_catalog.client import AsyncCatalogClient

        client = AsyncCatalogClient(base_dir=str(store_with_agent.root))

        async def _test():
            agents = await client.agents.list()
            assert len(agents) >= 1
            assert agents[0].slug == "http-test"

        asyncio.run(_test())

    def test_async_get(self, store_with_agent):
        import asyncio

        from agent_catalog.client import AsyncCatalogClient

        client = AsyncCatalogClient(base_dir=str(store_with_agent.root))

        async def _test():
            agent = await client.agents.get("http-test")
            assert agent.name == "HTTP Test Agent"

        asyncio.run(_test())

    def test_async_search(self, store_with_agent):
        import asyncio

        from agent_catalog.client import AsyncCatalogClient

        client = AsyncCatalogClient(base_dir=str(store_with_agent.root))

        async def _test():
            results = await client.search.by_capability("test_cap")
            assert len(results) >= 1

        asyncio.run(_test())

    def test_async_list_slugs(self, store_with_agent):
        import asyncio

        from agent_catalog.client import AsyncCatalogClient

        client = AsyncCatalogClient(base_dir=str(store_with_agent.root))

        async def _test():
            slugs = await client.list_slugs()
            assert "http-test" in slugs

        asyncio.run(_test())


# ═══════════════════════════════════════════════════════════════════════════════
# discovery.py — edge cases
# ═══════════════════════════════════════════════════════════════════════════════


class TestDiscoveryEdgeCases:
    def test_find_manifest_files_no_match(self):
        import tempfile

        from agent_catalog.discovery import find_manifest_files

        with tempfile.TemporaryDirectory() as td:
            results = find_manifest_files(td, "nonexistent.yaml")
            assert results == []

    def test_find_manifest_files_non_existent_dir(self):
        from agent_catalog.discovery import find_manifest_files

        results = find_manifest_files("/nonexistent/directory", "*.yaml")
        assert results == []

    def test_find_manifest_files_with_yaml(self):
        import tempfile

        from agent_catalog.discovery import find_manifest_files

        with tempfile.TemporaryDirectory() as td:
            Path(td, "agent.yaml").write_text("name: test\nslug: test\n")
            results = find_manifest_files(td, "agent.yaml")
            assert len(results) == 1

    def test_scan_module_not_python(self):
        import tempfile

        from agent_catalog.discovery import scan_module

        with tempfile.NamedTemporaryFile(suffix=".txt", mode="w") as f:
            f.write("not python")
            results = scan_module(f.name)
            assert results == []

    def test_scan_module_nonexistent(self):
        from agent_catalog.discovery import scan_module

        results = scan_module("/nonexistent/file.py")
        assert results == []

    def test_scan_directory_skips_private(self):
        import tempfile

        from agent_catalog.discovery import scan_directory

        with tempfile.TemporaryDirectory() as td:
            # Create a private file that should be skipped
            private = Path(td, "_private.py")
            private.write_text("# private")
            results = scan_directory(td)
            # _private.py should be skipped
            assert not any(p == private for p, _ in results)

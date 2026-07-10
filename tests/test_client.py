"""Tests for the CatalogClient SDK."""

from agent_catalog.client import AsyncCatalogClient, CatalogClient


class TestCatalogClient:
    def test_instantiation(self):
        c = CatalogClient()
        assert hasattr(c, "agents")
        assert hasattr(c, "search")
        assert hasattr(c, "with_raw_response")

    def test_list(self):
        c = CatalogClient()
        agents = c.agents.list()
        assert isinstance(agents, list)

    def test_search(self):
        c = CatalogClient()
        result = c.agents.search(capability="send_email")
        assert isinstance(result, list)

    def test_with_raw_response(self):
        c = CatalogClient()
        raw = c.with_raw_response.agents.list()
        assert raw is not None

    def test_async(self):
        ac = AsyncCatalogClient()
        assert ac.agents is not None

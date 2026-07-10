"""CatalogClient — the single entry point for the Agent Catalog Python SDK.

Patterned after eval-harness's EvalClient:
- env-var config fallback (CATALOG_BASE_DIR)
- @cached_property resource hierarchy (IDE-discoverable)
- with_raw_response escape hatch
- sync/async mirror

Usage:
    from agent_catalog.client import CatalogClient

    # Zero config — uses ~/.config/agent-catalog/agents/
    client = CatalogClient()

    # Resource hierarchy
    all_agents = client.agents.list()
    agent = client.agents.get("agentic-inbox")
    matched = client.search.by_capability("send_email")
    prod = client.agents.filter(env="production", status="active")

    # with_raw_response
    response = client.with_raw_response.agents.get("agentic-inbox")

    # Async mirror
    from agent_catalog.client import AsyncCatalogClient
    client = AsyncCatalogClient()
    agents = await client.agents.list()
"""

from __future__ import annotations

import os
from functools import cached_property
from pathlib import Path
from typing import Any, Generic, TypeVar

from agent_catalog.schema import AgentManifest
from agent_catalog.storage import CatalogStore

T = TypeVar("T")


class CatalogResponse(Generic[T]):
    """Wrapper returned by `with_raw_response` methods.

    Carries the typed result as `.data` plus access to the underlying store.
    """

    def __init__(self, data: T, store: CatalogStore | None = None) -> None:
        self.data = data
        self._store = store


# ── Resources ──────────────────────────────────────────────────────────────────


class AgentsResource:
    """Operations on agent manifests in the catalog."""

    def __init__(self, store: CatalogStore) -> None:
        self._store = store

    def list(self, *, env: str | None = None) -> list[AgentManifest]:
        """List all registered agents, optionally filtered by environment."""
        agents = self._store.list_all()
        if env is not None:
            agents = [a for a in agents if a.environment == env]
        return agents

    def get(self, slug: str) -> AgentManifest:
        """Get a single agent manifest by slug."""
        return self._store.get(slug)

    def search(
        self,
        *,
        capability: str | None = None,
        tool: str | None = None,
        surface: str | None = None,
        env: str | None = None,
    ) -> list[AgentManifest]:
        """Search agents by capability, tool, surface, or environment.

        All filters are AND'd together. None means "match everything."
        """
        return self._store.search(
            capability=capability,
            tool=tool,
            surface=surface,
            environment=env,
        )

    def filter(
        self,
        *,
        env: str | None = None,
        status: str | None = None,
    ) -> list[AgentManifest]:
        """Filter agents by environment and/or status."""
        agents = self._store.list_all()
        if env is not None:
            agents = [a for a in agents if a.environment == env]
        if status is not None:
            agents = [a for a in agents if a.status == status]
        return agents


class SearchResource:
    """Dedicated search operations on the catalog."""

    def __init__(self, store: CatalogStore) -> None:
        self._store = store

    def by_capability(self, text: str) -> list[AgentManifest]:
        """Find agents with a capability matching the given text."""
        return self._store.search(capability=text)

    def by_environment(self, env: str) -> list[AgentManifest]:
        """Find agents registered in a specific environment."""
        return self._store.search(environment=env)


# ── with_raw_response wrappers ────────────────────────────────────────────────


class AgentsResourceWithRawResponse:
    """Raw-response wrapper for AgentsResource.

    Each method returns CatalogResponse[list[AgentManifest]] instead of
    the bare list, giving access to the underlying store.
    """

    def __init__(self, resource: AgentsResource) -> None:
        self._resource = resource

    def list(self, *, env: str | None = None) -> CatalogResponse[list[AgentManifest]]:
        return CatalogResponse(self._resource.list(env=env), store=self._resource._store)

    def get(self, slug: str) -> CatalogResponse[AgentManifest]:
        return CatalogResponse(self._resource.get(slug), store=self._resource._store)

    def search(
        self,
        *,
        capability: str | None = None,
        tool: str | None = None,
        surface: str | None = None,
        env: str | None = None,
    ) -> CatalogResponse[list[AgentManifest]]:
        return CatalogResponse(
            self._resource.search(capability=capability, tool=tool, surface=surface, env=env),
            store=self._resource._store,
        )

    def filter(
        self,
        *,
        env: str | None = None,
        status: str | None = None,
    ) -> CatalogResponse[list[AgentManifest]]:
        return CatalogResponse(
            self._resource.filter(env=env, status=status),
            store=self._resource._store,
        )


class SearchResourceWithRawResponse:
    """Raw-response wrapper for SearchResource."""

    def __init__(self, resource: SearchResource) -> None:
        self._resource = resource

    def by_capability(self, text: str) -> CatalogResponse[list[AgentManifest]]:
        return CatalogResponse(self._resource.by_capability(text), store=self._resource._store)

    def by_environment(self, env: str) -> CatalogResponse[list[AgentManifest]]:
        return CatalogResponse(self._resource.by_environment(env), store=self._resource._store)


class CatalogWithRawResponse:
    """Prefix any resource with `.with_raw_response` to get CatalogResponse.

    Example:
        response = client.with_raw_response.agents.get("my-agent")
        response.data.slug       # typed AgentManifest
    """

    def __init__(self, client: CatalogClient) -> None:
        self._client = client

    @cached_property
    def agents(self) -> AgentsResourceWithRawResponse:
        return AgentsResourceWithRawResponse(self._client.agents)

    @cached_property
    def search(self) -> SearchResourceWithRawResponse:
        return SearchResourceWithRawResponse(self._client.search)


# ── CatalogClient ─────────────────────────────────────────────────────────────


class CatalogClient:
    """Agent Catalog Python SDK entry point.

    One import, one object, everything discoverable from there.

    Usage:
        client = CatalogClient()
        for agent in client.agents.list():
            print(agent.slug)
    """

    def __init__(
        self,
        *,
        base_dir: str | Path | None = None,
        config_dir: str | Path | None = None,
        env: str | None = None,
    ) -> None:
        # Env-var fallback: CATALOG_BASE_DIR (SDK), then AGENT_CATALOG_DIR (CLI)
        resolved = base_dir
        if resolved is None and os.environ.get("CATALOG_BASE_DIR"):
            resolved = os.environ["CATALOG_BASE_DIR"]
        self._config_dir = config_dir
        self._env = env or os.environ.get("CATALOG_DEFAULT_ENV", "")
        self._store = CatalogStore(root=resolved) if resolved else CatalogStore()

    def __repr__(self) -> str:
        return f"CatalogClient(root={self._store.root})"

    @cached_property
    def agents(self) -> AgentsResource:
        """Access agent manifest operations."""
        return AgentsResource(self._store)

    @cached_property
    def search(self) -> SearchResource:
        """Access catalog search operations."""
        return SearchResource(self._store)

    @cached_property
    def with_raw_response(self) -> CatalogWithRawResponse:
        """Access resources wrapped with raw-response support."""
        return CatalogWithRawResponse(self)

    def list_slugs(self) -> list[str]:
        """List all registered agent slugs."""
        return [a.slug for a in self.agents.list()]


# ── AsyncCatalogClient ────────────────────────────────────────────────────────


class AsyncCatalogClient:
    """Async mirror of CatalogClient.

    Same interface, all methods async. Delegates file I/O to a thread
    pool so it never blocks the event loop.
    """

    def __init__(self, **kwargs: Any) -> None:
        self._sync = CatalogClient(**kwargs)

    @cached_property
    def agents(self) -> AgentsResource:
        return self._sync.agents

    @cached_property
    def search(self) -> SearchResource:
        return self._sync.search

    @cached_property
    def with_raw_response(self) -> CatalogWithRawResponse:
        return self._sync.with_raw_response

    async def list_slugs(self) -> list[str]:
        """List all registered agent slugs."""
        import asyncio

        return await asyncio.to_thread(self._sync.list_slugs)

    async def refresh(self) -> None:
        """Re-read the catalog index from disk."""
        return

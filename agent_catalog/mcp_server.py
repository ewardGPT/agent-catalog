"""MCP server for Agent Catalog.

Exposes the agent catalog as MCP tools so any MCP client (Claude Code,
Cursor, etc.) can discover and invoke agents from the catalog.

Usage:
    # Run as standalone MCP server (stdio transport)
    python -m agent_catalog.mcp_server

    # Or from the CLI
    agent-catalog serve --mcp
"""

from __future__ import annotations

import json
from typing import Any

import mcp.server.stdio
import mcp.types as types
from mcp.server.lowlevel import Server

from agent_catalog.loader import invoke_capability
from agent_catalog.schema import AgentManifest
from agent_catalog.storage import CatalogStore


def _get_store() -> CatalogStore:
    import os

    root = os.environ.get("AGENT_CATALOG_DIR")
    return CatalogStore(root=root) if root else CatalogStore()


def _format_agent(a: AgentManifest) -> str:
    """Format an agent manifest as a readable string."""
    lines = [
        f"Name: {a.name}",
        f"Slug: {a.slug}",
        f"Version: {a.version}",
        f"Environment: {a.environment}",
        f"Status: {a.status}",
        f"Description: {a.description}",
    ]
    if a.model:
        lines.append(f"Model: {a.model.provider}/{a.model.name}")
    if a.capabilities:
        lines.append("Capabilities: " + ", ".join(c.id for c in a.capabilities))
    if a.tools:
        lines.append("Tools: " + ", ".join(t.name for t in a.tools))
    if a.dependencies:
        lines.append("Dependencies: " + ", ".join(d.name for d in a.dependencies))
    return "\n".join(lines)


def _list_agents(store: CatalogStore, env: str | None = None) -> list[types.TextContent]:
    """List agents, optionally filtered by environment."""
    agents = store.list_all()
    if env:
        agents = [a for a in agents if a.environment == env]
    if not agents:
        return [types.TextContent(type="text", text="No agents found.")]
    parts = [f"Found {len(agents)} agent(s):\n"]
    for a in sorted(agents, key=lambda x: x.slug):
        parts.append(f"- {a.slug} ({a.name}) @ {a.environment} — {a.status}")
        caps = ", ".join(c.id for c in a.capabilities[:3])
        if caps:
            parts[-1] += f" [{caps}]"
    return [types.TextContent(type="text", text="\n".join(parts))]


def _get_agent(store: CatalogStore, slug: str) -> list[types.TextContent]:
    """Get full details for one agent."""
    try:
        a = store.get(slug)
        return [types.TextContent(type="text", text=_format_agent(a))]
    except KeyError as e:
        return [types.TextContent(type="text", text=f"Error: {e}")]


def _invoke_agent(
    store: CatalogStore, slug: str, capability: str, params: str | None = None
) -> list[types.TextContent]:
    """Invoke an agent's capability at runtime."""
    kwargs: dict[str, Any] = {}
    if params:
        try:
            kwargs = json.loads(params)
        except json.JSONDecodeError as e:
            return [types.TextContent(type="text", text=f"Invalid JSON params: {e}")]
    try:
        result = invoke_capability(slug, capability, store=store, **kwargs)
        return [types.TextContent(type="text", text=str(result))]
    except Exception as e:
        return [types.TextContent(type="text", text=f"Error: {e}")]


def _search_agents(
    store: CatalogStore,
    capability: str | None = None,
    tool: str | None = None,
    surface: str | None = None,
    env: str | None = None,
) -> list[types.TextContent]:
    """Search agents by various criteria."""
    results = store.search(
        capability=capability,
        tool=tool,
        surface=surface,
        environment=env,
    )
    if not results:
        return [types.TextContent(type="text", text="No matching agents.")]
    parts = [f"Found {len(results)} matching agent(s):\n"]
    for a in sorted(results, key=lambda x: x.slug):
        parts.append(f"- {a.slug} ({a.name}) @ {a.environment}")
    return [types.TextContent(type="text", text="\n".join(parts))]


def create_server(store: CatalogStore | None = None) -> Server:
    """Create an MCP server exposing the agent catalog.

    Args:
        store: CatalogStore instance (default: auto-detect from env/config).
    """
    store = store or _get_store()
    server = Server("agent-catalog")

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="catalog_list_agents",
                description="List all registered agents, optionally filtered by environment",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "environment": {
                            "type": "string",
                            "description": "Filter by environment (production, staging, etc.)",
                        }
                    },
                },
            ),
            types.Tool(
                name="catalog_get_agent",
                description="Get full details for a specific agent by slug",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "slug": {
                            "type": "string",
                            "description": "Agent slug (e.g. agentic-inbox)",
                        }
                    },
                    "required": ["slug"],
                },
            ),
            types.Tool(
                name="catalog_search",
                description="Search agents by capability, tool, surface, or environment",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "capability": {
                            "type": "string",
                            "description": "Capability ID to search for",
                        },
                        "tool": {
                            "type": "string",
                            "description": "Tool name to search for",
                        },
                        "surface": {
                            "type": "string",
                            "description": "Surface type (cli, mcp, api, etc.)",
                        },
                        "environment": {
                            "type": "string",
                            "description": "Environment filter",
                        },
                    },
                },
            ),
            types.Tool(
                name="catalog_invoke",
                description=(
                    "Load an agent and invoke one of its capabilities at runtime. "
                    "The agent must have been registered via 'agent-catalog scan' "
                    "so its metadata contains python_module and python_class."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "slug": {
                            "type": "string",
                            "description": "Agent slug",
                        },
                        "capability": {
                            "type": "string",
                            "description": "Capability ID to invoke",
                        },
                        "params": {
                            "type": "string",
                            "description": "Optional JSON string of parameters",
                        },
                    },
                    "required": ["slug", "capability"],
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(
        name: str, arguments: dict[str, Any] | None
    ) -> list[types.TextContent]:
        args = arguments or {}
        try:
            if name == "catalog_list_agents":
                return _list_agents(store, env=args.get("environment"))
            elif name == "catalog_get_agent":
                return _get_agent(store, args["slug"])
            elif name == "catalog_search":
                return _search_agents(
                    store,
                    capability=args.get("capability"),
                    tool=args.get("tool"),
                    surface=args.get("surface"),
                    env=args.get("environment"),
                )
            elif name == "catalog_invoke":
                return _invoke_agent(
                    store,
                    args["slug"],
                    args["capability"],
                    params=args.get("params"),
                )
            else:
                return [types.TextContent(type="text", text=f"Unknown tool: {name}")]
        except Exception as e:
            return [types.TextContent(type="text", text=f"Error executing {name}: {e}")]

    return server


def run_server(store: CatalogStore | None = None) -> None:
    """Run the MCP server using stdio transport.

    Connects to the MCP client via stdin/stdout (the standard transport
    for MCP CLI tools).
    """
    import asyncio

    server = create_server(store)
    async def _run() -> None:
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())
    asyncio.run(_run())


if __name__ == "__main__":
    run_server()

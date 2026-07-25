"""MCP server for Agent Catalog.

Exposes the agent catalog as MCP tools with minimal token overhead.
All responses are:
  - Compact JSON or short text (no verbose prose)
  - Hard-truncated at 1500 chars per tool call
  - Lists return slugs only (not full agent text)
  - Details on demand via catalog_get_agent

Usage:
    agent-catalog serve --mcp
"""

from __future__ import annotations

import json
from typing import Any

from agent_catalog.loader import invoke_capability
from agent_catalog.storage import CatalogStore

# ── Token budget ──────────────────────────────────────────────────────────────

_MAX_RESPONSE_CHARS = 1500
"""Hard cap on text returned per tool call to limit token burn."""

_MAX_INVOKE_CHARS = 2000
"""Higher cap for invoke results (actual agent output)."""


def _truncate(text: str, limit: int = _MAX_RESPONSE_CHARS) -> str:
    """Truncate text to *limit* chars, appending a count if cut."""
    if len(text) <= limit:
        return text
    cut = text[:limit]
    # Cut at last space or newline to avoid mid-word breaks
    break_at = max(cut.rfind(" "), cut.rfind("\n"), 0)
    if break_at > limit // 2:
        cut = cut[:break_at]
    return f"{cut}\n... [{len(text) - len(cut)} more chars -- use catalog_get_agent for full details]"


def _agent_summary(a) -> str:
    """Slug and name only — densest possible agent reference."""
    return f"{a.slug}:{a.name}"


def _agent_brief(a) -> dict:
    """Compact agent dict (~200 bytes vs ~500 for full format)."""
    return {
        "s": a.slug,
        "n": a.name,
        "v": a.version,
        "e": a.environment,
        "st": a.status,
    }


_EMPTY = [{"type": "text", "text": "[]"}]
"""Pre-allocated empty response."""


def _text(text: str) -> list[dict]:
    """Build a TextContent dict (avoids importing mcp.types at module level)."""
    return [{"type": "text", "text": text}]


def _get_store() -> CatalogStore:
    import os

    root = os.environ.get("AGENT_CATALOG_DIR")
    return CatalogStore(root=root) if root else CatalogStore()


# ── Tool handlers (compact output, return dicts not mcp types) ────────────────


def _list_agents(store: CatalogStore, env: str | None = None) -> list[dict]:
    """List agents — returns compact JSON array of {slug, name, env, status}."""
    agents = store.list_all()
    if env:
        agents = [a for a in agents if a.environment == env]
    if not agents:
        return _EMPTY
    data = [_agent_brief(a) for a in sorted(agents, key=lambda x: x.slug)]
    text = json.dumps(data, separators=(",", ":"))
    return _text(_truncate(text))


def _get_agent(store: CatalogStore, slug: str) -> list[dict]:
    """Get one agent — returns compact JSON with all manifest fields."""
    try:
        a = store.get(slug)
        data = a.model_dump(mode="json", exclude_none=True)
        text = json.dumps(data, separators=(",", ":"))
        return _text(_truncate(text))
    except KeyError as e:
        return _text(_truncate(f"E:{e}"))


def _invoke_agent(
    store: CatalogStore, slug: str, capability: str, params: str | None = None
) -> list[dict]:
    """Invoke an agent capability — result is hard-truncated."""
    kwargs: dict[str, Any] = {}
    if params:
        try:
            kwargs = json.loads(params)
        except json.JSONDecodeError as e:
            return _text(_truncate(f"E:invalid JSON {e}"))
    try:
        result = invoke_capability(slug, capability, store=store, **kwargs)
        return _text(_truncate(str(result), _MAX_INVOKE_CHARS))
    except Exception as e:
        return _text(_truncate(f"E:{e}"))


def _search_agents(
    store: CatalogStore,
    capability: str | None = None,
    tool: str | None = None,
    surface: str | None = None,
    env: str | None = None,
) -> list[dict]:
    """Search agents — returns slugs-only JSON array."""
    results = store.search(
        capability=capability,
        tool=tool,
        surface=surface,
        environment=env,
    )
    if not results:
        return _EMPTY
    slugs = sorted(a.slug for a in results)
    text = json.dumps(slugs, separators=(",", ":"))
    return _text(_truncate(text))


def _handle_tool_call(
    name: str, args: dict, store: CatalogStore
) -> list[dict]:
    """Route a tool call to the right handler.

    Returns dict-based responses (type + text).  This is a module-level
    function so it can be tested without MCP transport.
    """
    try:
        if name == "catalog_list_agents":
            return _list_agents(store, env=args.get("environment"))
        elif name == "catalog_get_agent":
            return _get_agent(store, args.get("slug", ""))
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
                args.get("slug", ""),
                args.get("capability", ""),
                params=args.get("params"),
            )
        elif name == "catalog_register":
            import yaml

            from agent_catalog.schema import AgentManifest

            raw = yaml.safe_load(args.get("yaml", ""))
            if not raw:
                return _text("E:empty YAML")
            manifest = AgentManifest.model_validate(raw)
            store.register_manifest(manifest)
            return _text(f"Registered {manifest.slug}")
        else:
            return _text(f"Unknown tool: {name}")
    except Exception as e:
        return _text(f"Error executing {name}: {e}")


def create_server(store: CatalogStore | None = None):
    """Create an MCP server exposing the agent catalog.

    Args:
        store: CatalogStore instance (default: auto-detect from env/config).
    """
    import mcp.types as types
    from mcp.server.lowlevel import Server

    store = store or _get_store()
    server = Server("agent-catalog")

    def _tc(result: list[dict]) -> list[types.TextContent]:
        """Convert dict-based responses to TextContent."""
        return [types.TextContent(type=r["type"], text=r["text"]) for r in result]

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
            types.Tool(
                name="catalog_register",
                description="Register a new agent manifest in the catalog",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "yaml": {
                            "type": "string",
                            "description": "YAML manifest content to register",
                        },
                    },
                    "required": ["yaml"],
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(
        name: str, arguments: dict[str, Any] | None
    ) -> list[types.TextContent]:
        args = arguments or {}
        result = _handle_tool_call(name, args, store)
        return _tc(result)

    return server


def run_server(store: CatalogStore | None = None) -> None:
    """Run the MCP server using stdio transport.

    Connects to the MCP client via stdin/stdout (the standard transport
    for MCP CLI tools).
    """
    import asyncio

    import mcp.server.stdio

    server = create_server(store)
    async def _run() -> None:
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())
    asyncio.run(_run())


if __name__ == "__main__":
    run_server()

"""Agent Catalog — Declarative agent registry.

Discover, diff, and manage agent capabilities across environments.

Decorator API (new in 0.2.0):

    from agent_catalog import agent, capability, tool, interface, dependency
    from agent_catalog.decorators import build_manifest
"""

from __future__ import annotations

from agent_catalog.decorators import (
    agent,
    build_manifest,
    capability,
    dependency,
    interface,
    tool,
)

__all__ = [
    "agent",
    "build_manifest",
    "capability",
    "dependency",
    "interface",
    "tool",
]

__version__ = "0.2.0"

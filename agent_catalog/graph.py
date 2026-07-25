"""Dependency graph generator for agent catalog.

Produces Mermaid diagrams and JSON graph representations of
how agents depend on each other.
"""

from __future__ import annotations

from agent_catalog.storage import CatalogStore


def build_graph(store: CatalogStore) -> dict:
    """Build a dependency graph from all registered agents.

    Resolves agent dependencies by slug/name lookup (O(n) per agent
    using a set, rather than O(n²) nested loops).
    """
    agents = store.list_all()

    nodes: list[dict] = []
    edges: list[dict] = []

    # Build a set of all known agent identifiers (slug + lower name)
    known: set[str] = set()
    for a in agents:
        known.add(a.slug)
        known.add(a.name.lower())

    for a in agents:
        nodes.append(
            {
                "id": a.slug,
                "label": a.name,
                "environment": a.environment,
                "status": a.status,
                "capability_count": len(a.capabilities),
            }
        )

        for dep in a.dependencies:
            edges.append(
                {
                    "source": a.slug,
                    "target": dep.name,
                    "type": dep.type,
                    "required": dep.required,
                }
            )

            # If the dependency matches a known agent, emit reverse edge
            if dep.name in known or dep.name.lower() in known:
                edges.append(
                    {
                        "source": dep.name,
                        "target": a.slug,
                        "type": "agent-dependency",
                        "required": dep.required,
                    }
                )

    return {"nodes": nodes, "edges": edges}


def to_mermaid(store: CatalogStore) -> str:
    """Render the dependency graph as a Mermaid flowchart."""
    agents = store.list_all()

    lines = ["graph TD"]
    node_ids: dict[str, str] = {}

    for i, agent in enumerate(agents):
        nid = f"A{i}"
        node_ids[agent.slug] = nid
        status_icon = "\u25cf" if agent.status == "active" else "\u25cb"
        lines.append(f"    {nid}[{status_icon} {agent.name}]")

    for agent in agents:
        sid = node_ids.get(agent.slug)
        if sid is None:
            continue
        for dep in agent.dependencies:
            tid = node_ids.get(dep.name)
            if tid:
                style = "==>" if dep.required else "-.->"
                lines.append(f"    {sid} {style} {tid}")

    return "\n".join(lines)

"""Dependency graph generator for agent catalog.

Produces Mermaid diagrams and JSON graph representations of
how agents depend on each other.
"""

from __future__ import annotations

from agent_catalog.storage import CatalogStore


def build_graph(store: CatalogStore) -> dict:
    """Build a dependency graph from all registered agents."""
    nodes: list[dict] = []
    edges: list[dict] = []

    for agent in store.list_all():
        nodes.append(
            {
                "id": agent.slug,
                "label": agent.name,
                "environment": agent.environment,
                "status": agent.status,
                "capability_count": len(agent.capabilities),
            }
        )
        for dep in agent.dependencies:
            edges.append(
                {
                    "source": agent.slug,
                    "target": dep.name,
                    "type": dep.type,
                    "required": dep.required,
                }
            )

    # Mark agents as dependents of each other
    for agent in store.list_all():
        for other in store.list_all():
            if agent.slug == other.slug:
                continue
            for dep in other.dependencies:
                if dep.name == agent.slug or dep.name == agent.name.lower():
                    edges.append(
                        {
                            "source": other.slug,
                            "target": agent.slug,
                            "type": "agent-dependency",
                            "required": dep.required,
                        }
                    )

    return {"nodes": nodes, "edges": edges}


def to_mermaid(store: CatalogStore) -> str:
    """Render the dependency graph as a Mermaid flowchart."""
    lines = ["graph TD"]
    node_ids: dict[str, str] = {}

    for i, agent in enumerate(store.list_all()):
        nid = f"A{i}"
        node_ids[agent.slug] = nid
        status_icon = "●" if agent.status == "active" else "○"
        lines.append(f"    {nid}[{status_icon} {agent.name}]")

    for agent in store.list_all():
        sid = node_ids[agent.slug]
        for dep in agent.dependencies:
            if dep.name in node_ids:
                tid = node_ids[dep.name]
                style = "==>" if dep.required else "-.->"
                lines.append(f"    {sid} {style} {tid}")

    return "\n".join(lines)

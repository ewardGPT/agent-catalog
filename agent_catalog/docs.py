"""Generate markdown documentation for registered agents."""

from __future__ import annotations

from agent_catalog.storage import CatalogStore


def generate_docs(store: CatalogStore | None = None) -> str:
    """Generate a markdown document describing all registered agents."""
    from agent_catalog.storage import CatalogStore

    store = store or CatalogStore()
    agents = store.list_all()

    if not agents:
        return "# Agent Catalog\n\n*No agents registered.*\n"

    lines = [
        "# Agent Catalog",
        "",
        f"**{len(agents)} agent(s) registered**",
        "___",
        "",
    ]

    for a in sorted(agents, key=lambda x: x.slug):
        lines.append(f"## {a.name} (`{a.slug}`)")
        lines.append("")
        lines.append(f"- **Version:** {a.version}")
        lines.append(f"- **Environment:** {a.environment}")
        lines.append(f"- **Status:** {a.status}")
        lines.append(f"- **Description:** {a.description}")
        if a.model:
            lines.append(f"- **Model:** {a.model.provider}/{a.model.name}")
        if a.labels:
            lines.append(f"- **Labels:** {', '.join(a.labels)}")
        if a.interfaces:
            for iface in a.interfaces:
                lines.append(f"- **Interface:** {iface.type.value} at {iface.path or '/'} (auth={'yes' if iface.auth_required else 'no'})")
        lines.append("")

        if a.capabilities:
            lines.append("### Capabilities")
            lines.append("")
            lines.append("| ID | Description | Tools | Surfaces | Confirmation | Side Effects |")
            lines.append("|---|---|---|---|---|---|")
            for cap in a.capabilities:
                tools = ", ".join(cap.tools) if cap.tools else "—"
                surfaces = ", ".join(s.value for s in cap.surfaces) if cap.surfaces else "—"
                effects = ", ".join(e.value for e in cap.side_effects) if cap.side_effects else "—"
                confirm = "yes" if cap.requires_confirmation else "no"
                lines.append(f"| {cap.id} | {cap.description} | {tools} | {surfaces} | {confirm} | {effects} |")
            lines.append("")

        if a.tools:
            lines.append("### Tools")
            lines.append("")
            for t in a.tools:
                params_desc = ""
                if t.parameters and "properties" in t.parameters:
                    props = list(t.parameters["properties"].keys())
                    if props:
                        params_desc = f" — params: {', '.join(props)}"
                lines.append(f"- **{t.name}**: {t.description}{params_desc}")
            lines.append("")

        if a.dependencies:
            lines.append("### Dependencies")
            lines.append("")
            for d in a.dependencies:
                required = "required" if d.required else "optional"
                lines.append(f"- **{d.name}** ({d.type}, {required}): {d.description}")
            lines.append("")

        lines.append("___")
        lines.append("")

    return "\n".join(lines)

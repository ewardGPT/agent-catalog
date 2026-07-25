"""CRUD commands: register, list, get, search, validate, unregister, update."""

from __future__ import annotations

from pathlib import Path

import typer
import yaml
from rich.table import Table

from agent_catalog.cli import _get_store, _render_manifest, app, console
from agent_catalog.schema import AgentManifest


@app.command()
def register(
    manifest: str = typer.Argument(..., help="Path to agent manifest YAML file"),
):
    """Register an agent from a manifest file."""
    try:
        agent = _get_store().register(Path(manifest))
        console.print(f"[green]\u2713[/] Registered [bold]{agent.slug}[/] @ {agent.environment}")
        console.print(_render_manifest(agent))
    except Exception as e:
        console.print(f"[red]\u2717[/] Failed to register: {e}")
        raise typer.Exit(code=1) from e


@app.command()
def list(
    environment: str | None = typer.Option(None, "--env", "-e", help="Filter by environment"),
):
    """List all registered agents."""
    agents = _get_store().list_all()
    if environment:
        agents = [a for a in agents if a.environment == environment]

    if not agents:
        console.print("[yellow]No agents registered.[/]")
        return

    table = Table(title="Agent Catalog")
    table.add_column("Slug", style="cyan")
    table.add_column("Name", style="bold")
    table.add_column("Version")
    table.add_column("Environment")
    table.add_column("Capabilities")
    table.add_column("Status")

    for a in sorted(agents, key=lambda x: x.slug):
        table.add_row(
            a.slug,
            a.name,
            a.version,
            a.environment,
            ", ".join(c.id for c in a.capabilities[:3])
            + ("..." if len(a.capabilities) > 3 else ""),
            a.status,
        )

    console.print(table)
    console.print(f"[dim]{len(agents)} agent(s)[/]")


@app.command()
def get(
    slug: str = typer.Argument(..., help="Agent slug to retrieve"),
):
    """Show full details for an agent."""
    try:
        agent = _get_store().get(slug)
        console.print(_render_manifest(agent))
    except (KeyError, FileNotFoundError) as e:
        console.print(f"[red]\u2717[/] {e}")
        raise typer.Exit(code=1) from e


@app.command()
def search(
    capability: str | None = typer.Option(
        None, "--capability", "-c", help="Search by capability ID"
    ),
    tool: str | None = typer.Option(None, "--tool", "-t", help="Search by tool name"),
    surface: str | None = typer.Option(None, "--surface", "-s", help="Search by interface surface"),
    environment: str | None = typer.Option(None, "--env", "-e", help="Filter by environment"),
):
    """Search agents by capability, tool, surface, or environment."""
    results = _get_store().search(
        capability=capability,
        tool=tool,
        surface=surface,
        environment=environment,
    )

    if not results:
        console.print("[yellow]No matching agents.[/]")
        return

    table = Table(title=f"Search Results ({len(results)})")
    table.add_column("Slug", style="cyan")
    table.add_column("Name")
    table.add_column("Environment")
    table.add_column("Capabilities")
    table.add_column("Tools")
    table.add_column("Surfaces")

    for a in sorted(results, key=lambda x: x.slug):
        table.add_row(
            a.slug,
            a.name,
            a.environment,
            ", ".join(c.id for c in a.capabilities),
            ", ".join(t.name for t in a.tools),
            ", ".join(s.type.value for s in a.interfaces),
        )

    console.print(table)


@app.command()
def validate(
    manifest: str = typer.Argument(..., help="Path to manifest YAML to validate"),
):
    """Validate a manifest file without registering it."""
    try:
        raw = yaml.safe_load(Path(manifest).read_text())
        if raw is None:
            console.print("[red]\u2717[/] Empty or invalid YAML.")
            raise typer.Exit(1)
        m = AgentManifest.model_validate(raw)
        console.print(f"[green]\u2713[/] Valid: [bold]{m.slug}[/] ({m.name})")
    except Exception as e:
        console.print(f"[red]\u2717[/] Validation failed: {e}")
        raise typer.Exit(1) from e


@app.command()
def unregister(
    slug: str = typer.Argument(..., help="Agent slug to remove"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Remove an agent from the catalog."""
    if not force:
        typer.confirm(f"Remove '{slug}' from the catalog?", abort=True)
    if _get_store().unregister(slug):
        console.print(f"[green]\u2713[/] Unregistered [bold]{slug}[/]")
    else:
        console.print(f"[yellow]Agent '{slug}' not found.[/]")


@app.command()
def update(
    slug: str = typer.Argument(..., help="Agent slug to update"),
    manifest: str = typer.Argument(..., help="Path to updated manifest YAML"),
):
    """Update an existing agent's manifest."""
    try:
        raw = yaml.safe_load(Path(manifest).read_text())
        updated = AgentManifest.model_validate(raw)
        result = _get_store().update(slug, updated)
        console.print(f"[green]\u2713[/] Updated [bold]{result.slug}[/]")
        console.print(_render_manifest(result))
    except Exception as e:
        console.print(f"[red]\u2717[/] Update failed: {e}")
        raise typer.Exit(1) from e

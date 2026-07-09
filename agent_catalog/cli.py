"""CLI entry point for Agent Catalog.

Usage:
    agent-catalog register ./agent.yaml
    agent-catalog list
    agent-catalog get agentic-inbox
    agent-catalog search --capability send_email
    agent-catalog diff agentic-inbox --right staging
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from agent_catalog.diff import diff_manifests
from agent_catalog.schema import AgentManifest
from agent_catalog.storage import CatalogStore

app = typer.Typer(
    name="agent-catalog",
    help="Declarative agent registry — catalog, discover, and diff agent capabilities.",
    no_args_is_help=True,
)

console = Console()


def _get_store() -> CatalogStore:
    """Resolve the catalog store, respecting AGENT_CATALOG_DIR env var."""
    import os

    root = os.environ.get("AGENT_CATALOG_DIR")
    return CatalogStore(root=root) if root else CatalogStore()


# ── Helpers ────────────────────────────────────────────────────────────────────


def _render_manifest(m: AgentManifest) -> Panel:
    """Pretty-print an agent manifest."""
    rows: list[str] = []
    rows.append(f"[bold]Name:[/]         {m.name}")
    rows.append(f"[bold]Slug:[/]         {m.slug}")
    rows.append(f"[bold]Version:[/]      {m.version}")
    rows.append(f"[bold]Environment:[/]  {m.environment}")
    rows.append(f"[bold]Status:[/]       {m.status}")
    rows.append(f"[bold]Description:[/]  {m.description}")
    if m.model:
        rows.append(f"[bold]Model:[/]        {m.model.provider}/{m.model.name}")
    if m.capabilities:
        rows.append(f"[bold]Capabilities:[/] {', '.join(c.id for c in m.capabilities)}")
    if m.tools:
        rows.append(f"[bold]Tools:[/]        {', '.join(t.name for t in m.tools)}")
    if m.prompt:
        versions = ", ".join(p.version for p in m.prompt)
        rows.append(f"[bold]Prompts:[/]      {versions}")
    if m.dependencies:
        deps = ", ".join(d.name for d in m.dependencies)
        rows.append(f"[bold]Dependencies:[/] {deps}")
    if m.eval_contract:
        suites = ", ".join(m.eval_contract.suites)
        rows.append(f"[bold]Eval Suites:[/]  {suites}")

    text = "\n".join(rows)
    return Panel(Text.from_markup(text), title=m.environment_tag())


# ── Commands ───────────────────────────────────────────────────────────────────


@app.command()
def register(
    manifest: str = typer.Argument(..., help="Path to agent manifest YAML file"),
):
    """Register an agent from a manifest file."""
    try:
        agent = _get_store().register(Path(manifest))
        console.print(f"[green]✓[/] Registered [bold]{agent.slug}[/] @ {agent.environment}")
        console.print(_render_manifest(agent))
    except Exception as e:
        console.print(f"[red]✗[/] Failed to register: {e}")
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
        console.print(f"[red]✗[/] {e}")
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
def diff(
    slug: str = typer.Argument(..., help="Slug of the primary agent"),
    right: str | None = typer.Option(
        None,
        "--right",
        "-r",
        help="Path to another manifest to diff against (default: auto-look for staging)",
    ),
    right_env: str | None = typer.Option(
        None,
        "--right-env",
        help="Environment snapshot to compare (from metadata.environments)",
    ),
):
    """Show structured diff between two manifests or environments."""
    try:
        left = _get_store().get(slug)
    except KeyError:
        console.print(f"[red]✗[/] Agent '{slug}' not registered.")
        raise typer.Exit(1) from None

    if right:
        right_manifest = AgentManifest.model_validate(
            __import__("yaml").safe_load(Path(right).read_text())
        )
        right_manifest.environment = right_manifest.environment or "external"
    elif right_env:
        # Compare against a stored environment snapshot in metadata
        envs = left.metadata.get("environments", {})
        if right_env not in envs:
            console.print(f"[red]✗[/] No '{right_env}' snapshot in {slug} metadata.")
            raise typer.Exit(1)
        right_data = envs[right_env]
        right_manifest = left.model_copy(update=right_data)
        right_manifest.environment = right_env
    else:
        # Try to find staging
        try:
            right_manifest = _get_store().search(environment="staging")
            if not right_manifest:
                console.print("[yellow]No staging manifest found. Try --right or --right-env.[/]")
                raise typer.Exit(0)
            right_manifest = right_manifest[0]
        except Exception:
            console.print("[yellow]No staging manifest found. Try --right or --right-env.[/]")
            raise typer.Exit(0) from None

    report = diff_manifests(left, right_manifest)
    console.print(report.summary)


@app.command()
def validate(
    manifest: str = typer.Argument(..., help="Path to manifest YAML to validate"),
):
    """Validate a manifest file without registering it."""
    try:
        raw = __import__("yaml").safe_load(Path(manifest).read_text())
        if raw is None:
            console.print("[red]✗[/] Empty or invalid YAML.")
            raise typer.Exit(1)
        _ = AgentManifest.model_validate(raw)
        console.print(f"[green]✓[/] Valid: [bold]{_.slug}[/] ({_.name})")
    except Exception as e:
        console.print(f"[red]✗[/] Validation failed: {e}")
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
        console.print(f"[green]✓[/] Unregistered [bold]{slug}[/]")
    else:
        console.print(f"[yellow]Agent '{slug}' not found.[/]")


@app.command()
def update(
    slug: str = typer.Argument(..., help="Agent slug to update"),
    manifest: str = typer.Argument(..., help="Path to updated manifest YAML"),
):
    """Update an existing agent's manifest."""
    try:
        raw = __import__("yaml").safe_load(Path(manifest).read_text())
        updated = AgentManifest.model_validate(raw)
        result = _get_store().update(slug, updated)
        console.print(f"[green]✓[/] Updated [bold]{result.slug}[/]")
        console.print(_render_manifest(result))
    except Exception as e:
        console.print(f"[red]✗[/] Update failed: {e}")
        raise typer.Exit(1) from e


def main() -> None:
    """Entry point for the 'agent-catalog' command."""
    app()


if __name__ == "__main__":
    main()

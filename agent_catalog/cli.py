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
        help="Path to another manifest YAML to diff against",
    ),
    left_env: str | None = typer.Option(
        None,
        "--left-env",
        help="Environment for the left side (from metadata.environments snapshots)",
    ),
    right_env: str | None = typer.Option(
        None,
        "--right-env",
        help="Environment for the right side. Use with a second slug via --slug2 for cross-agent env diff",
    ),
    slug2: str | None = typer.Option(
        None,
        "--slug2",
        help="Second agent slug to diff against (for cross-agent comparison)",
    ),
):
    """Show structured diff between two manifests, environments, or agents.

    Modes:
      agent-catalog diff agentic-inbox --right-env staging
        Compare agentic-inbox's production manifest against its staging snapshot

      agent-catalog diff agentic-inbox --left-env staging --right-env production
        Compare staging and production snapshots from metadata.environments

      agent-catalog diff agentic-inbox --slug2 nexusgate
        Cross-agent comparison: agentic-inbox vs nexusgate

      agent-catalog diff agentic-inbox --right ./external.yaml
        Compare registered agent against an external manifest file
    """
    try:
        left = _get_store().get(slug)
    except KeyError:
        console.print(f"[red]✗[/] Agent '{slug}' not registered.")
        raise typer.Exit(1) from None

    # Resolve left manifest (with optional env overlay)
    left_manifest = left
    if left_env:
        envs = left.metadata.get("environments", {})
        if left_env not in envs:
            console.print(f"[red]✗[/] No '{left_env}' snapshot in {slug} metadata.")
            raise typer.Exit(1)
        left_data = envs[left_env]
        left_manifest = left.model_copy(update=left_data)
        left_manifest.environment = left_env

    # Resolve right manifest
    if right:
        # External file
        right_manifest = AgentManifest.model_validate(
            __import__("yaml").safe_load(Path(right).read_text())
        )
        right_manifest.environment = right_manifest.environment or "external"
    elif slug2:
        # Cross-agent comparison
        try:
            right_manifest = _get_store().get(slug2)
        except KeyError:
            console.print(f"[red]✗[/] Agent '{slug2}' not registered.")
            raise typer.Exit(1) from None
        if right_env:
            envs = right_manifest.metadata.get("environments", {})
            if right_env not in envs:
                console.print(f"[red]✗[/] No '{right_env}' snapshot in {slug2} metadata.")
                raise typer.Exit(1)
            right_data = envs[right_env]
            right_manifest = right_manifest.model_copy(update=right_data)
            right_manifest.environment = right_env
    elif right_env:
        # Same agent, env snapshot from metadata
        envs = left.metadata.get("environments", {})
        if right_env not in envs:
            console.print(f"[red]✗[/] No '{right_env}' snapshot in {slug} metadata.")
            raise typer.Exit(1)
        right_data = envs[right_env]
        right_manifest = left.model_copy(update=right_data)
        right_manifest.environment = right_env
    else:
        # Auto-find: try staging environment, then fall back to any second registered agent
        second = _get_store().search(environment="staging")
        if second:
            right_manifest = second[0]
        else:
            all_agents = _get_store().list_all()
            others = [a for a in all_agents if a.slug != slug]
            if others:
                right_manifest = others[0]
                console.print(
                    f"[dim]Comparing against '{right_manifest.slug}' (no staging found)[/]"
                )
            else:
                console.print(
                    "[yellow]No second manifest to diff against. Try --right, --slug2, or --right-env.[/]"
                )
                raise typer.Exit(0)

    report = diff_manifests(left_manifest, right_manifest)
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
def export_contract(
    slug: str = typer.Argument(..., help="Agent slug to export contract for"),
    output: str | None = typer.Option(
        None, "--output", "-o", help="Output file path (default: stdout)"
    ),
):
    """Export a manifest's eval contract as eval-harness compatible YAML."""
    try:
        agent = _get_store().get(slug)
    except KeyError:
        console.print(f"[red]✗[/] Agent '{slug}' not registered.")
        raise typer.Exit(1) from None

    ec = agent.eval_contract
    if not ec or not ec.suites:
        console.print(f"[yellow]No eval contract defined for '{slug}'.[/]")
        raise typer.Exit(1)

    contract_yaml = {
        "project": ec.project or agent.slug,
        "coverage_required": ec.coverage_required,
        "suites": ec.suites,
        "agent": {
            "slug": agent.slug,
            "version": agent.version,
            "environment": agent.environment,
            "capabilities": [c.id for c in agent.capabilities],
            "model": f"{agent.model.provider}/{agent.model.name}" if agent.model else None,
        },
    }

    yaml_text = __import__("yaml").dump(contract_yaml, sort_keys=False, default_flow_style=False)

    if output:
        Path(output).write_text(yaml_text)
        console.print(f"[green]✓[/] Contract exported to [bold]{output}[/]")
    else:
        console.print(yaml_text)


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


@app.command()
def sync(
    directory: str = typer.Argument(".", help="Directory to scan for agent manifests"),
    pattern: str = typer.Option(
        "agent.yaml",
        "--pattern",
        "-p",
        help="Filename pattern to match",
    ),
    env: str = typer.Option(
        "production", "--env", "-e", help="Default environment for discovered agents"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be registered without doing it"
    ),
):
    """Auto-discover and register agent manifests from a project directory."""
    root = Path(directory).resolve()
    if not root.exists():
        console.print(f"[red]✗[/] Directory not found: {root}")
        raise typer.Exit(1)

    manifests = _find_manifests(root, pattern)
    if not manifests:
        console.print(f"[yellow]No files matching '{pattern}' in {root}[/]")
        return

    console.print(f"[bold]Found {len(manifests)} manifest(s):[/]")

    registered = 0
    skipped = 0

    for path in manifests:
        rel = path.relative_to(root)
        try:
            raw = __import__("yaml").safe_load(path.read_text())
            if not raw or "name" not in raw:
                console.print(f"  [yellow]⚠[/] {rel}: not a valid agent manifest (missing 'name')")
                skipped += 1
                continue

            manifest = AgentManifest.model_validate(raw)
            if not manifest.environment or manifest.environment == "production":
                manifest.environment = env

            if not dry_run:
                _get_store().register(path)
                console.print(f"  [green]✓[/] {rel} → {manifest.slug} @ {manifest.environment}")
            else:
                console.print(
                    f"  [dim]would register {rel} → {manifest.slug} @ {manifest.environment}[/]"
                )
            registered += 1
        except Exception as e:
            console.print(f"  [red]✗[/] {rel}: {e}")
            skipped += 1

    if not dry_run:
        console.print(
            f"\n[green]✓[/] Registered [bold]{registered}[/] agent(s) (skipped {skipped})"
        )
    else:
        console.print(f"\n[dim]Dry run: would register {registered}, skip {skipped}[/]")


def _find_manifests(root: Path, pattern: str) -> list[Path]:
    """Find manifest files using manual directory scan (workaround for broken rglob)."""
    import fnmatch
    import os

    results: list[Path] = []
    # Try Python glob first (works in most environments)
    try:
        py_results = list(root.glob(pattern))
        if py_results:
            return sorted(py_results)
    except Exception:
        pass

    # Fallback: manual scan with os.scandir
    for dirpath, _dirnames, filenames in os.walk(str(root)):
        for f in filenames:
            if fnmatch.fnmatch(f, "agent.yaml") or fnmatch.fnmatch(f, "*.yaml"):
                full = Path(dirpath) / f
                if fnmatch.fnmatch(str(full.relative_to(root)), pattern):
                    results.append(full)

    # Also scan immediate subdirs explicitly for agent.yaml
    for entry in os.scandir(str(root)):
        if entry.is_dir() and not entry.name.startswith("."):
            candidate = Path(entry.path) / "agent.yaml"
            if candidate.exists() and candidate not in results:
                results.append(candidate)

    return sorted(results)


@app.command()
def security_audit(
    output_format: str = typer.Option("table", "--format", "-f", help="Output: table, json"),
):
    """Audit all registered agents for security gaps."""
    from agent_catalog.security import audit_catalog

    findings = audit_catalog(_get_store())
    if not findings:
        console.print("[green]No security issues found[/]")
        return

    if output_format == "json":
        import json

        console.print(
            json.dumps(
                [
                    {"severity": f.severity, "agent": f.agent, "title": f.title, "detail": f.detail}
                    for f in findings
                ],
                indent=2,
            )
        )
        return

    table = Table(title="Security Audit")
    table.add_column("Severity", style="bold")
    table.add_column("Agent")
    table.add_column("Issue")
    table.add_column("Detail", style="dim")

    for f in findings:
        color = {"critical": "red", "high": "yellow", "medium": "dim", "low": "dim"}[f.severity]
        table.add_row(f"[{color}]{f.severity}[/]", f.agent, f.title, f.detail)

    console.print(table)
    crit = sum(1 for f in findings if f.severity == "critical")
    high = sum(1 for f in findings if f.severity == "high")
    console.print(f"[bold]Summary:[/] {len(findings)} findings ({crit} critical, {high} high)")


@app.command()
def graph(
    output_format: str = typer.Option("mermaid", "--format", "-f", help="Output: mermaid, json"),
):
    """Show agent dependency graph."""
    from agent_catalog.graph import build_graph, to_mermaid

    store = _get_store()
    if output_format == "json":
        import json

        console.print_json(json.dumps(build_graph(store), default=str))
    else:
        console.print(to_mermaid(store))


@app.command()
def serve(
    port: int = typer.Option(8420, "--port", "-p", help="HTTP port"),
):
    """Start the Agent Marketplace web dashboard."""
    from agent_catalog.serve import serve as run_serve

    run_serve(port=port, store=_get_store())


@app.command()
def scan(
    directory: str = typer.Argument(".", help="Directory to scan for decorated agent classes"),
    pattern: str = typer.Option(
        "**/*.py",
        "--pattern",
        "-p",
        help="Glob pattern for Python files",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be registered without doing it"
    ),
):
    """Discover @agent-decorated classes and register them.

    Scans Python files for classes decorated with @agent, builds manifests,
    and registers them in the catalog.
    """

    from agent_catalog.discovery import scan_directory

    root = Path(directory).resolve()
    if not root.exists():
        console.print(f"[red]✗[/] Directory not found: {root}")
        raise typer.Exit(1)

    found = scan_directory(root, pattern=pattern)
    if not found:
        console.print(f"[yellow]No @agent-decorated classes found in {root}[/]")
        return

    console.print(f"[bold]Found {len(found)} agent class(es):[/]")

    registered = 0
    skipped = 0

    for path, cls in found:
        rel = path.relative_to(root)
        try:
            from agent_catalog.decorators import build_manifest

            manifest = build_manifest(cls)
            meta = dict(manifest.metadata)
            meta["python_module"] = str(path.resolve())
            meta["python_class"] = cls.__name__
            manifest.metadata = meta
            if not dry_run:
                _get_store().register_manifest(manifest)
                console.print(
                    f"  [green]✓[/] {rel} → [bold]{manifest.slug}[/] @ {manifest.environment}"
                )
            else:
                console.print(
                    f"  [dim]would register {rel} → {manifest.slug} @ {manifest.environment}[/]"
                )
            registered += 1
        except Exception as e:
            console.print(f"  [red]✗[/] {rel}: {e}")
            skipped += 1

    if not dry_run:
        console.print(
            f"\n[green]✓[/] Registered [bold]{registered}[/] agent(s) (skipped {skipped})"
        )
    else:
        console.print(f"\n[dim]Dry run: would register {registered}, skip {skipped}[/]")


@app.command()
def inspect(
    path: str = typer.Argument(..., help="Path to Python file with @agent-decorated class"),
    format: str = typer.Option("yaml", "--format", "-f", help="Output format: yaml, json"),
):
    """Inspect a Python file and show the generated agent manifest.

    Imports the file, finds @agent classes, builds manifests, and
    displays them without registering.
    """
    import json

    import yaml

    from agent_catalog.discovery import scan_module

    file_path = Path(path).resolve()
    if not file_path.exists():
        console.print(f"[red]✗[/] File not found: {file_path}")
        raise typer.Exit(1)

    from agent_catalog.decorators import build_manifest

    classes = scan_module(file_path)
    if not classes:
        console.print(f"[yellow]No @agent-decorated classes found in {file_path}[/]")
        return

    for i, cls in enumerate(classes):
        try:
            manifest = build_manifest(cls)
            data = manifest.model_dump(mode="json", exclude_none=True)

            if format == "json":
                console.print_json(json.dumps(data, default=str, indent=2))
            else:
                yaml_text = yaml.dump(
                    data, sort_keys=False, default_flow_style=False, allow_unicode=True
                )
                console.print(yaml_text)

            if i < len(classes) - 1:
                console.print("---")
        except Exception as e:
            console.print(f"[red]✗[/] {cls.__name__}: {e}")


@app.command()
def run(
    slug: str = typer.Argument(..., help="Agent slug"),
    capability: str = typer.Argument(..., help="Capability ID to invoke"),
    params: str | None = typer.Option(None, "--params", "-p", help="JSON string of parameters"),
):
    """Load an agent and invoke a capability at runtime.

    Uses metadata.python_module / metadata.python_class to find and
    import the agent class, then calls the capability method.

    Examples:
        agent-catalog run my-agent greet
        agent-catalog run my-agent greet --params '{"name": "World"}'
    """
    import json

    from agent_catalog.loader import invoke_capability

    kwargs: dict = {}
    if params:
        try:
            kwargs = json.loads(params)
        except json.JSONDecodeError as e:
            console.print(f"[red]✗[/] Invalid JSON in --params: {e}")
            raise typer.Exit(1) from e

    try:
        result = invoke_capability(slug, capability, store=_get_store(), **kwargs)
        console.print(result)
    except Exception as e:
        console.print(f"[red]✗[/] {e}")
        raise typer.Exit(1) from e


def main() -> None:
    """Entry point for the 'agent-catalog' command."""
    app()


if __name__ == "__main__":
    main()

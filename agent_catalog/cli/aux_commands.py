"""Auxiliary commands: security-audit, graph, serve, run, doctor."""

from __future__ import annotations

import json

import typer

from agent_catalog.cli import _get_store, app, console


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

    from rich.table import Table

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
        console.print_json(json.dumps(build_graph(store), default=str))
    else:
        console.print(to_mermaid(store))


@app.command()
def serve(
    port: int = typer.Option(8420, "--port", "-p", help="HTTP port"),
    mcp: bool = typer.Option(False, "--mcp", help="Run MCP server instead of HTTP (stdio transport)"),
):
    """Start the Agent Marketplace web dashboard.

    By default starts an HTTP server.  Pass --mcp to run as an MCP
    server over stdio (for use with MCP clients like Claude Code).
    """
    if mcp:
        from agent_catalog.mcp_server import run_server

        run_server(store=_get_store())
    else:
        from agent_catalog.serve import serve as run_serve

        run_serve(port=port, store=_get_store())


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
    from agent_catalog.loader import invoke_capability

    kwargs: dict = {}
    if params:
        try:
            kwargs = json.loads(params)
        except json.JSONDecodeError as e:
            console.print(f"[red]\u2717[/] Invalid JSON in --params: {e}")
            raise typer.Exit(1) from e

    try:
        result = invoke_capability(slug, capability, store=_get_store(), **kwargs)
        console.print(result)
    except Exception as e:
        console.print(f"[red]\u2717[/] {e}")
        raise typer.Exit(1) from e


@app.command()
def doctor():
    """Check catalog consistency (orphaned files, missing manifests).

    Scans the catalog directory and verifies every indexed agent
    has a manifest file on disk, and every YAML file is indexed.
    """
    store = _get_store()
    issues = store.check_consistency()

    if not issues:
        console.print("[green]\u2713[/] Catalog is consistent")
        return

    console.print(f"[yellow]Found {len(issues)} issue(s):[/]")
    for issue in issues:
        prefix = "[red]MISSING[/]" if issue.startswith("MISSING") else "[yellow]ORPHAN[/]"
        console.print(f"  {prefix} {issue}")
    raise typer.Exit(1)


@app.command()
def docs(
    output: str | None = typer.Option(
        None, "--output", "-o", help="Output file path (default: stdout)"
    ),
):
    """Generate markdown documentation for all registered agents."""
    from pathlib import Path

    from agent_catalog.docs import generate_docs

    md = generate_docs(_get_store())
    if output:
        Path(output).write_text(md)
        console.print(f"[green]\u2713[/] Docs written to [bold]{output}[/]")
    else:
        console.print(md)


@app.command()
def publish(
    message: str | None = typer.Option(
        None, "--message", "-m", help="Commit message for the publish"
    ),
):
    """Push agent manifests to the remote git registry.

    Requires AGENT_CATALOG_REMOTE env var or remote.url in config.
    """
    from agent_catalog.remote import publish as _publish

    _publish(message=message)


@app.command()
def pull():
    """Pull agent manifests from the remote git registry.

    Requires AGENT_CATALOG_REMOTE env var or remote.url in config.
    """
    from agent_catalog.remote import pull as _pull

    _pull()


@app.command()
def verify():
    """Verify every agent can be loaded and instantiated.

    Iterates all registered agents, attempts to import their Python
    class and create an instance.  Reports failures without stopping.
    """
    store = _get_store()
    agents = store.list_all()
    from agent_catalog.loader import LoaderError, load_agent_class

    passed = 0
    failed = 0
    for a in agents:
        try:
            cls = load_agent_class(a.slug, store=store)
            cls()
            passed += 1
        except LoaderError as e:
            console.print(f"[red]\u2717[/] {a.slug}: {e}")
            failed += 1
        except Exception as e:
            console.print(f"[yellow]\u26a0[/] {a.slug}: class found but instantiation failed: {e}")
            failed += 1

    if failed:
        console.print(f"[yellow]Verified {passed} agent(s), {failed} failed[/]")
        raise typer.Exit(1)
    else:
        console.print(f"[green]\u2713[/] All {passed} agent(s) verified successfully")


@app.command()
def sync(
    directory: str = typer.Argument(".", help="Directory to scan"),
    pattern: str = typer.Option("agent.yaml", "--pattern", "-p", help="Filename pattern"),
    env: str = typer.Option("production", "--env", "-e", help="Default environment"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be done"),
    watch: bool = typer.Option(False, "--watch", "-w", help="Watch directory for changes (poll every 10s)"),
):
    """Auto-discover and register agent manifests from a directory.

    With --watch, polls the directory every 10 seconds for new or
    changed manifests and registers them automatically.
    """
    from agent_catalog.cli.discover_commands import _sync_impl

    if watch:
        _sync_watch(directory, pattern, env)
    else:
        _sync_impl(directory, pattern, env, dry_run, _get_store, console)


def _sync_watch(directory: str, pattern: str, env: str) -> None:
    """Poll a directory every 10s for new/changed manifests."""
    import hashlib
    import time
    from pathlib import Path

    from agent_catalog.cli.discover_commands import _sync_impl

    root = Path(directory).resolve()
    if not root.exists():
        console.print(f"[red]\u2717[/] Directory not found: {root}")
        raise typer.Exit(1)

    console.print(f"[dim]Watching {root} for manifests matching '{pattern}'...[/]")
    known: dict[str, str] = {}

    while True:
        from agent_catalog.discovery import find_manifest_files

        manifests = find_manifest_files(root, pattern)
        changed = []
        for p in manifests:
            h = hashlib.md5(p.read_bytes()).hexdigest()
            if known.get(str(p)) != h:
                changed.append(p)
                known[str(p)] = h

        if changed:
            console.print(f"[dim]Found {len(changed)} changed manifest(s)[/]")
            _sync_impl(str(root), pattern, env, dry_run=False, get_store=_get_store, console=console)

        time.sleep(10)

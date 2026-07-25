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

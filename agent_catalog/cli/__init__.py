"""Agent Catalog CLI — declarative agent registry.

Usage:
    agent-catalog register ./agent.yaml
    agent-catalog list
    agent-catalog get agentic-inbox
    agent-catalog search --capability send_email
    agent-catalog diff agentic-inbox --right staging
"""

from __future__ import annotations

import os

import typer
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from agent_catalog import __version__
from agent_catalog.storage import CatalogStore

# ── App ────────────────────────────────────────────────────────────────────────

app = typer.Typer(
    name="agent-catalog",
    help="Declarative agent registry — catalog, discover, and diff agent capabilities.",
    no_args_is_help=True,
)

# Typer adds --install-completion and --show-completion automatically.

console = Console()


# ── Version flag ────────────────────────────────────────────────────────────────


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"agent-catalog {__version__}")
        raise typer.Exit()


@app.callback()
def _main_options(
    version: bool = typer.Option(
        False,
        "--version",
        help="Show version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    """Agent Catalog — declarative agent registry."""


# ── Shared helpers ─────────────────────────────────────────────────────────────


def _get_store() -> CatalogStore:
    """Resolve the catalog store, respecting AGENT_CATALOG_DIR env var."""
    root = os.environ.get("AGENT_CATALOG_DIR")
    return CatalogStore(root=root) if root else CatalogStore()


def _render_manifest(m) -> Panel:
    """Pretty-print an agent manifest as a Rich Panel."""
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


# ── Entry point ────────────────────────────────────────────────────────────────


def main() -> None:
    """Entry point for the 'agent-catalog' command."""
    app()


if __name__ == "__main__":
    main()

# ── Register subcommand modules ────────────────────────────────────────────────

from . import aux_commands, crud, diff_commands, discover_commands  # noqa: E402,F401

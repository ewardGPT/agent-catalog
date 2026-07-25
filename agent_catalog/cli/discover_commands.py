"""Discovery commands: sync (YAML scan), scan (Python class scan), inspect."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import typer
import yaml
from rich.console import Console

from agent_catalog.cli import _get_store, app, console
from agent_catalog.schema import AgentManifest


def _sync_impl(
    directory: str,
    pattern: str,
    env: str,
    dry_run: bool,
    get_store: Callable,
    console: Console,
) -> None:
    """Shared implementation for the sync command.

    Used by both ``sync`` and ``sync --watch``.
    """
    from agent_catalog.discovery import find_manifest_files

    root = Path(directory).resolve()
    if not root.exists():
        console.print(f"[red]\u2717[/] Directory not found: {root}")
        raise typer.Exit(1)

    manifests = find_manifest_files(root, pattern)
    if not manifests:
        console.print(f"[yellow]No files matching '{pattern}' in {root}[/]")
        return

    console.print(f"[bold]Found {len(manifests)} manifest(s):[/]")

    registered = 0
    skipped = 0

    for path in manifests:
        rel = path.relative_to(root)
        try:
            raw = yaml.safe_load(path.read_text())
            if not raw or "name" not in raw:
                console.print(f"  [yellow]\u26a0[/] {rel}: not a valid agent manifest (missing 'name')")
                skipped += 1
                continue

            manifest = AgentManifest.model_validate(raw)
            if not manifest.environment or manifest.environment == "production":
                manifest.environment = env

            if not dry_run:
                get_store().register(path)
                console.print(f"  [green]\u2713[/] {rel} \u2192 {manifest.slug} @ {manifest.environment}")
            else:
                console.print(
                    f"  [dim]would register {rel} \u2192 {manifest.slug} @ {manifest.environment}[/]"
                )
            registered += 1
        except Exception as e:
            console.print(f"  [red]\u2717[/] {rel}: {e}")
            skipped += 1

    if not dry_run:
        console.print(
            f"\n[green]\u2713[/] Registered [bold]{registered}[/] agent(s) (skipped {skipped})"
        )
    else:
        console.print(f"\n[dim]Dry run: would register {registered}, skip {skipped}[/]")


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

    _sync_impl(directory, pattern, env, dry_run, _get_store, console)
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

    from agent_catalog.decorators import build_manifest
    from agent_catalog.discovery import scan_directory

    root = Path(directory).resolve()
    if not root.exists():
        console.print(f"[red]\u2717[/] Directory not found: {root}")
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
            manifest = build_manifest(cls)
            meta = dict(manifest.metadata)
            meta["python_module"] = str(path.resolve())
            meta["python_class"] = cls.__name__
            manifest.metadata = meta
            if not dry_run:
                _get_store().register_manifest(manifest)
                console.print(
                    f"  [green]\u2713[/] {rel} \u2192 [bold]{manifest.slug}[/] @ {manifest.environment}"
                )
            else:
                console.print(
                    f"  [dim]would register {rel} \u2192 {manifest.slug} @ {manifest.environment}[/]"
                )
            registered += 1
        except Exception as e:
            console.print(f"  [red]\u2717[/] {rel}: {e}")
            skipped += 1

    if not dry_run:
        console.print(
            f"\n[green]\u2713[/] Registered [bold]{registered}[/] agent(s) (skipped {skipped})"
        )
    else:
        console.print(f"\n[dim]Dry run: would register {registered}, skip {skipped}[/]")


@app.command()
def inspect(
    path: str = typer.Argument(..., help="Path to Python file with @agent-decorated class"),
    output_format: str = typer.Option("yaml", "--format", "-f", help="Output format: yaml, json"),
):
    """Inspect a Python file and show the generated agent manifest.

    Imports the file, finds @agent classes, builds manifests, and
    displays them without registering.
    """
    import json

    from agent_catalog.decorators import build_manifest
    from agent_catalog.discovery import scan_module

    file_path = Path(path).resolve()
    if not file_path.exists():
        console.print(f"[red]\u2717[/] File not found: {file_path}")
        raise typer.Exit(1)

    classes = scan_module(file_path)
    if not classes:
        console.print(f"[yellow]No @agent-decorated classes found in {file_path}[/]")
        return

    for i, cls in enumerate(classes):
        try:
            manifest = build_manifest(cls)
            data = manifest.model_dump(mode="json", exclude_none=True)

            if output_format == "json":
                console.print_json(json.dumps(data, default=str, indent=2))
            else:
                yaml_text = yaml.dump(
                    data, sort_keys=False, default_flow_style=False, allow_unicode=True
                )
                console.print(yaml_text)

            if i < len(classes) - 1:
                console.print("---")
        except Exception as e:
            console.print(f"[red]\u2717[/] {cls.__name__}: {e}")
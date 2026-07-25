"""Diff commands: diff, export_contract."""

from __future__ import annotations

from pathlib import Path

import typer
import yaml

from agent_catalog.cli import _get_store, app, console
from agent_catalog.diff import diff_manifests
from agent_catalog.schema import AgentManifest


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
        console.print(f"[red]\u2717[/] Agent '{slug}' not registered.")
        raise typer.Exit(1) from None

    # Resolve left manifest (with optional env overlay)
    left_manifest = left
    if left_env:
        envs = left.metadata.get("environments", {})
        if left_env not in envs:
            console.print(f"[red]\u2717[/] No '{left_env}' snapshot in {slug} metadata.")
            raise typer.Exit(1)
        left_data = envs[left_env]
        left_manifest = left.model_copy(update=left_data)
        left_manifest.environment = left_env

    # Resolve right manifest
    if right:
        # External file
        right_manifest = AgentManifest.model_validate(
            yaml.safe_load(Path(right).read_text())
        )
        right_manifest.environment = right_manifest.environment or "external"
    elif slug2:
        # Cross-agent comparison
        try:
            right_manifest = _get_store().get(slug2)
        except KeyError:
            console.print(f"[red]\u2717[/] Agent '{slug2}' not registered.")
            raise typer.Exit(1) from None
        if right_env:
            envs = right_manifest.metadata.get("environments", {})
            if right_env not in envs:
                console.print(f"[red]\u2717[/] No '{right_env}' snapshot in {slug2} metadata.")
                raise typer.Exit(1)
            right_data = envs[right_env]
            right_manifest = right_manifest.model_copy(update=right_data)
            right_manifest.environment = right_env
    elif right_env:
        # Same agent, env snapshot from metadata
        envs = left.metadata.get("environments", {})
        if right_env not in envs:
            console.print(f"[red]\u2717[/] No '{right_env}' snapshot in {slug} metadata.")
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
                    "[yellow]No second manifest to diff against. "
                    "Try --right, --slug2, or --right-env.[/]"
                )
                raise typer.Exit(0)

    report = diff_manifests(left_manifest, right_manifest)
    console.print(report.summary)


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
        console.print(f"[red]\u2717[/] Agent '{slug}' not registered.")
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

    yaml_text = yaml.dump(contract_yaml, sort_keys=False, default_flow_style=False)

    if output:
        Path(output).write_text(yaml_text)
        console.print(f"[green]\u2713[/] Contract exported to [bold]{output}[/]")
    else:
        console.print(yaml_text)

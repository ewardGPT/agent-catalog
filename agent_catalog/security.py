"""Security auditor for agent manifests.

Scans catalog for: unconfirmed side effects, open MCP without auth,
dangerous capability chains, missing confirmation on write operations.
"""

from __future__ import annotations

from agent_catalog.schema import AgentManifest, SideEffect
from agent_catalog.storage import CatalogStore


class SecurityFinding:
    def __init__(self, severity: str, agent: str, title: str, detail: str) -> None:
        self.severity = severity
        self.agent = agent
        self.title = title
        self.detail = detail


def audit_catalog(store: CatalogStore) -> list[SecurityFinding]:
    """Audit all registered agents for security issues."""
    findings: list[SecurityFinding] = []

    for agent in store.list_all():
        findings.extend(_audit_agent(agent))

    return sorted(
        findings, key=lambda f: {"critical": 0, "high": 1, "medium": 2, "low": 3}[f.severity]
    )


def _audit_agent(a: AgentManifest) -> list[SecurityFinding]:
    f: list[SecurityFinding] = []

    # MCP without auth
    for iface in a.interfaces:
        if iface.type.value == "mcp" and not iface.auth_required:
            f.append(
                SecurityFinding(
                    "critical",
                    a.slug,
                    "MCP server exposed without authentication",
                    f"Interface {iface.path or '/'} is MCP with auth_required=False",
                )
            )

    # Write side effects without confirmation
    write_effects = {
        SideEffect.EMAIL_SEND,
        SideEffect.DB_WRITE,
        SideEffect.ORDER_SUBMIT,
        SideEffect.FILE_WRITE,
        SideEffect.NOTIFICATION,
        SideEffect.API_CALL,
    }
    for cap in a.capabilities:
        if not cap.requires_confirmation:
            cap_writes = set(cap.side_effects) & write_effects
            if cap_writes:
                effects = ", ".join(s.value for s in cap_writes)
                f.append(
                    SecurityFinding(
                        "high",
                        a.slug,
                        f"Write capability '{cap.id}' has no confirmation gate",
                        f"Side effects [{effects}] without requires_confirmation=True",
                    )
                )

    # Capabilities that chain dangerous operations
    for cap in a.capabilities:
        has_write = bool(set(cap.side_effects) & write_effects)
        has_injection_adjacent = any(
            "injection" in t.lower() or "prompt" in t.lower() for t in cap.tools
        )
        if has_write and has_injection_adjacent:
            f.append(
                SecurityFinding(
                    "medium",
                    a.slug,
                    f"Capability '{cap.id}' chains prompt input with write operations",
                    "Increased injection→action risk surface",
                )
            )

    # Idempotent tools that should not be
    for tool in a.tools:
        tool_writes = set(tool.side_effects) & write_effects
        if tool_writes and tool.idempotent:
            effects = ", ".join(s.value for s in tool_writes)
            f.append(
                SecurityFinding(
                    "low",
                    a.slug,
                    f"Tool '{tool.name}' marked idempotent but has write effects: {effects}",
                    "Idempotent write tools may be called repeatedly without confirmation",
                )
            )

    return f

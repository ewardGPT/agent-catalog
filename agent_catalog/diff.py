"""Diff engine for agent manifests.

Compare two manifests or two environments of the same agent.  Produces
human-readable (and machine-parseable) diff output.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from deepdiff import DeepDiff

from agent_catalog.schema import AgentManifest


@dataclass
class Change:
    """A single detected change between two manifests."""

    path: str  # dotted path, e.g. "capabilities.0.description"
    kind: str  # added | removed | changed
    old_value: str | None = None
    new_value: str | None = None


@dataclass
class DiffReport:
    """The result of diffing two agent manifests."""

    left_slug: str
    right_slug: str
    left_env: str
    right_env: str
    changes: list[Change] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return len(self.changes) > 0

    @property
    def summary(self) -> str:
        if not self.changes:
            return "No differences."
        parts = [f"{len(self.changes)} change(s) between {self.left_env} and {self.right_env}:"]
        for c in self.changes:
            parts.append(f"  [{c.kind}] {c.path}")
            if c.old_value:
                parts.append(f"       - {c.old_value}")
            if c.new_value:
                parts.append(f"       + {c.new_value}")
        return "\n".join(parts)


def diff_manifests(
    left: AgentManifest,
    right: AgentManifest,
) -> DiffReport:
    """Compute a structured diff between two agent manifests.

    Uses DeepDiff under the hood for smart structural comparison.
    """
    d_left = left.model_dump(mode="json", exclude_none=True)
    d_right = right.model_dump(mode="json", exclude_none=True)

    dd = DeepDiff(d_left, d_right, ignore_order=True, verbose_level=2)

    changes: list[Change] = []

    # New items in right (not in left)
    for path, value in dd.get("dictionary_item_added", {}).items():
        path = _clean_path(path)
        # Skip the path segment removal for root-level keys
        changes.append(Change(path=path, kind="added", new_value=_fmt(value)))

    # Items in left removed from right
    for path, value in dd.get("dictionary_item_removed", {}).items():
        path = _clean_path(path)
        changes.append(Change(path=path, kind="removed", old_value=_fmt(value)))

    # Changed values
    for path, delta in dd.get("values_changed", {}).items():
        path = _clean_path(path)
        changes.append(
            Change(
                path=path,
                kind="changed",
                old_value=_fmt(delta.get("old_value")),
                new_value=_fmt(delta.get("new_value")),
            )
        )

    # Type changes
    for path, delta in dd.get("type_changes", {}).items():
        path = _clean_path(path)
        changes.append(
            Change(
                path=path,
                kind="changed",
                old_value=_fmt(delta.get("old_value")),
                new_value=_fmt(delta.get("new_value")),
            )
        )

    # Iterable item adds/removes
    for path, value in dd.get("iterable_item_added", {}).items():
        path = _clean_path(path)
        changes.append(Change(path=path, kind="added", new_value=_fmt(value)))

    for path, value in dd.get("iterable_item_removed", {}).items():
        path = _clean_path(path)
        changes.append(Change(path=path, kind="removed", old_value=_fmt(value)))

    return DiffReport(
        left_slug=left.slug,
        right_slug=right.slug,
        left_env=left.environment,
        right_env=right.environment,
        changes=changes,
    )


def compare_environments(
    left: AgentManifest,
    right_env: str = "staging",
) -> DiffReport:
    """Convenience: compare one manifest against an environment label.

    Requires the manifest to have an `environments` metadata dict with
    per-environment overrides.  Falls back to self-comparison.
    """
    envs = left.metadata.get("environments", {})
    if right_env not in envs:
        return diff_manifests(left, left)  # no diff

    right_data = envs[right_env]
    right = left.model_copy(update=right_data)
    right.environment = right_env
    return diff_manifests(left, right)


def _clean_path(p: str) -> str:
    """Convert DeepDiff root-prefixed paths to clean dotted notation."""
    p = p.removeprefix("root['").removesuffix("']")
    p = p.replace("']['", ".")
    return p


def _fmt(value: object) -> str:
    """Format a value for human-readable diff output."""
    if value is None:
        return "<null>"
    if isinstance(value, (dict, list)):
        import json

        return json.dumps(value, default=str)
    return str(value)

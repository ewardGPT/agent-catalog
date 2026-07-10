"""Filesystem-based storage for agent manifests.

Git-ops friendly: every agent is a YAML file in a directory.  The registry
index maps agent slugs to their file paths.  No database needed — `git diff`
gives you change history for free.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import yaml

from agent_catalog.schema import AgentManifest, CatalogIndex


class CatalogStore:
    """Read/write agent manifests to a filesystem directory."""

    DEFAULT_DIR = Path.home() / ".config" / "agent-catalog" / "agents"

    def __init__(self, root: str | Path | None = None) -> None:
        import os

        if root:
            self.root = Path(root)
        elif os.environ.get("AGENT_CATALOG_DIR"):
            self.root = Path(os.environ["AGENT_CATALOG_DIR"])
        else:
            self.root = self.DEFAULT_DIR
        self.root.mkdir(parents=True, exist_ok=True)
        self._index_path = self.root / "index.yaml"

    # ── Index operations ───────────────────────────────────────────────────

    def index(self) -> CatalogIndex:
        """Load the catalog index, or return an empty one."""
        if not self._index_path.exists():
            return CatalogIndex()
        data = yaml.safe_load(self._index_path.read_text()) or {}
        return CatalogIndex(**data)

    def _save_index(self, idx: CatalogIndex) -> None:
        idx.generated_at = datetime.now(timezone.utc)
        text = yaml.dump(idx.model_dump(mode="json", exclude_none=True), sort_keys=False)
        self._index_path.write_text(text)

    # ── CRUD ───────────────────────────────────────────────────────────────

    def register(self, manifest_path: str | Path) -> AgentManifest:
        """Register a manifest from a YAML file.

        Copies the manifest into the catalog directory and indexes it.
        """
        src = Path(manifest_path).resolve()
        if not src.exists():
            raise FileNotFoundError(f"Manifest not found: {src}")

        manifest = self._parse(src)
        return self.register_manifest(manifest)

    def register_manifest(self, manifest: AgentManifest) -> AgentManifest:
        """Register an AgentManifest directly (bypasses YAML file parsing).

        Copies the manifest into the catalog directory and indexes it.
        """
        now = datetime.now(timezone.utc)
        manifest.registered_at = manifest.registered_at or now
        manifest.updated_at = now

        dest = self.root / f"{manifest.slug}.yaml"
        self._write_manifest(dest, manifest)

        idx = self.index()
        idx.agents[manifest.slug] = str(dest.relative_to(self.root))
        self._save_index(idx)

        return manifest

    def get(self, slug: str) -> AgentManifest:
        """Retrieve a single agent by slug."""
        idx = self.index()
        if slug not in idx.agents:
            raise KeyError(f"Agent '{slug}' not found in catalog. Registered: {list(idx.agents)}")

        path = self.root / idx.agents[slug]
        if not path.exists():
            raise FileNotFoundError(f"Manifest file missing for '{slug}': {path}")
        return self._parse(path)

    def list_all(self) -> list[AgentManifest]:
        """List all registered agents."""
        idx = self.index()
        result: list[AgentManifest] = []
        for relpath in idx.agents.values():
            path = self.root / relpath
            if path.exists():
                result.append(self._parse(path))
        return result

    def unregister(self, slug: str) -> bool:
        """Remove an agent from the catalog.  Returns True if it existed."""
        idx = self.index()
        if slug not in idx.agents:
            return False
        path = self.root / idx.agents.pop(slug)
        if path.exists():
            path.unlink()
        self._save_index(idx)
        return True

    def update(self, slug: str, manifest: AgentManifest) -> AgentManifest:
        """Update an existing agent manifest in place."""
        idx = self.index()
        if slug not in idx.agents:
            raise KeyError(f"Agent '{slug}' not found in catalog")
        manifest.updated_at = datetime.now(timezone.utc)
        path = self.root / idx.agents[slug]
        self._write_manifest(path, manifest)
        return manifest

    # ── Search ─────────────────────────────────────────────────────────────

    def search(
        self,
        *,
        capability: str | None = None,
        tool: str | None = None,
        surface: str | None = None,
        environment: str | None = None,
    ) -> list[AgentManifest]:
        """Search agents by capability, tool, surface, or environment.

        All filters are AND'd together.  None means "match everything."
        """
        agents = self.list_all()
        if environment:
            agents = [a for a in agents if a.environment == environment]
        if capability:
            agents = [a for a in agents if any(c.id == capability for c in a.capabilities)]
        if tool:
            agents = [a for a in agents if any(t.name == tool for t in a.tools)]
        if surface:
            agents = [a for a in agents if any(s.type.value == surface for s in a.interfaces)]
        return agents

    # ── Helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _parse(path: Path) -> AgentManifest:
        """Parse a YAML file into an AgentManifest."""
        raw = yaml.safe_load(path.read_text())
        if raw is None:
            raise ValueError(f"Empty or invalid YAML in {path}")
        return AgentManifest(**raw)

    @staticmethod
    def _write_manifest(path: Path, manifest: AgentManifest) -> None:
        """Serialize a manifest to YAML, preserving readability."""
        data = manifest.model_dump(mode="json", exclude_none=True)
        # Make the YAML readable: no anchors, explicit flow style for lists
        text = yaml.dump(data, sort_keys=False, default_flow_style=False, allow_unicode=True)
        path.write_text(text)

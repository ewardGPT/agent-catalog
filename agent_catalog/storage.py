"""Filesystem-based storage for agent manifests.

Git-ops friendly: every agent is a YAML file in a directory.  The registry
index maps agent slugs to their file paths.  No database needed — `git diff`
gives you change history for free.

Production features:
  - Atomic writes (temp file + os.replace)
  - Slug-to-filename safety (path traversal prevention)
  - Consistency check (orphaned / missing manifests)
  - Structured logging
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import yaml

from agent_catalog.schema import AgentManifest, CatalogIndex

logger = logging.getLogger("agent-catalog.storage")


class CatalogStore:
    """Read/write agent manifests to a filesystem directory."""

    DEFAULT_DIR = Path.home() / ".config" / "agent-catalog" / "agents"

    def __init__(self, root: str | Path | None = None) -> None:
        if root:
            self.root = Path(root)
        elif os.environ.get("AGENT_CATALOG_DIR"):
            self.root = Path(os.environ["AGENT_CATALOG_DIR"])
        else:
            self.root = self.DEFAULT_DIR
        self.root.mkdir(parents=True, exist_ok=True)
        self._index_path = self.root / "index.yaml"
        self._cached_index: CatalogIndex | None = None
        self._cached_index_mtime: float = -1.0
        self._cached_agents: dict[str, AgentManifest] | None = None
        """Cached {slug: AgentManifest}. Invalidated on any write.

        ``list_all()`` populates this cache on first call and returns
        cached results on subsequent calls within the same process.
        """

    # ── Index operations ───────────────────────────────────────────────────

    def index(self) -> CatalogIndex:
        """Load the catalog index, or return an empty one.

        Results are cached based on the index file's mtime.  The cache
        is invalidated on any write operation (_save_index, register,
        unregister) so repeated calls within one CLI invocation don't
        re-parse the same file.
        """
        if self._cached_index is not None:
            if self._index_path.exists():
                current_mtime = self._index_path.stat().st_mtime
                if current_mtime <= self._cached_index_mtime:
                    return self._cached_index
            else:
                return self._cached_index

        if not self._index_path.exists():
            self._cached_index = CatalogIndex()
            self._cached_index_mtime = -1.0
            return self._cached_index

        data = yaml.safe_load(self._index_path.read_text()) or {}
        self._cached_index = CatalogIndex(**data)
        self._cached_index_mtime = self._index_path.stat().st_mtime
        return self._cached_index

    def _save_index(self, idx: CatalogIndex) -> None:
        idx.generated_at = datetime.now(timezone.utc)
        text = yaml.dump(idx.model_dump(mode="json", exclude_none=True), sort_keys=False)
        self._atomic_write(self._index_path, text)
        self._invalidate_cache()

    def _invalidate_cache(self) -> None:
        """Drop the cached index and agents so the next call re-reads from disk."""
        self._cached_index = None
        self._cached_index_mtime = -1.0
        self._cached_agents = None

    # ── CRUD ───────────────────────────────────────────────────────────────

    def register(self, manifest_path: str | Path) -> AgentManifest:
        """Register a manifest from a YAML file.

        Copies the manifest into the catalog directory and indexes it.
        """
        src = Path(manifest_path).resolve()
        if not src.exists():
            raise FileNotFoundError(f"Manifest not found: {src}")

        manifest = self._parse(src)
        return self._register(manifest)

    def register_manifest(self, manifest: AgentManifest) -> AgentManifest:
        """Register an AgentManifest directly (bypasses YAML file parsing).

        Copies the manifest into the catalog directory and indexes it.
        """
        return self._register(manifest)

    def _register(self, manifest: AgentManifest) -> AgentManifest:
        """Common registration logic with atomic write + index update."""
        now = datetime.now(timezone.utc)
        manifest.registered_at = manifest.registered_at or now
        manifest.updated_at = now

        # Safe filename from slug (guards against path traversal)
        filename = self._slug_filename(manifest.slug)
        dest = self.root / filename

        # Atomic write: manifest first, then index
        self._write_manifest(dest, manifest)

        try:
            idx = self.index()
            idx.agents[manifest.slug] = filename
            self._save_index(idx)
        except Exception:
            # Rollback: remove orphaned manifest file
            if dest.exists():
                dest.unlink()
            logger.exception("Failed to save index after registering %s", manifest.slug)
            raise

        logger.info("Registered %s @ %s", manifest.slug, manifest.environment)
        return manifest

    def get(self, slug: str) -> AgentManifest:
        """Retrieve a single agent by slug."""
        # Check agent cache first
        if self._cached_agents is not None and slug in self._cached_agents:
            return self._cached_agents[slug]

        idx = self.index()
        if slug not in idx.agents:
            raise KeyError(f"Agent '{slug}' not found in catalog. Registered: {list(idx.agents)}")

        path = self.root / idx.agents[slug]
        if not path.exists():
            raise FileNotFoundError(f"Manifest file missing for '{slug}': {path}")
        return self._parse(path)

    def list_all(self) -> list[AgentManifest]:
        """List all registered agents.

        Results are cached on first call and returned from cache on
        subsequent calls.  The cache is invalidated on any write
        operation (register, unregister, update).
        """
        if self._cached_agents is not None:
            return list(self._cached_agents.values())

        idx = self.index()
        agents: dict[str, AgentManifest] = {}
        for relpath in idx.agents.values():
            path = self.root / relpath
            if path.exists():
                try:
                    a = self._parse(path)
                    agents[a.slug] = a
                except Exception:
                    logger.warning("Skipping unparseable manifest: %s", path)
        self._cached_agents = agents
        return list(agents.values())

    def unregister(self, slug: str) -> bool:
        """Remove an agent from the catalog.  Returns True if it existed."""
        idx = self.index()
        if slug not in idx.agents:
            return False
        relpath = idx.agents.pop(slug)
        path = self.root / relpath

        # Delete manifest first, then save index (reverse order of register)
        if path.exists():
            path.unlink()
        self._save_index(idx)
        logger.info("Unregistered %s", slug)
        return True

    def update(self, slug: str, manifest: AgentManifest) -> AgentManifest:
        """Update an existing agent manifest in place."""
        idx = self.index()
        if slug not in idx.agents:
            raise KeyError(f"Agent '{slug}' not found in catalog")
        manifest.updated_at = datetime.now(timezone.utc)
        path = self.root / idx.agents[slug]
        self._write_manifest(path, manifest)
        logger.info("Updated %s", slug)
        return manifest

    def register_many(self, manifests: list[AgentManifest]) -> list[AgentManifest]:
        """Register multiple agents with a single index update.

        Significantly faster than calling ``register_manifest`` in a loop
        when importing many agents at once.  Index is written once after
        all manifest files are written.
        """
        now = datetime.now(timezone.utc)
        idx = self.index()
        registered: list[AgentManifest] = []
        for m in manifests:
            m.registered_at = m.registered_at or now
            m.updated_at = now
            filename = self._slug_filename(m.slug)
            dest = self.root / filename
            self._write_manifest(dest, m)
            idx.agents[m.slug] = filename
            registered.append(m)
        self._save_index(idx)
        logger.info("Registered %d agents (batch)", len(registered))
        return registered

    # ── Consistency check ──────────────────────────────────────────────────

    def check_consistency(self) -> list[str]:
        """Check catalog consistency.

        Returns a list of human-readable issues found.  Empty list means
        the catalog is consistent (every indexed manifest exists on disk,
        no orphaned manifest files).
        """
        issues: list[str] = []
        idx = self.index()

        # Check every indexed manifest exists on disk
        for slug, relpath in idx.agents.items():
            path = self.root / relpath
            if not path.exists():
                issues.append(f"MISSING: agent '{slug}' indexed at {relpath} but file not found")

        # Check every YAML file in the catalog directory is indexed
        indexed_files = set(idx.agents.values())
        indexed_files.add("index.yaml")
        for f in self.root.iterdir():
            if f.suffix == ".yaml" and f.name not in indexed_files:
                issues.append(f"ORPHAN: file {f.name} exists but is not in the index")

        return issues

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
        text = yaml.dump(data, sort_keys=False, default_flow_style=False, allow_unicode=True)
        CatalogStore._atomic_write(path, text)

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        """Write *content* to *path* atomically.

        Writes to a temporary file on the same filesystem, then renames
        atomically via ``os.replace``.  If the process crashes mid-write
        the target file is untouched and the temp file is left behind.
        """
        tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        try:
            tmp.write_text(content)
            os.replace(str(tmp), str(path))
        finally:
            # Clean up temp file if rename failed or was interrupted
            if tmp.exists():
                tmp.unlink()

    @staticmethod
    def _slug_filename(slug: str) -> str:
        """Convert a slug to a safe filename.

        Strips any characters that could be used for path traversal,
        then appends ``.yaml``.  Raises ``ValueError`` if the result
        is empty or unsafe.
        """
        # Keep only safe filename characters
        safe = "".join(c for c in slug if c.isalnum() or c in "._-")
        if not safe or safe in (".", ".."):
            raise ValueError(f"Slug {slug!r} produces unsafe filename")
        return f"{safe}.yaml"

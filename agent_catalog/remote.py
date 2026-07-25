"""Git-based remote registry for agent-catalog.

Allows pushing and pulling agent manifests to/from a git remote.
Uses the existing AGENT_CATALOG_DIR as the working tree.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger("agent-catalog.remote")


def _get_remote() -> str | None:
    """Return the remote URL from env or config."""
    url = os.environ.get("AGENT_CATALOG_REMOTE")
    if url:
        return url
    try:
        from agent_catalog.config import get as cfg_get

        return cfg_get("remote.url")
    except Exception:
        return None


def _git(*args: str, cwd: str | Path | None = None) -> str:
    """Run a git command and return stdout."""
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=30,
    )
    if result.returncode != 0:
        combined = (result.stderr.strip() or result.stdout.strip())
        raise RuntimeError(f"git {' '.join(args)} failed: {combined}")
    return result.stdout.strip()


def publish(store_dir: str | Path | None = None, message: str | None = None) -> None:
    """Push the catalog directory to the remote git repo.

    Steps:
      1. git add .
      2. git commit (with auto-generated or provided message)
      3. git push
    """
    from agent_catalog.config import get as cfg_get

    cwd = Path(store_dir or cfg_get("catalog_dir"))
    remote = _get_remote()
    if not remote:
        print("No remote configured. Set AGENT_CATALOG_REMOTE env var or remote.url in config.", file=sys.stderr)
        raise SystemExit(1)

    # Ensure it's a git repo
    if not (cwd / ".git").exists():
        _git("init", cwd=cwd)
        # Rename default branch to main for consistency
        from contextlib import suppress
        with suppress(RuntimeError):
            _git("branch", "-M", "main", cwd=cwd)
        logger.info("Initialized git repo at %s", cwd)

    # Ensure remote is set
    try:
        existing = _git("remote", "get-url", "origin", cwd=cwd)
        if existing != remote:
            _git("remote", "set-url", "origin", remote, cwd=cwd)
    except RuntimeError:
        _git("remote", "add", "origin", remote, cwd=cwd)

    # Add, commit, push
    _git("add", "-A", cwd=cwd)
    # Set author identity for the commit (required in CI with no global git config)
    try:
        _git("config", "user.email", "agent-catalog@users.noreply.github.com", cwd=cwd)
        _git("config", "user.name", "agent-catalog", cwd=cwd)
    except RuntimeError:
        pass
    msg = message or f"agent-catalog publish: update {len(list(cwd.glob('*.yaml'))) - 1} agent(s)"
    try:
        _git("commit", "-m", msg, cwd=cwd)
    except RuntimeError as e:
        err = str(e)
        if "nothing to commit" in err or "no changes" in err:
            print("Nothing to publish — catalog is unchanged.")
            return
        raise
    _git("push", "origin", "main", cwd=cwd)
    logger.info("Published %s agent(s) to %s", len(list(cwd.glob("*.yaml"))) - 1, remote)


def pull(store_dir: str | Path | None = None) -> None:
    """Pull the latest manifests from the remote git repo."""
    from agent_catalog.config import get as cfg_get

    cwd = Path(store_dir or cfg_get("catalog_dir"))
    remote = _get_remote()
    if not remote:
        print("No remote configured. Set AGENT_CATALOG_REMOTE env var or remote.url in config.", file=sys.stderr)
        raise SystemExit(1)

    if not (cwd / ".git").exists():
        _git("init", cwd=cwd)
        _git("remote", "add", "origin", remote, cwd=cwd)

    try:
        _git("pull", "origin", "main", "--ff-only", cwd=cwd)
        print(f"Pulled latest agents from {remote}")
    except RuntimeError as e:
        print(f"Pull failed: {e}", file=sys.stderr)
        raise SystemExit(1) from e

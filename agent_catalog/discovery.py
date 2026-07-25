"""Discover decorated agent classes in Python modules and auto-register.

Scans directories for ``@agent``-decorated classes, builds manifests, and
optionally registers them with a ``CatalogStore``.

Usage:

    from agent_catalog.discovery import discover_and_register

    manifests = discover_and_register("~/projects/active")
    print(f"Registered {len(manifests)} agents")
"""

from __future__ import annotations

import fnmatch
import importlib.util
import inspect
import os
import sys
from pathlib import Path

from agent_catalog.decorators import AGENT_META_ATTR, build_manifest
from agent_catalog.schema import AgentManifest
from agent_catalog.storage import CatalogStore


def find_agent_classes(module) -> list[type]:
    """Find all ``@agent``-decorated classes in an imported module."""
    results: list[type] = []
    for _name, obj in inspect.getmembers(module, inspect.isclass):
        if hasattr(obj, AGENT_META_ATTR):
            results.append(obj)
    return results


def scan_module(module_path: str | Path) -> list[type]:
    """Import a Python file and return all ``@agent``-decorated classes.

    The module is loaded using ``importlib``.  Errors (import failures,
    missing decorator metadata) are silently skipped.
    """
    path = Path(module_path).resolve()
    if not path.exists() or path.suffix != ".py":
        return []

    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        return []

    module = importlib.util.module_from_spec(spec)
    # Temporarily add parent to sys.path so relative imports work.
    # Track whether we added it so we only remove our own entry.
    parent = str(path.parent)
    added = parent not in sys.path
    if added:
        sys.path.insert(0, parent)
    try:
        spec.loader.exec_module(module)
    except Exception:
        return []
    finally:
        if added:
            sys.path.remove(parent)

    return find_agent_classes(module)


def scan_directory(
    directory: str | Path,
    pattern: str = "**/*.py",
    exclude_prefixes: tuple[str, ...] = ("_", "test_"),
) -> list[tuple[Path, type]]:
    """Scan a directory for Python files with ``@agent``-decorated classes.

    Returns a list of ``(file_path, decorated_class)`` tuples.
    Files starting with ``_`` or ``test_`` are skipped by default.
    """
    root = Path(directory).resolve()
    results: list[tuple[Path, type]] = []

    for pyfile in sorted(root.glob(pattern)):
        # Skip __init__.py, test files, private modules
        if pyfile.name.startswith(exclude_prefixes):
            continue
        if pyfile.name == "__init__.py":
            continue

        try:
            classes = scan_module(pyfile)
            results.extend((pyfile, cls) for cls in classes)
            continue
        except Exception:
            continue

    return results


def discover_and_register(
    directory: str | Path,
    store: CatalogStore | None = None,
    pattern: str = "**/*.py",
    dry_run: bool = False,
) -> list[AgentManifest]:
    """Scan *directory* and register all ``@agent``-decorated classes.

    Stores the source file path and class name in each manifest's
    ``metadata.python_module`` and ``metadata.python_class`` fields
    so the loader can import and instantiate the class at runtime.

    Returns the list of ``AgentManifest`` objects that were (or would be)
    registered.  When *dry_run* is ``True``, manifests are built but not
    written to the store.
    """
    store = store or CatalogStore()
    found = scan_directory(directory, pattern)
    manifests: list[AgentManifest] = []

    for path, cls in found:
        try:
            manifest = build_manifest(cls)
            meta = dict(manifest.metadata)
            meta["python_module"] = str(path.resolve())
            meta["python_class"] = cls.__name__
            manifest.metadata = meta
            manifests.append(manifest)
            if not dry_run:
                store.register_manifest(manifest)
        except Exception:
            continue

    return manifests


def find_manifest_files(
    root: str | Path,
    pattern: str = "agent.yaml",
) -> list[Path]:
    """Find YAML manifest files in *root* matching *pattern*.

    Tries Python glob first (fastest), falls back to manual ``os.walk`` +
    ``fnmatch`` for environments with broken ``rglob`` (container runtimes).
    Also scans immediate subdirectories for ``agent.yaml`` explicitly.
    """
    root = Path(root).resolve()
    if not root.exists():
        return []

    results: list[Path] = []

    # Try Python glob first (works in most environments)
    try:
        py_results = list(root.glob(pattern))
        if py_results:
            return sorted(py_results)
    except Exception:
        pass

    # Fallback: manual scan with os.walk
    for dirpath, _dirnames, filenames in os.walk(str(root)):
        for f in filenames:
            if fnmatch.fnmatch(f, "agent.yaml") or fnmatch.fnmatch(f, "*.yaml"):
                full = Path(dirpath) / f
                try:
                    if fnmatch.fnmatch(str(full.relative_to(root)), pattern):
                        results.append(full)
                except ValueError:
                    continue

    # Also scan immediate subdirs explicitly for agent.yaml
    for entry in os.scandir(str(root)):
        if entry.is_dir() and not entry.name.startswith("."):
            candidate = Path(entry.path) / "agent.yaml"
            if candidate.exists() and candidate not in results:
                results.append(candidate)

    return sorted(results)

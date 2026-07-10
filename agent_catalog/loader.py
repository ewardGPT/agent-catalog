"""Runtime agent loader — import and invoke agents from the catalog.

After agents are registered (from YAML or decorators), the loader lets
you import the actual Python class and call its capabilities.

Usage:

    from agent_catalog.loader import load_agent_class, create_agent, invoke_capability

    # Get the class
    Cls = load_agent_class("my-agent")

    # Create an instance
    agent = create_agent("my-agent")

    # Invoke a capability
    result = invoke_capability("my-agent", "greet", name="World")
"""

from __future__ import annotations

import importlib.util
import inspect
import sys
from pathlib import Path
from typing import Any, Callable

from agent_catalog.storage import CatalogStore


class LoaderError(Exception):
    """Raised when agent class loading fails."""


def load_agent_class(
    slug: str,
    store: CatalogStore | None = None,
) -> type:
    """Import and return the Python class for a registered agent.

    Uses ``python_module`` and ``python_class`` from the manifest's
    ``metadata`` to locate and import the class.

    Raises ``LoaderError`` if the class cannot be found or imported.
    """
    store = store or CatalogStore()
    manifest = store.get(slug)

    module_path = manifest.metadata.get("python_module", "")
    class_name = manifest.metadata.get("python_class", "")

    if not module_path or not class_name:
        raise LoaderError(
            f"Agent '{slug}' has no python_module/python_class in metadata. "
            "Re-register with `agent-catalog scan` to store source location."
        )

    path = Path(module_path).resolve()
    if not path.exists():
        raise LoaderError(
            f"Source module not found: {path}. "
            f"The agent '{slug}' was registered from this file but it no longer exists."
        )

    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise LoaderError(f"Cannot load module from {path}")

    module = importlib.util.module_from_spec(spec)
    parent = str(path.parent)
    if parent not in sys.path:
        sys.path.insert(0, parent)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise LoaderError(f"Failed to import {path}: {exc}") from exc
    finally:
        if parent in sys.path:
            sys.path.remove(parent)

    cls = getattr(module, class_name, None)
    if cls is None or not inspect.isclass(cls):
        raise LoaderError(
            f"Class '{class_name}' not found in {path}. "
            f"The module was imported but '{class_name}' is not defined there."
        )

    return cls


def create_agent(
    slug: str,
    store: CatalogStore | None = None,
    **kwargs: Any,
) -> Any:
    """Load an agent class and create an instance.

    Extra keyword arguments are passed to the constructor.
    """
    cls = load_agent_class(slug, store=store)
    try:
        return cls(**kwargs)
    except TypeError as exc:
        raise LoaderError(
            f"Failed to instantiate '{cls.__name__}' for slug '{slug}': {exc}"
        ) from exc


def get_capability(
    slug: str,
    capability_id: str,
    store: CatalogStore | None = None,
) -> Callable:
    """Get a bound method for a specific capability.

    Returns a callable that, when invoked, executes the capability
    with the given parameters.

    Raises ``LoaderError`` if the capability or its tool is not found.
    """
    store = store or CatalogStore()
    manifest = store.get(slug)

    cap_names = {c.id for c in manifest.capabilities}
    if capability_id not in cap_names:
        raise LoaderError(
            f"Capability '{capability_id}' not found in agent '{slug}'. "
            f"Available: {sorted(cap_names)}"
        )

    agent = create_agent(slug, store=store)
    cap = next(c for c in manifest.capabilities if c.id == capability_id)

    if cap.tools:
        method_name = cap.tools[0]
    else:
        method_name = capability_id.replace("-", "_")

    method = getattr(agent, method_name, None)
    if not callable(method):
        raise LoaderError(
            f"Capability '{capability_id}' maps to method '{method_name}' "
            f"on '{type(agent).__name__}', but it is not callable."
        )

    return method


def invoke_capability(
    slug: str,
    capability_id: str,
    store: CatalogStore | None = None,
    **kwargs: Any,
) -> Any:
    """Load an agent and invoke a capability.

    Shortcut for::

        method = get_capability(slug, capability_id, store=store)
        return method(**kwargs)
    """
    method = get_capability(slug, capability_id, store=store)
    return method(**kwargs)

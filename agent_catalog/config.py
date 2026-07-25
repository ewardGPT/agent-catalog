"""Config file loader for agent-catalog.

Reads ~/.config/agent-catalog/config.yaml with defaults.
Validates the config structure on load and reports bad keys.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG = {
    "catalog_dir": str(Path.home() / ".config" / "agent-catalog" / "agents"),
    "default_environment": "production",
    "sync": {
        "patterns": ["agent.yaml"],
        "directories": [],
    },
    "security": {
        "fail_on": ["critical"],
        "ignore_agents": [],
    },
    "serve": {
        "port": 8420,
        "host": "0.0.0.0",
    },
}

# Schema for validation: expected type per dotted key
_CONFIG_SCHEMA: dict[str, type] = {
    "catalog_dir": str,
    "default_environment": str,
    "sync.patterns": list,
    "sync.directories": list,
    "security.fail_on": list,
    "security.ignore_agents": list,
    "serve.port": int,
    "serve.host": str,
}

_config: dict | None = None

_validation_warnings: list[str] | None = None


def load_config() -> dict:
    global _config, _validation_warnings
    if _config is not None:
        return _config

    config_path = Path.home() / ".config" / "agent-catalog" / "config.yaml"
    if config_path.exists():
        raw = yaml.safe_load(config_path.read_text()) or {}
        merged = _deep_merge(DEFAULT_CONFIG, raw)
    else:
        merged = dict(DEFAULT_CONFIG)

    _validation_warnings = _validate_config(merged)
    _config = merged
    return _config


def get(key: str, default=None):
    config = load_config()
    parts = key.split(".")
    val = config
    for p in parts:
        val = val.get(p, {})
        if not isinstance(val, dict) and p == parts[-1]:
            return val
    return val if val != {} else default


def _deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def _validate_config(cfg: dict) -> list[str]:
    """Check the merged config for type errors and unknown keys.

    Returns a list of warning strings (empty if everything is fine).
    """
    warnings: list[str] = []

    # Check known key types
    for dotted_key, expected_type in _CONFIG_SCHEMA.items():
        val: dict | Any = cfg
        for part in dotted_key.split("."):
            val = val.get(part) if isinstance(val, dict) else None
            if val is None:
                break
        if val is not None and not isinstance(val, expected_type):
            warnings.append(
                f"config: {dotted_key} should be {expected_type.__name__}, "
                f"got {type(val).__name__} ({val!r})"
            )

    # Check for completely unknown top-level keys
    known_top = {k.split(".")[0] for k in _CONFIG_SCHEMA}
    for k in cfg:
        if k not in known_top:
            warnings.append(f"config: unknown key '{k}'")

    return warnings


def get_validation_warnings() -> list[str]:
    """Return config validation warnings from the last load_config() call.
    Empty list means no issues.
    """
    if _validation_warnings is None:
        load_config()
    return _validation_warnings or []

"""Config file loader for agent-catalog.

Reads ~/.config/agent-catalog/config.yaml with defaults.
"""

from __future__ import annotations

from pathlib import Path

import yaml

DEFAULT_CONFIG = {
    "catalog_dir": str(Path.home() / ".config" / "agent-catalog" / "agents"),
    "default_environment": "production",
    "sync": {
        "patterns": ["agent.yaml"],
        "directories": [
            "~/projects/active",
            "~/projects/research",
            "~/projects/trading",
            "~/projects/palentir",
        ],
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

_config: dict | None = None


def load_config() -> dict:
    global _config
    if _config is not None:
        return _config

    config_path = Path.home() / ".config" / "agent-catalog" / "config.yaml"
    if config_path.exists():
        raw = yaml.safe_load(config_path.read_text()) or {}
        merged = _deep_merge(DEFAULT_CONFIG, raw)
    else:
        merged = dict(DEFAULT_CONFIG)

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

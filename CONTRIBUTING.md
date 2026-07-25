# Contributing

## Project structure

```
agent_catalog/            # Library + CLI
├── cli/                  # CLI commands (5 modules)
├── serve.py              # HTTP dashboard
├── mcp_server.py         # MCP protocol server
├── storage.py            # Filesystem store (atomic writes, index cache)
├── schema.py             # Pydantic models
├── client.py             # Python SDK (sync + async)
├── discovery.py          # File/class discovery
├── loader.py             # Runtime agent loading
├── graph.py              # Dependency graph
├── diff.py               # Manifest comparison
├── security.py           # Security auditing
├── config.py             # Config loading + validation
└── decorators.py         # @agent, @capability, @tool
tests/                    # pytest suite
```

## Setup

```bash
git clone https://github.com/ewardGPT/agent-catalog
cd agent-catalog
pip install -e ".[dev]"
```

## Running tests

```bash
pytest -q --cov
```

## Lint and type check

```bash
ruff check agent_catalog/ tests/
mypy agent_catalog/
```

## Pre-commit hooks (optional)

```bash
pip install pre-commit
pre-commit install
```

## Before submitting a PR

1. Tests pass (`pytest -q --cov`)
2. Lint clean (`ruff check agent_catalog/ tests/`)
3. Coverage doesn't drop below 60%
4. No `type: ignore` or `Any` unless absolutely necessary

## Design principles

- **Vertical slices.** One feature = one complete change, not a horizontal layer.
- **No AI slop.** README, docs, and comments say what something does, not why it's great.
- **Ponytail.** The laziest correct solution wins. Fewer lines, fewer deps, fewer abstractions.
- **No dead code.** If it's not tested, it doesn't exist. If it's not used, delete it.
- **Atomic writes.** Every write must survive a crash mid-operation. Temp file + rename.

## Release process

```bash
# bump version in pyproject.toml and agent_catalog/__init__.py
git tag vX.Y.Z
git push origin main --tags
# CI publishes to PyPI automatically
```

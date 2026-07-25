# Agent Catalog

[![CI](https://github.com/ewardGPT/agent-catalog/actions/workflows/ci.yml/badge.svg)](https://github.com/ewardGPT/agent-catalog/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/agent-catalog)](https://pypi.org/project/agent-catalog/)
[![Python](https://img.shields.io/pypi/pyversions/agent-catalog)](https://pypi.org/project/agent-catalog/)
[![License](https://img.shields.io/github/license/ewardGPT/agent-catalog)](LICENSE)

A registry for AI agents. Track every agent you own — what it does, what tools it uses, what model it runs, where it's deployed. YAML manifests stored on disk. No database. Git-ops friendly.

Think `npm` for agents. One tool to list, search, diff, and invoke them all.

```bash
pip install agent-catalog
agent-catalog register ./my-agent.yaml
agent-catalog list
```

## Why

You have agents scattered across repos, environments, and projects. Prod vs staging drift goes unnoticed. A dependency changes and nothing tells you. You grep through directories to find which agent has the capability you need.

Agent Catalog fixes that. One directory is the source of truth. Every command queries it.

## Features

- **Registry.** Register agents from YAML manifests. List, search, get details. Filter by environment, capability, tool, surface.
- **Diff.** Compare manifests across environments (`--left-env staging --right-env production`). Catch drift before it hits prod.
- **Consistency.** `agent-catalog doctor` finds orphaned files and missing manifests.
- **Security audit.** Flags MCP endpoints without auth, write capabilities without confirmation gates, idempotent tools that should not be.
- **MCP server.** Expose the catalog as MCP tools — any MCP client can discover agents and invoke their capabilities.
- **HTTP dashboard.** `agent-catalog serve` starts a web UI on `:8420`.
- **Python SDK.** `from agent_catalog.client import CatalogClient` — sync or async.
- **Decorator API.** Define agents inline with `@agent`, `@capability`, `@tool`. Manifests auto-generated from Python classes.
- **Runtime loader.** Load an agent class from the catalog and invoke a capability from the command line or API.

## Quick start

```bash
pip install agent-catalog

# Register an agent
agent-catalog register ./examples/agentic-inbox.yaml

# See everything you have
agent-catalog list

# Get details
agent-catalog get agentic-inbox

# Search
agent-catalog search --capability send_email

# Validate a manifest without registering
agent-catalog validate ./my-agent.yaml
```

## Walkthrough: managing agents across environments

```bash
# Register your staging agent
agent-catalog register ./staging/agent.yaml --env staging

# Later, register production
agent-catalog register ./prod/agent.yaml

# See the drift
agent-catalog diff agentic-inbox --left-env staging --right-env production

# Validate your changes
agent-catalog validate ./prod/agent.yaml

# Check everything is consistent
agent-catalog doctor
```

## Walkthrough: exposing agents via MCP

```bash
# Start the MCP server
agent-catalog serve --mcp

# Any MCP client can now call:
# - catalog_list_agents
# - catalog_get_agent
# - catalog_search
# - catalog_invoke
```

## Walkthrough: Python SDK

```python
from agent_catalog.client import CatalogClient

client = CatalogClient()

# List all production agents
for agent in client.agents.list(env="production"):
    print(agent.slug, agent.capability_ids())

# Async
from agent_catalog.client import AsyncCatalogClient
client = AsyncCatalogClient()
agents = await client.agents.list()
```

## Walkthrough: decorator API

```python
from agent_catalog import agent, capability, tool, build_manifest

@agent(name="My Agent", version="1.0.0", environment="production")
class MyAgent:
    @capability(id="greet", description="Greets the user")
    @tool(name="greet", description="Say hello")
    def greet(self, name: str) -> str:
        return f"Hello, {name}!"

manifest = build_manifest(MyAgent)
```

## Commands

| Command | Action |
|---------|--------|
| `register <path>` | Register agent from YAML |
| `list [--env] [--output json]` | List agents |
| `get <slug> [--output json]` | Show agent details |
| `search [--capability] [--tool] [--surface] [--env]` | Find agents |
| `diff <slug> [--right] [--slug2] [--right-env]` | Compare manifests |
| `validate <path>` | Validate YAML |
| `unregister <slug>` | Remove agent |
| `update <slug> <path>` | Update manifest |
| `sync <dir> [--pattern]` | Bulk register YAML files |
| `scan <dir>` | Discover @agent-decorated Python classes |
| `inspect <file>` | Show manifest from Python file |
| `export-contract <slug>` | Export eval contract |
| `security-audit [--format json]` | Security audit |
| `graph [--format json]` | Dependency graph |
| `serve [--port] [--mcp]` | HTTP dashboard or MCP server |
| `run <slug> <capability>` | Invoke a capability |
| `doctor` | Consistency check |

## Storage

Manifests are YAML files in `~/.config/agent-catalog/agents/`. `index.yaml` maps slugs to filenames. Set `AGENT_CATALOG_DIR` to point at a git repo — changes show up in `git diff`.

```
~/.config/agent-catalog/agents/
├── index.yaml            # slug → filename mapping
├── agentic-inbox.yaml    # agent manifests
├── nexusgate.yaml
└── trading-agent.yaml
```

## Production features

- **Atomic writes.** Every write goes to a temp file then `os.replace()` — no partial writes on crash.
- **Slug validation.** Rejects path traversal characters (/, \\, .., null).
- **Index cache.** Repeated `index()` calls within one invocation skip re-parsing.
- **Config validation.** Warns on type errors and unknown keys in config.yaml.
- **Consistency check.** `doctor` command finds orphaned files and missing manifests.
- **XSS-safe dashboard.** All agent values HTML-escaped.
- **CORS headers.** JSON API supports cross-origin requests.
- **Graceful shutdown.** SIGINT/SIGTERM signal handlers on HTTP server.
- **MCP token budget.** Tool responses hard-truncated to 1500 chars.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT

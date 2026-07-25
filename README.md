# Agent Catalog

YAML-based agent registry. Register agents, list them, diff their manifests across environments, run consistency checks. Filesystem-backed — no database, git-ops compatible.

## Install

```bash
pip install -e .
```

## Usage

### Register / List / Get

```bash
agent-catalog register ./examples/agentic-inbox.yaml
agent-catalog list
agent-catalog get agentic-inbox
```

### Search

```bash
agent-catalog search --capability send_email
agent-catalog search --tool read_inbox
agent-catalog search --surface mcp
```

### Diff

```bash
# Against a file
agent-catalog diff agentic-inbox --right ./other.yaml

# Between two registered agents
agent-catalog diff agentic-inbox --slug2 nexusgate

# Between environment snapshots
agent-catalog diff agentic-inbox --right-env staging
```

### Validate / Inspect

```bash
agent-catalog validate ./my-agent.yaml
agent-catalog inspect ./decorated_agent.py
```

### Consistency check

```bash
agent-catalog doctor
```

### Security audit

```bash
agent-catalog security-audit
agent-catalog security-audit --format json
```

### Web dashboard

```bash
agent-catalog serve
# → http://localhost:8420
```

## Commands

| Command | Action |
|---------|--------|
| `register <path>` | Register agent from YAML |
| `list [--env]` | List agents |
| `get <slug>` | Show agent details |
| `search [--capability] [--tool] [--surface] [--env]` | Find agents |
| `diff <slug> [--right] [--slug2] [--right-env]` | Compare manifests |
| `validate <path>` | Validate YAML without registering |
| `unregister <slug>` | Remove agent |
| `update <slug> <path>` | Update manifest |
| `sync <dir> [--pattern]` | Bulk register YAML files from a directory |
| `scan <dir>` | Discover @agent-decorated Python classes |
| `inspect <file>` | Show manifest generated from a Python file |
| `export-contract <slug>` | Export eval contract as YAML |
| `security-audit [--format json]` | Check agents for security issues |
| `graph [--format json]` | Show dependency graph (Mermaid or JSON) |
| `serve [--port]` | Start web dashboard |
| `run <slug> <capability>` | Invoke a capability at runtime |
| `doctor` | Check catalog consistency |

## Manifest format

```yaml
manifest_version: "1.0"
name: "My Agent"
slug: my-agent
description: "What this agent does"
version: "1.0.0"
environment: production
status: active

capabilities:
  - id: my_capability
    description: "What it can do"
    tools: [tool_name]
    surfaces: [cli, mcp]
    requires_confirmation: false
    side_effects: [email_send]
    evaluation_methods: [deterministic, outcome]
    critical: true

model:
  provider: anthropic
  name: claude-3-sonnet-20240229
  config:
    temperature: 0.7

tools:
  - name: tool_name
    description: "What the tool does"
    parameters:
      type: object
      properties:
        input: {type: string}
    side_effects: [none]
    idempotent: true

interfaces:
  - type: web
    path: /
    auth_required: true
  - type: mcp
    path: /mcp

dependencies:
  - name: postgres
    type: database
    required: true

eval_contract:
  suites: [my_project:injection, my_project:quality]
  coverage_required: 0.80
  project: my-project

prompt:
  - version: v1
    hash: a1b2c3d4
    date: "2026-01-01"
    path: prompts/v1/system.yaml
```

## Storage

Manifests are YAML files in `~/.config/agent-catalog/agents/`. `index.yaml` maps slugs to filenames. Set `AGENT_CATALOG_DIR` to use a different directory — point it at a git repo and changes show up in `git diff`.

## Python SDK

```python
from agent_catalog.client import CatalogClient

client = CatalogClient()
for agent in client.agents.list():
    print(agent.slug, agent.environment)

# Async
from agent_catalog.client import AsyncCatalogClient
client = AsyncCatalogClient()
agents = await client.agents.list()
```

## Decorator API

```python
from agent_catalog import agent, capability, tool, build_manifest

@agent(name="My Agent", version="1.0.0")
class MyAgent:
    @capability(id="greet", description="Greets the user")
    @tool(name="greet", description="Say hello")
    def greet(self, name: str) -> str:
        return f"Hello, {name}!"

manifest = build_manifest(MyAgent)
```

## Examples

See `examples/agentic-inbox.yaml`, `examples/nexusgate.yaml`, `examples/trading-agent.yaml`.

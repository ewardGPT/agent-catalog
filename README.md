# Agent Catalog

Declarative agent registry — catalog, discover, and diff agent capabilities across environments. Git-ops friendly. No database required.

## Quick Start

```bash
pip install -e .

# Register an agent from a manifest file
agent-catalog register ./examples/agentic-inbox.yaml

# List everything
agent-catalog list
agent-catalog list --env production

# Get full details
agent-catalog get agentic-inbox

# Search by capability, tool, or surface
agent-catalog search --capability send_email
agent-catalog search --tool read_inbox
agent-catalog search --surface mcp

# Diff staging vs production
agent-catalog diff agentic-inbox --right examples/agentic-inbox-staging.yaml

# Validate a manifest without registering
agent-catalog validate ./my-agent.yaml
```

## CLI Reference

| Command | Description |
|---|---|
| `register <path>` | Register agent from YAML manifest |
| `list [--env X]` | List all agents, optionally filtered |
| `get <slug>` | Show full agent details |
| `search [--capability X] [--tool X] [--surface X]` | Find agents by attribute |
| `diff <slug> [--right <path>] [--right-env X]` | Compare two manifests |
| `validate <path>` | Validate manifest without registering |
| `update <slug> <path>` | Update existing agent |
| `unregister <slug> [--force]` | Remove from catalog |

## Manifest Format

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
    description: "Primary data store"

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

Manifests stored as YAML files in `~/.config/agent-catalog/agents/`. Set `AGENT_CATALOG_DIR` to override. The `index.yaml` maps slugs to files.

Git-ops: point `AGENT_CATALOG_DIR` at a git repo to track every change via `git diff`.

## Example

See `examples/agentic-inbox.yaml` for a complete production manifest.

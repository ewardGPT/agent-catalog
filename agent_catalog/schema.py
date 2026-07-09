"""Core Pydantic schema for agent manifests.

An AgentManifest is the single source of truth for what an agent is, what it
can do, what tools it uses, what model it runs, and how it integrates.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field, field_validator

# ── Enums ──────────────────────────────────────────────────────────────────────


class Surface(str, Enum):
    """External interface surface for agent interaction."""

    CLI = "cli"
    MCP = "mcp"
    USER = "user"
    WEBSOCKET = "websocket"
    API = "api"
    SDK = "sdk"
    WEB = "web"


class SideEffect(str, Enum):
    """Classify what an agent capability can change in the outside world."""

    EMAIL_SEND = "email_send"
    DB_WRITE = "db_write"
    DB_READ = "db_read"
    API_CALL = "api_call"
    FILE_WRITE = "file_write"
    FILE_READ = "file_read"
    ORDER_SUBMIT = "order_submit"
    NOTIFICATION = "notification"
    SEARCH = "search"
    NONE = "none"


class EvaluationMethod(str, Enum):
    """How a capability is evaluated."""

    DETERMINISTIC = "deterministic"
    OUTCOME = "outcome"
    TRAJECTORY = "trajectory"
    LLM_JUDGE = "llm_judge"
    SCHEMA = "schema"
    SAFETY = "safety"
    OPERATIONAL = "operational"


# ── Nested Models ──────────────────────────────────────────────────────────────


class Interface(BaseModel):
    """An external surface the agent exposes."""

    type: Surface
    path: str | None = None
    port: int | None = None
    auth_required: bool = True


class ModelReference(BaseModel):
    """The model configuration an agent runs against."""

    provider: str
    name: str
    config: dict = Field(default_factory=dict)

    @field_validator("provider", mode="before")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return v.strip()


class ToolDeclaration(BaseModel):
    """A tool the agent can invoke."""

    name: str
    description: str = ""
    parameters: dict = Field(default_factory=dict, description="JSON Schema for tool parameters")
    side_effects: list[SideEffect] = Field(default_factory=list)
    idempotent: bool = False


class Capability(BaseModel):
    """A declared capability of the agent — what it can do."""

    id: str
    description: str
    tools: list[str] = Field(default_factory=list)
    surfaces: list[Surface] = Field(default_factory=list)
    requires_confirmation: bool = False
    side_effects: list[SideEffect] = Field(default_factory=list)
    evaluation_methods: list[EvaluationMethod] = Field(
        default_factory=lambda: [EvaluationMethod.DETERMINISTIC]
    )
    critical: bool = False


class PromptRef(BaseModel):
    """Pointer to a prompt version."""

    version: str
    hash: str = ""
    date: datetime | None = None
    path: str | None = None


class EvalContract(BaseModel):
    """Eval harness integration contract."""

    suites: list[str] = Field(default_factory=list)
    coverage_required: float = 0.80
    project: str = ""


class Dependency(BaseModel):
    """A dependency on another agent or service."""

    name: str
    type: str = "agent"  # agent | service | database | api
    required: bool = True
    description: str = ""


# ── Root Manifest ──────────────────────────────────────────────────────────────


class AgentManifest(BaseModel):
    """The complete agent registry entry.

    This is the canonical declaration of an agent in the catalog.  Every
    agent in the system must have a valid manifest to be registered.

    The schema is intentionally flat — nested at most two levels — to keep
    YAML readable, diffs clean, and validation fast.
    """

    # Identity
    manifest_version: str = "1.0"
    name: str
    slug: str = ""
    description: str = ""
    version: str = "0.0.0"

    # Lifecycle
    environment: str = "production"
    status: str = "active"  # active | deprecated | retired | experimental

    # Capabilities
    capabilities: list[Capability] = Field(default_factory=list)
    model: ModelReference | None = None
    prompt: list[PromptRef] = Field(default_factory=list)

    # Tool declarations (what the agent can invoke)
    tools: list[ToolDeclaration] = Field(default_factory=list)

    # Interfaces
    interfaces: list[Interface] = Field(default_factory=list)

    # Relationships
    dependencies: list[Dependency] = Field(default_factory=list)
    dependents: list[str] = Field(
        default_factory=list, description="Other agents that depend on this one"
    )

    # Evaluation
    eval_contract: EvalContract | None = None

    # Arbitrary metadata for project-specific fields
    metadata: dict = Field(default_factory=dict)

    # Timestamps (populated by registry, not user)
    registered_at: datetime | None = None
    updated_at: datetime | None = None

    def model_post_init(self, __context) -> None:
        """Derive slug from name if not provided."""
        if not self.slug:
            self.slug = self.name.lower().replace(" ", "-").replace("_", "-")

    @field_validator("version")
    @classmethod
    def validate_semver(cls, v: str) -> str:
        parts = v.split(".")
        if len(parts) not in (1, 2, 3):
            raise ValueError(f"Version must be semver-like, got: {v}")
        for p in parts:
            if not p.isdigit():
                raise ValueError(f"Version components must be numeric, got: {v}")
        return v

    def capability_ids(self) -> list[str]:
        return [c.id for c in self.capabilities]

    def tool_names(self) -> list[str]:
        return [t.name for t in self.tools]

    def environment_tag(self) -> str:
        """Return the full env-qualified slug."""
        return f"{self.slug}@{self.environment}"


# ── Catalog Index ──────────────────────────────────────────────────────────────


class CatalogIndex(BaseModel):
    """The registry index — maps agent slugs to their file paths."""

    version: str = "1.0"
    agents: dict[str, str] = Field(
        default_factory=dict,
        description="slug → relative path to manifest YAML",
    )
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

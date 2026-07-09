"""Comprehensive schema tests — 150+ cases via parametrize."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent_catalog.schema import (
    AgentManifest,
    Capability,
    CatalogIndex,
    Dependency,
    EvalContract,
    EvaluationMethod,
    Interface,
    ModelReference,
    PromptRef,
    SideEffect,
    Surface,
    ToolDeclaration,
)

# ═══════════════════════════════════════════════════════════════════════════════
# AgentManifest — slug derivation
# ═══════════════════════════════════════════════════════════════════════════════

SLUG_CASES = [
    ("My Agent Name", "my-agent-name"),
    ("A", "a"),
    ("with_underscores", "with-underscores"),
    ("Mix OF_cAsEs", "mix-of-cases"),
    ("  spaces  ", "--spaces--"),
    ("multi   space", "multi---space"),
    ("trailing-dash-", "trailing-dash-"),
    ("", ""),
    ("123", "123"),
    ("UPPERCASE", "uppercase"),
    ("snake_case_name", "snake-case-name"),
    ("kebab-already", "kebab-already"),
    ("double--dash", "double--dash"),
    ("leading space", "leading-space"),
    ("unicode-ä-char", "unicode-ä-char"),
    ("a" * 50, "a" * 50),
    ("1.0.0-release", "1.0.0-release"),
    ("agent/service", "agent/service"),
    ("@special", "@special"),
    ("test!", "test!"),
]


@pytest.mark.parametrize("name,expected_slug", SLUG_CASES)
def test_slug_derivation(name: str, expected_slug: str) -> None:
    m = AgentManifest(name=name, description="test")
    assert m.slug == expected_slug


@pytest.mark.parametrize("explicit_slug", ["custom-slug", "a", "x" * 100, "foo.bar_baz"])
def test_explicit_slug_wins(explicit_slug: str) -> None:
    m = AgentManifest(name="Original Name", slug=explicit_slug, description="test")
    assert m.slug == explicit_slug


# ═══════════════════════════════════════════════════════════════════════════════
# AgentManifest — version validation
# ═══════════════════════════════════════════════════════════════════════════════

VALID_VERSIONS = [
    "0",
    "1",
    "0.0",
    "1.0",
    "0.0.0",
    "1.0.0",
    "2.1.0",
    "99.99.99",
    "0.0.1",
    "10",
    "100.200.300",
]

INVALID_VERSIONS = [
    "v1",
    "1.0.0-beta",
    "alpha",
    "1.0.0.0",
    "",
    "1.0.0-rc1",
    "latest",
    "1.0.0+build",
    "a.b.c",
    "1,0,0",
]


@pytest.mark.parametrize("ver", VALID_VERSIONS)
def test_valid_version(ver: str) -> None:
    m = AgentManifest(name="A", description="B", version=ver)
    assert m.version == ver


@pytest.mark.parametrize("ver", INVALID_VERSIONS)
def test_invalid_version_raises(ver: str) -> None:
    with pytest.raises(ValidationError):
        AgentManifest(name="A", description="B", version=ver)


# ═══════════════════════════════════════════════════════════════════════════════
# AgentManifest — environment tag
# ═══════════════════════════════════════════════════════════════════════════════

ENV_TAG_CASES = [
    ("test", "production", "test@production"),
    ("my-agent", "staging", "my-agent@staging"),
    ("simple", "dev", "simple@dev"),
    ("a", "b", "a@b"),
    ("agent-with-dashes", "research", "agent-with-dashes@research"),
]


@pytest.mark.parametrize("slug,env,expected", ENV_TAG_CASES)
def test_environment_tag(slug: str, env: str, expected: str) -> None:
    m = AgentManifest(name="X", description="Y", slug=slug, environment=env)
    assert m.environment_tag() == expected


# ═══════════════════════════════════════════════════════════════════════════════
# AgentManifest — capability_ids / tool_names
# ═══════════════════════════════════════════════════════════════════════════════


def test_capability_ids_many() -> None:
    caps = [Capability(id=f"c{i}", description=f"D{i}") for i in range(20)]
    m = AgentManifest(name="X", description="Y", capabilities=caps)
    assert m.capability_ids() == [f"c{i}" for i in range(20)]


def test_tool_names_many() -> None:
    tools = [ToolDeclaration(name=f"tool_{i}", description=f"T{i}") for i in range(15)]
    m = AgentManifest(name="X", description="Y", tools=tools)
    assert m.tool_names() == [f"tool_{i}" for i in range(15)]


# ═══════════════════════════════════════════════════════════════════════════════
# Capability
# ═══════════════════════════════════════════════════════════════════════════════

CAPABILITY_VALID = [
    ({"id": "a", "description": "A"}, "a", [], False, False),
    (
        {
            "id": "send",
            "description": "Send stuff",
            "tools": ["t1", "t2"],
            "surfaces": [Surface.USER, Surface.MCP],
            "requires_confirmation": True,
            "side_effects": [SideEffect.EMAIL_SEND],
            "evaluation_methods": [EvaluationMethod.DETERMINISTIC, EvaluationMethod.SAFETY],
            "critical": True,
        },
        "send",
        ["t1", "t2"],
        True,
        True,
    ),
    ({"id": "read", "description": "Read"}, "read", [], False, False),
    (
        {
            "id": "write",
            "description": "Write",
            "side_effects": [SideEffect.DB_WRITE, SideEffect.FILE_WRITE],
        },
        "write",
        [],
        False,
        False,
    ),
    (
        {
            "id": "search",
            "description": "Search",
            "surfaces": [Surface.CLI, Surface.API, Surface.WEB],
            "evaluation_methods": [EvaluationMethod.OUTCOME, EvaluationMethod.TRAJECTORY],
        },
        "search",
        [],
        False,
        False,
    ),
]


@pytest.mark.parametrize("data,exp_id,exp_tools,exp_confirm,exp_critical", CAPABILITY_VALID)
def test_capability_variants(data, exp_id, exp_tools, exp_confirm, exp_critical) -> None:
    c = Capability(**data)
    assert c.id == exp_id
    assert c.tools == exp_tools
    assert c.requires_confirmation == exp_confirm
    assert c.critical == exp_critical


# ═══════════════════════════════════════════════════════════════════════════════
# Interface
# ═══════════════════════════════════════════════════════════════════════════════

INTERFACE_CASES = [
    (Surface.CLI, None, None, True),
    (Surface.WEB, "/", 443, True),
    (Surface.MCP, "/mcp", None, True),
    (Surface.API, "http://localhost:8000", 8000, True),
    (Surface.WEBSOCKET, "/ws", None, False),
    (Surface.SDK, None, None, False),
    (Surface.USER, None, None, True),
]


@pytest.mark.parametrize("typ,path,port,auth", INTERFACE_CASES)
def test_interface_variants(typ, path, port, auth) -> None:
    kwargs = {"type": typ, "auth_required": auth}
    if path is not None:
        kwargs["path"] = path
    if port is not None:
        kwargs["port"] = port
    i = Interface(**kwargs)
    assert i.type == typ
    assert i.auth_required == auth


# ═══════════════════════════════════════════════════════════════════════════════
# ModelReference — provider strip
# ═══════════════════════════════════════════════════════════════════════════════

MODEL_PROVIDER_CASES = [
    ("openai", "openai"),
    (" openai  ", "openai"),
    ("  anthropic", "anthropic"),
    ("cloudflare ", "cloudflare"),
    ("aws", "aws"),
    (" open ai ", "open ai"),  # inner spaces preserved
    ("\tanthropic\t", "anthropic"),
    ("  a  ", "a"),
]


@pytest.mark.parametrize("raw,stripped", MODEL_PROVIDER_CASES)
def test_model_provider_stripped(raw: str, stripped: str) -> None:
    m = ModelReference(provider=raw, name="gpt-4")
    assert m.provider == stripped


MODEL_CONFIG_CASES = [
    {},
    {"temperature": 0.7},
    {"max_tokens": 4096},
    {"temperature": 0.0, "max_tokens": 1},
    {"temperature": 1.0, "max_tokens": 128000, "top_p": 0.9, "stop": ["</s>"]},
]


@pytest.mark.parametrize("config", MODEL_CONFIG_CASES)
def test_model_config_variants(config: dict) -> None:
    m = ModelReference(provider="test", name="test-model", config=config)
    assert m.config == config


# ═══════════════════════════════════════════════════════════════════════════════
# ToolDeclaration
# ═══════════════════════════════════════════════════════════════════════════════

TOOL_SIDE_EFFECT_CASES = [
    ([], True),
    ([SideEffect.NONE], True),
    ([SideEffect.DB_READ], True),
    ([SideEffect.EMAIL_SEND], False),
    ([SideEffect.ORDER_SUBMIT], False),
    ([SideEffect.FILE_WRITE], False),
    ([SideEffect.API_CALL], False),
    ([SideEffect.DB_READ, SideEffect.SEARCH], True),  # read-only = idempotent
    ([SideEffect.DB_WRITE, SideEffect.EMAIL_SEND], False),
]


@pytest.mark.parametrize("side_effects,idempotent", TOOL_SIDE_EFFECT_CASES)
def test_tool_side_effects(side_effects, idempotent: bool) -> None:
    t = ToolDeclaration(
        name="test_tool",
        description="test",
        side_effects=side_effects,
        idempotent=idempotent,
    )
    assert t.side_effects == side_effects
    assert t.idempotent == idempotent


TOOL_PARAMETER_CASES = [
    {"type": "object", "properties": {}},
    {"type": "object", "properties": {"x": {"type": "string"}}},
    {
        "type": "object",
        "properties": {
            "a": {"type": "string"},
            "b": {"type": "integer"},
            "c": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["a"],
    },
]


@pytest.mark.parametrize("params", TOOL_PARAMETER_CASES)
def test_tool_parameters(params: dict) -> None:
    t = ToolDeclaration(name="t", description="d", parameters=params)
    assert t.parameters == params


# ═══════════════════════════════════════════════════════════════════════════════
# PromptRef
# ═══════════════════════════════════════════════════════════════════════════════

PROMPT_REF_CASES = [
    ({"version": "v1"}, "v1", "", None, None),
    ({"version": "v2", "hash": "abc"}, "v2", "abc", None, None),
    (
        {"version": "v3", "hash": "def456", "path": "prompts/v3.yaml"},
        "v3",
        "def456",
        None,
        "prompts/v3.yaml",
    ),
    (
        {"version": "v4", "hash": "", "date": "2026-01-01T00:00:00"},
        "v4",
        "",
        "2026-01-01T00:00:00",
        None,
    ),
]


@pytest.mark.parametrize("data,exp_ver,exp_hash,exp_date,exp_path", PROMPT_REF_CASES)
def test_prompt_ref_variants(data, exp_ver, exp_hash, exp_date, exp_path) -> None:
    p = PromptRef(**data)
    assert p.version == exp_ver
    assert p.hash == exp_hash
    if exp_date:
        assert p.date.isoformat().startswith(exp_date[:10])
    assert p.path == exp_path


# ═══════════════════════════════════════════════════════════════════════════════
# EvalContract
# ═══════════════════════════════════════════════════════════════════════════════

EVAL_CONTRACT_CASES = [
    (EvalContract(), [], 0.80, ""),
    (EvalContract(suites=["a:b", "c:d"]), ["a:b", "c:d"], 0.80, ""),
    (EvalContract(coverage_required=0.95), [], 0.95, ""),
    (EvalContract(project="my-proj"), [], 0.80, "my-proj"),
    (EvalContract(suites=["x"], coverage_required=0.50, project="p"), ["x"], 0.50, "p"),
]


@pytest.mark.parametrize("c,exp_suites,exp_cov,exp_proj", EVAL_CONTRACT_CASES)
def test_eval_contract(c, exp_suites, exp_cov, exp_proj) -> None:
    assert c.suites == exp_suites
    assert c.coverage_required == exp_cov
    assert c.project == exp_proj


# ═══════════════════════════════════════════════════════════════════════════════
# Dependency
# ═══════════════════════════════════════════════════════════════════════════════

DEPENDENCY_CASES = [
    ({"name": "pg", "type": "database", "required": True, "description": "db"}, True),
    ({"name": "redis", "type": "service", "required": False, "description": "cache"}, False),
    ({"name": "other-agent", "type": "agent", "required": True, "description": "dep"}, True),
]


@pytest.mark.parametrize("data,exp_req", DEPENDENCY_CASES)
def test_dependency_variants(data, exp_req) -> None:
    d = Dependency(**data)
    assert d.required == exp_req


# ═══════════════════════════════════════════════════════════════════════════════
# CatalogIndex
# ═══════════════════════════════════════════════════════════════════════════════


def test_catalog_index_default() -> None:
    ci = CatalogIndex()
    assert ci.version == "1.0"
    assert ci.agents == {}


def test_catalog_index_with_agents() -> None:
    ci = CatalogIndex(agents={"a": "a.yaml", "b": "sub/b.yaml"})
    assert "a" in ci.agents
    assert "b" in ci.agents
    assert ci.agents["b"] == "sub/b.yaml"


# ═══════════════════════════════════════════════════════════════════════════════
# Surface enum
# ═══════════════════════════════════════════════════════════════════════════════

SURFACE_VALUES = [
    ("cli", Surface.CLI),
    ("mcp", Surface.MCP),
    ("user", Surface.USER),
    ("websocket", Surface.WEBSOCKET),
    ("api", Surface.API),
    ("sdk", Surface.SDK),
    ("web", Surface.WEB),
]


@pytest.mark.parametrize("raw,expected", SURFACE_VALUES)
def test_surface_from_string(raw: str, expected: Surface) -> None:
    assert Surface(raw) == expected


# ═══════════════════════════════════════════════════════════════════════════════
# SideEffect enum
# ═══════════════════════════════════════════════════════════════════════════════

SIDE_EFFECT_VALUES = [
    ("email_send", SideEffect.EMAIL_SEND),
    ("db_write", SideEffect.DB_WRITE),
    ("db_read", SideEffect.DB_READ),
    ("api_call", SideEffect.API_CALL),
    ("file_write", SideEffect.FILE_WRITE),
    ("file_read", SideEffect.FILE_READ),
    ("order_submit", SideEffect.ORDER_SUBMIT),
    ("notification", SideEffect.NOTIFICATION),
    ("search", SideEffect.SEARCH),
    ("none", SideEffect.NONE),
]


@pytest.mark.parametrize("raw,expected", SIDE_EFFECT_VALUES)
def test_side_effect_from_string(raw: str, expected: SideEffect) -> None:
    assert SideEffect(raw) == expected


# ═══════════════════════════════════════════════════════════════════════════════
# EvaluationMethod enum
# ═══════════════════════════════════════════════════════════════════════════════

EVAL_METHOD_VALUES = [
    ("deterministic", EvaluationMethod.DETERMINISTIC),
    ("outcome", EvaluationMethod.OUTCOME),
    ("trajectory", EvaluationMethod.TRAJECTORY),
    ("llm_judge", EvaluationMethod.LLM_JUDGE),
    ("schema", EvaluationMethod.SCHEMA),
    ("safety", EvaluationMethod.SAFETY),
    ("operational", EvaluationMethod.OPERATIONAL),
]


@pytest.mark.parametrize("raw,expected", EVAL_METHOD_VALUES)
def test_eval_method_from_string(raw: str, expected: EvaluationMethod) -> None:
    assert EvaluationMethod(raw) == expected


# ═══════════════════════════════════════════════════════════════════════════════
# Edge cases
# ═══════════════════════════════════════════════════════════════════════════════


def test_manifest_max_capabilities() -> None:
    caps = [Capability(id=f"c{i}", description=f"D{i}") for i in range(100)]
    m = AgentManifest(name="X", description="Y", capabilities=caps)
    assert len(m.capabilities) == 100
    assert len(m.capability_ids()) == 100


def test_manifest_max_tools() -> None:
    tools = [ToolDeclaration(name=f"t{i}", description=f"T{i}") for i in range(50)]
    m = AgentManifest(name="X", description="Y", tools=tools)
    assert len(m.tools) == 50


def test_manifest_empty_defaults() -> None:
    m = AgentManifest(name="Min", description="Minimal")
    assert m.capabilities == []
    assert m.tools == []
    assert m.interfaces == []
    assert m.dependencies == []
    assert m.prompt == []
    assert m.model is None
    assert m.eval_contract is None
    assert m.metadata == {}
    assert m.environment == "production"
    assert m.status == "active"


def test_manifest_all_status_values() -> None:
    for s in ["active", "deprecated", "retired", "experimental"]:
        m = AgentManifest(name="X", description="Y", status=s)
        assert m.status == s


def test_manifest_with_dependents() -> None:
    m = AgentManifest(name="Base", description="X", dependents=["agent-a", "agent-b"])
    assert m.dependents == ["agent-a", "agent-b"]


def test_manifest_metadata_arbitrary() -> None:
    m = AgentManifest(
        name="X",
        description="Y",
        metadata={
            "team": "infra",
            "sla": "99.9",
            "custom": {"nested": True, "count": 42},
        },
    )
    assert m.metadata["team"] == "infra"
    assert m.metadata["custom"]["nested"] is True

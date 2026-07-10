"""Decorator-based agent declaration API.

Declare agents inline in Python code — manifests auto-generated
from decorated classes.  No YAML drift, no separate files.

Usage:

    @agent(name="My Agent", version="1.0.0", environment="production")
    class MyAgent:
        @capability(id="greet", description="Greets the user")
        @tool(name="greet", description="Say hello to someone")
        def greet(self, name: str, greeting: str = "Hello") -> str:
            return f"{greeting}, {name}!"

    manifest = build_manifest(MyAgent)
    manifest.model_dump(mode="json")  # → AgentManifest with auto-derived schema
"""

from __future__ import annotations

import inspect
import typing
from collections.abc import Callable
from types import UnionType
from typing import Any, get_type_hints

from agent_catalog.schema import (
    AgentManifest,
    Capability,
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

# ── Constants ────────────────────────────────────────────────────────────

_MISSING: Any = object()

AGENT_META_ATTR = "__agent_meta__"
CAPABILITY_META_ATTR = "__capability_meta__"
TOOL_META_ATTR = "__tool_meta__"
INTERFACE_META_ATTR = "__interface_meta__"
DEPENDENCY_META_ATTR = "__dependency_meta__"
PROMPT_META_ATTR = "__prompt_meta__"

# Python type → JSON Schema type map
_TYPE_MAP: dict[type, dict] = {
    str: {"type": "string"},
    int: {"type": "integer"},
    float: {"type": "number"},
    bool: {"type": "boolean"},
    type(None): {"type": "null"},
}


# ── Schema derivation helpers ────────────────────────────────────────────


def _resolve_type_hints(func: Callable) -> dict[str, type]:
    """Safely resolve type hints, returning {} on failure."""
    try:
        return get_type_hints(func)
    except (NameError, AttributeError, TypeError):
        return {}


def _pytype_to_json_schema(tp: type, default: Any = _MISSING) -> dict:
    """Derive a JSON Schema property from a Python type hint."""
    origin = typing.get_origin(tp)
    args = typing.get_args(tp)

    # Optional[X] = Union[X, None]  (both typing.Union and types.UnionType)
    if origin is typing.Union or origin is UnionType:
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            schema = _pytype_to_json_schema(non_none[0])
            _maybe_add_default(schema, default)
            return schema

    # list[X]
    if origin is list:
        item_tp = args[0] if args else str
        schema = {"type": "array", "items": _pytype_to_json_schema(item_tp)}
        _maybe_add_default(schema, default)
        return schema

    # dict[K, V]
    if origin is dict:
        schema = {"type": "object"}
        _maybe_add_default(schema, default)
        return schema

    # Literal["a", "b"]
    if origin is typing.Literal:
        return {"type": "string", "enum": list(args)}

    # Basic types
    if tp in _TYPE_MAP:
        schema = dict(_TYPE_MAP[tp])
        _maybe_add_default(schema, default)
        return schema

    # Fallback: string with type name as description
    return {"type": "string", "description": str(tp)}


def _maybe_add_default(schema: dict, default: Any) -> None:
    """Add default to schema if one was provided."""
    if default is not _MISSING:
        schema["default"] = default


def _build_parameters_schema(func: Callable) -> dict:
    """Build JSON Schema for tool parameters from function signature.

    Derives types, required-ness, and defaults from Python annotations.
    """
    sig = inspect.signature(func)
    hints = _resolve_type_hints(func)

    properties: dict[str, dict] = {}
    required: list[str] = []

    for name, param in sig.parameters.items():
        if name in ("self", "cls"):
            continue

        tp = hints.get(name, str)
        has_default = param.default is not inspect.Parameter.empty
        default = param.default if has_default else _MISSING

        prop = _pytype_to_json_schema(tp, default)
        properties[name] = prop

        if not has_default:
            required.append(name)

    schema: dict[str, Any] = {"type": "object"}
    if properties:
        schema["properties"] = properties
    if required:
        schema["required"] = required
    return schema


# ── Coercion helpers ─────────────────────────────────────────────────────


def _coerce_enum(val: Any, enum_cls: type) -> Any:
    """Convert string to enum member if needed."""
    if isinstance(val, enum_cls):
        return val
    if isinstance(val, str):
        return enum_cls(val)
    return val


def _coerce_surface(val: str | Surface) -> Surface:
    return _coerce_enum(val, Surface)  # type: ignore[return-value]


def _coerce_side_effect(val: str | SideEffect) -> SideEffect:
    return _coerce_enum(val, SideEffect)  # type: ignore[return-value]


def _coerce_eval_method(val: str | EvaluationMethod) -> EvaluationMethod:
    return _coerce_enum(val, EvaluationMethod)  # type: ignore[return-value]


def _coerce_list(vals: list, coerce_fn: Callable) -> list:
    return [coerce_fn(v) for v in vals]


# ── Meta-collection helpers ──────────────────────────────────────────────


def _attach_meta(cls_or_func: Any, attr: str, item: dict) -> None:
    """Append a metadata dict to a class or function's list attribute."""
    existing = getattr(cls_or_func, attr, [])
    existing.append(item)
    setattr(cls_or_func, attr, existing)


# ── @agent ───────────────────────────────────────────────────────────────


class agent:
    """Declare a class as an agent.

    The class can contain ``@capability`` and ``@tool`` decorated methods.
    Call ``build_manifest(cls)`` to generate an ``AgentManifest``.
    """

    def __init__(
        self,
        *,
        name: str | None = None,
        slug: str | None = None,
        version: str = "0.1.0",
        description: str = "",
        environment: str = "production",
        status: str = "active",
        model: ModelReference | dict | None = None,
        eval_contract: EvalContract | dict | None = None,
        metadata: dict | None = None,
        manifest_version: str = "1.0",
    ) -> None:
        self._name = name
        self._slug = slug
        self._version = version
        self._description = description
        self._environment = environment
        self._status = status
        self._model = model
        self._eval_contract = eval_contract
        self._metadata = metadata or {}
        self._manifest_version = manifest_version

    def __call__(self, cls: type) -> type:
        existing = getattr(cls, AGENT_META_ATTR, {})
        existing.update(
            name=self._name or cls.__name__,
            slug=self._slug,
            version=self._version,
            description=self._description or (cls.__doc__ or "").strip(),
            environment=self._environment,
            status=self._status,
            model=self._model,
            eval_contract=self._eval_contract,
            metadata=self._metadata,
            manifest_version=self._manifest_version,
        )
        setattr(cls, AGENT_META_ATTR, existing)
        return cls


# ── @capability ──────────────────────────────────────────────────────────


class capability:
    """Mark a method as an agent capability."""

    def __init__(
        self,
        *,
        id: str,
        description: str = "",
        surfaces: list[str | Surface] | None = None,
        requires_confirmation: bool = False,
        side_effects: list[str | SideEffect] | None = None,
        evaluation_methods: list[str | EvaluationMethod] | None = None,
        critical: bool = False,
    ) -> None:
        self._id = id
        self._description = description
        self._surfaces = surfaces or []
        self._requires_confirmation = requires_confirmation
        self._side_effects = side_effects or []
        self._evaluation_methods = evaluation_methods or []
        self._critical = critical

    def __call__(self, func: Callable) -> Callable:
        _attach_meta(
            func,
            CAPABILITY_META_ATTR,
            {
                "id": self._id,
                "description": self._description,
                "surfaces": self._surfaces,
                "requires_confirmation": self._requires_confirmation,
                "side_effects": self._side_effects,
                "evaluation_methods": self._evaluation_methods,
                "critical": self._critical,
            },
        )
        return func


# ── @tool ────────────────────────────────────────────────────────────────


class tool:
    """Mark a method as an agent tool.

    Parameter schema is auto-derived from the function's type hints
    unless explicitly provided via *parameters_schema*.

    Implemented as a callable class so the name ``tool`` is always
    resolvable by LOAD_NAME inside class bodies (avoids Python 3.13+
    closure edge cases with function-based factories).
    """

    def __init__(
        self,
        *,
        name: str | None = None,
        description: str = "",
        side_effects: list[str | SideEffect] | None = None,
        idempotent: bool = False,
        parameters_schema: dict | None = None,
    ) -> None:
        self._name = name
        self._description = description
        self._side_effects = side_effects or []
        self._idempotent = idempotent
        self._parameters_schema = parameters_schema

    def __call__(self, func: Callable) -> Callable:
        _attach_meta(
            func,
            TOOL_META_ATTR,
            {
                "name": self._name or func.__name__,
                "description": self._description or (func.__doc__ or "").strip(),
                "side_effects": self._side_effects,
                "idempotent": self._idempotent,
                "parameters_schema": self._parameters_schema,
            },
        )
        return func


# ── @interface ───────────────────────────────────────────────────────────


class interface:
    """Add an interface to an agent class."""

    def __init__(
        self,
        *,
        type: str | Surface,
        path: str | None = None,
        port: int | None = None,
        auth_required: bool = True,
    ) -> None:
        self._type = _coerce_surface(type) if isinstance(type, str) else type
        self._path = path
        self._port = port
        self._auth_required = auth_required

    def __call__(self, cls: type) -> type:
        _attach_meta(
            cls,
            INTERFACE_META_ATTR,
            {
                "type": self._type,
                "path": self._path,
                "port": self._port,
                "auth_required": self._auth_required,
            },
        )
        return cls


# ── @dependency ──────────────────────────────────────────────────────────


class dependency:
    """Add a dependency to an agent class."""

    def __init__(
        self,
        *,
        name: str,
        type: str = "agent",
        required: bool = True,
        description: str = "",
    ) -> None:
        self._name = name
        self._type = type
        self._required = required
        self._description = description

    def __call__(self, cls: type) -> type:
        _attach_meta(
            cls,
            DEPENDENCY_META_ATTR,
            {
                "name": self._name,
                "type": self._type,
                "required": self._required,
                "description": self._description,
            },
        )
        return cls


# ── @prompt_ref ──────────────────────────────────────────────────────────


class prompt_ref:
    """Add a prompt reference to an agent class.

    Can be stacked to declare multiple prompt versions.
    """

    def __init__(
        self,
        *,
        version: str,
        hash: str = "",
        date: str | None = None,
        path: str | None = None,
    ) -> None:
        self._version = version
        self._hash = hash
        self._date = date
        self._path = path

    def __call__(self, cls: type) -> type:
        from datetime import datetime

        parsed_date: datetime | None = None
        if self._date:
            try:
                parsed_date = datetime.fromisoformat(self._date)
            except (ValueError, TypeError):
                parsed_date = None

        _attach_meta(
            cls,
            PROMPT_META_ATTR,
            {
                "version": self._version,
                "hash": self._hash,
                "date": parsed_date,
                "path": self._path,
            },
        )
        return cls


# ── Manifest builder ─────────────────────────────────────────────────────


def _get_members(cls: type) -> list[tuple[str, Callable]]:
    """Walk a class hierarchy collecting methods with their metadata attrs.

    Handles regular methods, classmethods, and staticmethods.
    """
    members: list[tuple[str, Callable]] = []
    for attr_name in dir(cls):
        raw = getattr(cls, attr_name, None)
        if not callable(raw):
            continue
        # Unwrap descriptors to get the underlying function
        func = raw
        if isinstance(raw, (classmethod, staticmethod)):
            func = raw.__func__
        if not callable(func):
            continue
        members.append((attr_name, func))
    return members


def build_manifest(cls: type) -> AgentManifest:
    """Build an ``AgentManifest`` from a decorated agent class.

    Raises ``TypeError`` if the class is not decorated with ``@agent``.
    """
    meta = getattr(cls, AGENT_META_ATTR, None)
    if meta is None:
        raise TypeError(
            f"{cls.__name__} is not decorated with @agent — "
            "add @agent(...) above the class definition"
        )

    capabilities_list: list[Capability] = []
    tools_list: list[ToolDeclaration] = []

    for _attr_name, func in _get_members(cls):
        cap_meta_list = getattr(func, CAPABILITY_META_ATTR, [])
        tool_meta_list = getattr(func, TOOL_META_ATTR, [])

        # Collect tool declarations
        current_tool_names: list[str] = []
        for tm in tool_meta_list:
            params = tm["parameters_schema"] or _build_parameters_schema(func)
            declaration = ToolDeclaration(
                name=tm["name"],
                description=tm["description"],
                parameters=params,
                side_effects=_coerce_list(tm["side_effects"], _coerce_side_effect),
                idempotent=tm["idempotent"],
            )
            tools_list.append(declaration)
            current_tool_names.append(tm["name"])

        # Collect capability declarations
        for cm in cap_meta_list:
            # Capability auto-links to tools on the same method only
            cap_tools = (
                list(current_tool_names)
                if not tool_meta_list
                else [t["name"] for t in tool_meta_list]
            )
            capability_obj = Capability(
                id=cm["id"],
                description=cm["description"],
                tools=cap_tools,
                surfaces=_coerce_list(cm["surfaces"], _coerce_surface),
                requires_confirmation=cm["requires_confirmation"],
                side_effects=_coerce_list(cm["side_effects"], _coerce_side_effect),
                evaluation_methods=_coerce_list(cm["evaluation_methods"], _coerce_eval_method),
                critical=cm["critical"],
            )
            capabilities_list.append(capability_obj)

    # Build class-level lists
    interfaces_list = [Interface(**i) for i in getattr(cls, INTERFACE_META_ATTR, [])]
    deps_list = [Dependency(**d) for d in getattr(cls, DEPENDENCY_META_ATTR, [])]
    prompts_list = [PromptRef(**p) for p in getattr(cls, PROMPT_META_ATTR, [])]

    # Coerce model
    model_ref: ModelReference | None = None
    if meta.get("model"):
        m = meta["model"]
        model_ref = ModelReference(**m) if isinstance(m, dict) else m

    # Coerce eval contract
    eval_contract: EvalContract | None = None
    if meta.get("eval_contract"):
        ec = meta["eval_contract"]
        eval_contract = EvalContract(**ec) if isinstance(ec, dict) else ec

    return AgentManifest(
        manifest_version=meta.get("manifest_version", "1.0"),
        name=meta["name"],
        slug=meta.get("slug") or "",
        description=meta.get("description", ""),
        version=meta.get("version", "0.1.0"),
        environment=meta.get("environment", "production"),
        status=meta.get("status", "active"),
        capabilities=capabilities_list,
        model=model_ref,
        prompt=prompts_list,
        tools=tools_list,
        interfaces=interfaces_list,
        dependencies=deps_list,
        eval_contract=eval_contract,
        metadata=meta.get("metadata", {}),
    )

"""Tests for the decorator-based agent declaration API."""

from __future__ import annotations

from agent_catalog import agent, build_manifest, capability, dependency, interface, tool
from agent_catalog.schema import (
    AgentManifest,
    SideEffect,
    Surface,
)

# ── Minimal agent ────────────────────────────────────────────────────────


class TestMinimalAgent:
    def test_bare_agent(self):
        @agent()
        class SilentAgent:
            pass

        m = build_manifest(SilentAgent)
        assert isinstance(m, AgentManifest)
        assert m.name == "SilentAgent"
        assert m.slug == "silentagent"
        assert m.version == "0.1.0"
        assert m.environment == "production"
        assert m.capabilities == []
        assert m.tools == []

    def test_name_override(self):
        @agent(name="My Agent")
        class Foo:
            pass

        m = build_manifest(Foo)
        assert m.name == "My Agent"

    def test_custom_slug(self):
        @agent(name="Test Agent", slug="custom-slug")
        class Foo:
            pass

        m = build_manifest(Foo)
        assert m.slug == "custom-slug"

    def test_version(self):
        @agent(name="V", version="2.0.0")
        class Foo:
            pass

        m = build_manifest(Foo)
        assert m.version == "2.0.0"

    def test_environment(self):
        @agent(name="E", environment="staging")
        class Foo:
            pass

        m = build_manifest(Foo)
        assert m.environment == "staging"

    def test_description_from_docstring(self):
        @agent(name="DocTest")
        class Foo:
            """This agent does something useful."""

        m = build_manifest(Foo)
        assert m.description == "This agent does something useful."

    def test_not_decorated_raises(self):
        class PlainClass:
            pass

        import pytest

        with pytest.raises(TypeError, match="not decorated with @agent"):
            build_manifest(PlainClass)


# ── Capability + tool ────────────────────────────────────────────────────


class TestCapabilityAndTool:
    def test_capability_with_tool(self):
        @agent(name="Greeter")
        class GreeterAgent:
            @capability(id="greet", description="Greets the user")
            @tool(name="greet", description="Say hello")
            def greet(self, name: str) -> str:
                """Greet someone."""
                return f"Hello, {name}!"

        m = build_manifest(GreeterAgent)
        assert len(m.capabilities) == 1
        assert m.capabilities[0].id == "greet"
        assert m.capabilities[0].description == "Greets the user"
        # Capability auto-links to tool on same method
        assert m.capabilities[0].tools == ["greet"]

        assert len(m.tools) == 1
        assert m.tools[0].name == "greet"
        assert m.tools[0].description == "Say hello"

    def test_multiple_capabilities(self):
        @agent(name="Multi")
        class MultiAgent:
            @capability(id="read", description="Read data")
            @tool(name="read_data")
            def read(self, query: str) -> list:
                return []

            @capability(id="write", description="Write data", requires_confirmation=True)
            @tool(name="write_data", idempotent=False)
            def write(self, data: dict) -> bool:
                return True

        m = build_manifest(MultiAgent)
        assert len(m.capabilities) == 2
        assert len(m.tools) == 2
        assert {c.id for c in m.capabilities} == {"read", "write"}
        assert {t.name for t in m.tools} == {"read_data", "write_data"}

    def test_capability_with_multiple_tools(self):
        @agent(name="MultiTool")
        class MultiToolAgent:
            @capability(id="manage", description="Manage things")
            @tool(name="create")
            @tool(name="delete")
            def manage(self, action: str) -> str:
                return action

        m = build_manifest(MultiToolAgent)
        assert len(m.capabilities) == 1
        # Capability references both tools
        assert sorted(m.capabilities[0].tools) == ["create", "delete"]
        assert len(m.tools) == 2

    def test_capability_side_effects(self):
        @agent(name="Mailer")
        class MailerAgent:
            @capability(
                id="send_email",
                description="Send emails",
                requires_confirmation=True,
                side_effects=[SideEffect.EMAIL_SEND],
                surfaces=[Surface.USER, Surface.MCP],
                critical=True,
            )
            @tool(name="send_email", side_effects=["email_send"])
            def send(self, to: str, subject: str) -> bool:
                return True

        m = build_manifest(MailerAgent)
        cap = m.capabilities[0]
        assert cap.requires_confirmation is True
        assert SideEffect.EMAIL_SEND in cap.side_effects
        assert Surface.USER in cap.surfaces
        assert Surface.MCP in cap.surfaces
        assert cap.critical is True


# ── Parameter schema auto-derivation ─────────────────────────────────────


class TestParameterSchema:
    def test_required_params(self):
        @agent(name="P")
        class ParamAgent:
            @capability(id="greet")
            @tool(name="greet")
            def greet(self, name: str, age: int) -> str:
                return f"{name} is {age}"

        m = build_manifest(ParamAgent)
        decl = m.tools[0]
        assert decl.parameters["type"] == "object"
        assert "properties" in decl.parameters
        assert "name" in decl.parameters["properties"]
        assert "age" in decl.parameters["properties"]
        assert decl.parameters["properties"]["name"]["type"] == "string"
        assert decl.parameters["properties"]["age"]["type"] == "integer"
        assert "name" in decl.parameters["required"]
        assert "age" in decl.parameters["required"]

    def test_optional_params(self):
        @agent(name="O")
        class OptAgent:
            @capability(id="greet")
            @tool(name="greet")
            def greet(self, name: str, greeting: str = "Hello") -> str:
                return f"{greeting} {name}"

        m = build_manifest(OptAgent)
        decl = m.tools[0]
        props = decl.parameters["properties"]
        assert props["greeting"]["default"] == "Hello"
        assert "greeting" not in decl.parameters.get("required", [])
        assert "name" in decl.parameters.get("required", [])

    def test_optional_type(self):
        @agent(name="Opt")
        class OptAgent:
            @capability(id="find")
            @tool(name="find")
            def find(self, query: str, limit: int | None = None) -> list:
                return []

        m = build_manifest(OptAgent)
        props = m.tools[0].parameters["properties"]
        # Optional[X] should resolve to X's type
        assert props["limit"]["type"] == "integer"
        assert "default" in props["limit"]

    def test_list_param(self):
        @agent(name="L")
        class ListAgent:
            @capability(id="batch")
            @tool(name="batch")
            def batch(self, items: list[str]) -> int:
                return len(items)

        m = build_manifest(ListAgent)
        props = m.tools[0].parameters["properties"]["items"]
        assert props["type"] == "array"
        assert props["items"]["type"] == "string"

    def test_explicit_schema_overrides(self):
        @agent(name="E")
        class ExplicitAgent:
            @capability(id="custom")
            @tool(
                name="custom",
                parameters_schema={"type": "object", "properties": {"x": {"type": "number"}}},
            )
            def custom(self, x: float) -> float:
                return x * 2

        m = build_manifest(ExplicitAgent)
        assert m.tools[0].parameters == {
            "type": "object",
            "properties": {"x": {"type": "number"}},
        }


# ── Interface decoration ─────────────────────────────────────────────────


class TestInterface:
    def test_interface_decorator(self):
        @agent(name="I")
        @interface(type="mcp", path="/mcp", auth_required=True)
        @interface(type="web", path="/", auth_required=False)
        class WebAgent:
            pass

        m = build_manifest(WebAgent)
        assert len(m.interfaces) == 2
        types = {i.type.value for i in m.interfaces}
        assert types == {"mcp", "web"}

    def test_interface_coercion(self):
        @agent(name="I2")
        @interface(type=Surface.CLI, auth_required=False)
        class CliAgent:
            pass

        m = build_manifest(CliAgent)
        assert m.interfaces[0].type == Surface.CLI


# ── Dependency decoration ────────────────────────────────────────────────


class TestDependency:
    def test_dependency_decorator(self):
        @agent(name="D")
        @dependency(name="postgres", type="database", required=True)
        @dependency(name="redis", type="cache", required=False)
        class DataAgent:
            pass

        m = build_manifest(DataAgent)
        assert len(m.dependencies) == 2
        names = {d.name for d in m.dependencies}
        assert names == {"postgres", "redis"}

    def test_dependency_with_description(self):
        @agent(name="D2")
        @dependency(name="auth-service", type="api", description="User authentication")
        class AuthAgent:
            pass

        m = build_manifest(AuthAgent)
        assert m.dependencies[0].description == "User authentication"


# ── Model reference ──────────────────────────────────────────────────────


class TestModel:
    def test_model_as_dict(self):
        @agent(
            name="M",
            model={"provider": "anthropic", "name": "claude-sonnet-4-20250514"},
        )
        class ModelAgent:
            pass

        m = build_manifest(ModelAgent)
        assert m.model is not None
        assert m.model.provider == "anthropic"
        assert m.model.name == "claude-sonnet-4-20250514"

    def test_eval_contract(self):
        from agent_catalog.schema import EvalContract

        @agent(
            name="EvalAgent",
            eval_contract=EvalContract(
                suites=["test:smoke", "test:quality"],
                coverage_required=0.85,
                project="evaltest",
            ),
        )
        class EvalAgent:
            pass

        m = build_manifest(EvalAgent)
        assert m.eval_contract is not None
        assert m.eval_contract.suites == ["test:smoke", "test:quality"]
        assert m.eval_contract.coverage_required == 0.85


# ── Full integration ─────────────────────────────────────────────────────


class TestFullIntegration:
    def test_complex_agent(self):
        @agent(
            name="Inbox Agent",
            version="2.1.0",
            environment="production",
            model={"provider": "cloudflare", "name": "@cf/moonshotai/kimi-k2.5"},
            metadata={"repository": "https://github.com/example/inbox", "team": "inbox"},
        )
        @interface(type="web", path="/", auth_required=True)
        @interface(type="mcp", path="/mcp", auth_required=True)
        @dependency(name="postgres", type="database", required=True)
        class InboxAgent:
            """Self-hosted email agent."""

            @capability(
                id="read_inbox",
                description="Read and search emails",
                critical=True,
            )
            @tool(name="read_inbox", description="Read emails from mailbox", idempotent=True)
            def read_inbox(self, mailbox_id: str, limit: int = 20) -> list:
                return []

            @capability(
                id="send_email",
                description="Compose and send emails",
                requires_confirmation=True,
                side_effects=[SideEffect.EMAIL_SEND],
                critical=True,
            )
            @tool(name="send_email", description="Send an email")
            def send_email(self, to: str, subject: str, body: str) -> bool:
                return True

        m = build_manifest(InboxAgent)
        assert m.name == "Inbox Agent"
        assert m.slug == "inbox-agent"
        assert m.version == "2.1.0"
        assert m.environment == "production"
        assert m.model is not None
        assert m.model.provider == "cloudflare"
        assert len(m.capabilities) == 2
        assert len(m.tools) == 2
        assert len(m.interfaces) == 2
        assert len(m.dependencies) == 1
        assert m.metadata["team"] == "inbox"

        # Check auto-derived schema
        read = next(t for t in m.tools if t.name == "read_inbox")
        props = read.parameters.get("properties", {})
        assert "mailbox_id" in props
        assert props["mailbox_id"]["type"] == "string"
        assert props["limit"]["type"] == "integer"
        assert props["limit"]["default"] == 20

    def test_class_still_usable(self):
        """Decorated class should still work as a normal Python class."""

        @agent(name="Usable")
        class UsableAgent:
            @capability(id="double")
            @tool(name="double")
            def double(self, x: int) -> int:
                return x * 2

        instance = UsableAgent()
        assert instance.double(21) == 42

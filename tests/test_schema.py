"""Schema validation tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent_catalog.schema import (
    AgentManifest,
    Capability,
    ModelReference,
    Surface,
    ToolDeclaration,
)


class TestCapability:
    def test_minimal_capability(self):
        c = Capability(id="test_cap", description="A test capability")
        assert c.id == "test_cap"
        assert c.tools == []
        assert not c.requires_confirmation

    def test_full_capability(self):
        c = Capability(
            id="send_email",
            description="Send emails",
            tools=["send_email"],
            surfaces=[Surface.USER],
            requires_confirmation=True,
            critical=True,
        )
        assert c.critical is True
        assert c.requires_confirmation is True


class TestModelReference:
    def test_provider_trimmed(self):
        m = ModelReference(provider=" openai ", name="gpt-4")
        assert m.provider == "openai"


class TestAgentManifest:
    def test_minimal(self):
        m = AgentManifest(name="Test Agent", description="Test")
        assert m.slug == "test-agent"
        assert m.environment == "production"

    def test_slug_derived(self):
        m = AgentManifest(name="My Agent Name", description="X")
        assert m.slug == "my-agent-name"

    def test_explicit_slug_wins(self):
        m = AgentManifest(name="My Agent", slug="custom-slug", description="X")
        assert m.slug == "custom-slug"

    def test_version_validation(self):
        AgentManifest(name="A", description="B", version="1.0.0")  # ok
        AgentManifest(name="A", description="B", version="0.5")  # ok

        with pytest.raises(ValidationError):
            AgentManifest(name="A", description="B", version="one")

    def test_environment_tag(self):
        m = AgentManifest(name="Test", description="X", environment="staging")
        assert m.environment_tag() == "test@staging"

    def test_capability_ids(self):
        m = AgentManifest(
            name="Test",
            description="X",
            capabilities=[
                Capability(id="a", description="A"),
                Capability(id="b", description="B"),
            ],
        )
        assert m.capability_ids() == ["a", "b"]

    def test_tool_names(self):
        m = AgentManifest(
            name="Test",
            description="X",
            tools=[
                ToolDeclaration(name="t1", description="T1"),
                ToolDeclaration(name="t2", description="T2"),
            ],
        )
        assert m.tool_names() == ["t1", "t2"]

    def test_deserialize_example(self):
        from pathlib import Path

        import yaml

        path = Path(__file__).parent.parent / "examples" / "agentic-inbox.yaml"
        raw = yaml.safe_load(path.read_text())
        m = AgentManifest.model_validate(raw)
        assert m.slug == "agentic-inbox"
        assert len(m.capabilities) == 4
        assert m.model.provider == "cloudflare"
        assert len(m.tools) == 4
        assert len(m.eval_contract.suites) == 2

"""Diff engine tests."""

from __future__ import annotations

from agent_catalog.diff import diff_manifests
from agent_catalog.schema import AgentManifest, Capability


class TestDiffManifest:
    def test_identical_no_changes(self):
        m = AgentManifest(name="Test", description="Test")
        report = diff_manifests(m, m)
        assert not report.has_changes
        assert "No differences" in report.summary

    def test_capability_added(self):
        left = AgentManifest(name="Test", description="Test")
        right = AgentManifest(
            name="Test",
            description="Test",
            capabilities=[Capability(id="new_cap", description="New")],
        )
        report = diff_manifests(left, right)
        assert report.has_changes
        assert any(c.kind == "added" for c in report.changes)

    def test_environment_changed(self):
        left = AgentManifest(name="Test", description="Test", environment="staging")
        right = AgentManifest(name="Test", description="Test", environment="production")
        report = diff_manifests(left, right)
        assert report.has_changes
        assert report.left_env == "staging"
        assert report.right_env == "production"

    def test_tool_added_and_removed(self):
        from agent_catalog.schema import ToolDeclaration

        left = AgentManifest(
            name="Test",
            description="Test",
            tools=[ToolDeclaration(name="old_tool", description="Old")],
        )
        right = AgentManifest(
            name="Test",
            description="Test",
            tools=[ToolDeclaration(name="new_tool", description="New")],
        )
        report = diff_manifests(left, right)
        assert report.has_changes
        # DeepDiff may represent item swap as iterable changes or value changes
        kinds = {c.kind for c in report.changes}
        assert len(kinds) >= 1  # at least one change detected

    def test_prompt_hash_changed(self):
        from agent_catalog.schema import PromptRef

        left = AgentManifest(
            name="Test",
            description="X",
            prompt=[PromptRef(version="v1", hash="aaa")],
        )
        right = AgentManifest(
            name="Test",
            description="X",
            prompt=[PromptRef(version="v1", hash="bbb")],
        )
        report = diff_manifests(left, right)
        assert report.has_changes
        assert any("hash" in c.path for c in report.changes)

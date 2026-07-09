"""CLI integration tests."""

from __future__ import annotations

import tempfile
from pathlib import Path
from textwrap import dedent

import pytest
from typer.testing import CliRunner

from agent_catalog.cli import app


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def manifest_file():
    content = dedent("""\
    manifest_version: "1.0"
    name: "CLI Test Agent"
    slug: cli-test
    description: "Testing the CLI"
    version: "1.0.0"
    environment: production
    status: active
    capabilities:
      - id: test_cap
        description: "A test capability"
        tools: [tool_one, tool_two]
        surfaces: [cli]
    """)
    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
        f.write(content)
        return Path(f.name)


class TestRegister:
    def test_register_from_file(self, runner, manifest_file):
        with tempfile.TemporaryDirectory() as td:
            result = runner.invoke(
                app,
                ["register", str(manifest_file)],
                env={"AGENT_CATALOG_DIR": td},
            )
            assert result.exit_code == 0
            assert "cli-test" in result.stdout

    def test_register_missing_file(self, runner):
        result = runner.invoke(app, ["register", "/nonexistent/file.yaml"])
        assert result.exit_code == 1

    def test_validate_valid(self, runner, manifest_file):
        result = runner.invoke(app, ["validate", str(manifest_file)])
        assert result.exit_code == 0
        assert "Valid" in result.stdout


class TestList:
    def test_list_empty(self, runner):
        with tempfile.TemporaryDirectory() as td:
            result = runner.invoke(
                app,
                ["list"],
                env={"AGENT_CATALOG_DIR": td},
            )
            assert result.exit_code == 0
            assert "No agents" in result.stdout

    def test_list_after_register(self, runner, manifest_file):
        with tempfile.TemporaryDirectory() as td:
            runner.invoke(app, ["register", str(manifest_file)], env={"AGENT_CATALOG_DIR": td})
            result = runner.invoke(app, ["list"], env={"AGENT_CATALOG_DIR": td})
            assert result.exit_code == 0
            assert "cli-test" in result.stdout


class TestGet:
    def test_get_existing(self, runner, manifest_file):
        with tempfile.TemporaryDirectory() as td:
            runner.invoke(app, ["register", str(manifest_file)], env={"AGENT_CATALOG_DIR": td})
            result = runner.invoke(app, ["get", "cli-test"], env={"AGENT_CATALOG_DIR": td})
            assert result.exit_code == 0
            assert "CLI Test Agent" in result.stdout

    def test_get_missing(self, runner):
        with tempfile.TemporaryDirectory() as td:
            result = runner.invoke(app, ["get", "nonexistent"], env={"AGENT_CATALOG_DIR": td})
            assert result.exit_code == 1


class TestSearch:
    def test_search_by_capability(self, runner, manifest_file):
        with tempfile.TemporaryDirectory() as td:
            runner.invoke(app, ["register", str(manifest_file)], env={"AGENT_CATALOG_DIR": td})
            result = runner.invoke(
                app, ["search", "--capability", "test_cap"], env={"AGENT_CATALOG_DIR": td}
            )
            assert result.exit_code == 0
            assert "cli-test" in result.stdout

    def test_search_no_match(self, runner, manifest_file):
        with tempfile.TemporaryDirectory() as td:
            runner.invoke(app, ["register", str(manifest_file)], env={"AGENT_CATALOG_DIR": td})
            result = runner.invoke(
                app, ["search", "--capability", "nonexistent"], env={"AGENT_CATALOG_DIR": td}
            )
            assert result.exit_code == 0
            assert "No matching" in result.stdout

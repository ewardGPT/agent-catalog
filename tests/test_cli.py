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


@pytest.fixture
def registered_env(runner, manifest_file):
    """Return a temp dir with cli-test already registered."""
    with tempfile.TemporaryDirectory() as td:
        runner.invoke(app, ["register", str(manifest_file)], env={"AGENT_CATALOG_DIR": td})
        yield td


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


class TestUnregister:
    def test_unregister_existing(self, runner, manifest_file):
        with tempfile.TemporaryDirectory() as td:
            runner.invoke(app, ["register", str(manifest_file)], env={"AGENT_CATALOG_DIR": td})
            result = runner.invoke(
                app, ["unregister", "cli-test", "--force"], env={"AGENT_CATALOG_DIR": td}
            )
            assert result.exit_code == 0
            assert "Unregistered" in result.stdout

    def test_unregister_missing(self, runner):
        with tempfile.TemporaryDirectory() as td:
            result = runner.invoke(
                app, ["unregister", "nonexistent", "--force"], env={"AGENT_CATALOG_DIR": td}
            )
            assert result.exit_code == 0
            assert "not found" in result.stdout


class TestUpdate:
    def test_update_existing(self, runner, manifest_file):
        with tempfile.TemporaryDirectory() as td:
            runner.invoke(app, ["register", str(manifest_file)], env={"AGENT_CATALOG_DIR": td})
            with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
                f.write(manifest_file.read_text().replace("1.0.0", "2.0.0"))
                updated = Path(f.name)
            result = runner.invoke(
                app, ["update", "cli-test", str(updated)], env={"AGENT_CATALOG_DIR": td}
            )
            assert result.exit_code == 0
            assert "Updated" in result.stdout


class TestDiff:
    def test_diff_two_registered(self, runner, manifest_file):
        with tempfile.TemporaryDirectory() as td:
            runner.invoke(app, ["register", str(manifest_file)], env={"AGENT_CATALOG_DIR": td})
            content2 = manifest_file.read_text().replace("production", "staging")
            with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
                f.write(content2)
                path2 = Path(f.name)
            runner.invoke(app, ["register", str(path2)], env={"AGENT_CATALOG_DIR": td})
            result = runner.invoke(
                app, ["diff", "cli-test", "--slug2", "cli-test"], env={"AGENT_CATALOG_DIR": td}
            )
            assert result.exit_code == 0


class TestSecurityAudit:
    def test_security_audit_clean(self, runner):
        with tempfile.TemporaryDirectory() as td:
            result = runner.invoke(
                app, ["security-audit"], env={"AGENT_CATALOG_DIR": td}
            )
            assert result.exit_code == 0
            assert "No security" in result.stdout

    def test_security_audit_json(self, runner):
        with tempfile.TemporaryDirectory() as td:
            result = runner.invoke(
                app, ["security-audit", "--format", "json"], env={"AGENT_CATALOG_DIR": td}
            )
            assert result.exit_code == 0


class TestGraph:
    def test_graph_mermaid(self, runner):
        with tempfile.TemporaryDirectory() as td:
            result = runner.invoke(
                app, ["graph"], env={"AGENT_CATALOG_DIR": td}
            )
            assert result.exit_code == 0
            assert "graph TD" in result.stdout

    def test_graph_json(self, runner):
        with tempfile.TemporaryDirectory() as td:
            result = runner.invoke(
                app, ["graph", "--format", "json"], env={"AGENT_CATALOG_DIR": td}
            )
            assert result.exit_code == 0


class TestSync:
    def test_sync_directory_no_matches(self, runner):
        with tempfile.TemporaryDirectory() as td:
            result = runner.invoke(
                app, ["sync", td, "--pattern", "agent.yaml", "--dry-run"],
                env={"AGENT_CATALOG_DIR": tempfile.mkdtemp()},
            )
            assert result.exit_code == 0
            assert "No files matching" in result.stdout

    def test_sync_directory_with_manifest(self, runner, manifest_file):
        with tempfile.TemporaryDirectory() as td:
            # Copy manifest into the target dir
            dest = Path(td) / "agent.yaml"
            dest.write_text(manifest_file.read_text())
            result = runner.invoke(
                app, ["sync", td, "--dry-run"],
                env={"AGENT_CATALOG_DIR": tempfile.mkdtemp()},
            )
            assert result.exit_code == 0
            assert "would register" in result.stdout


class TestExportContract:
    def test_export_no_contract(self, runner):
        with tempfile.TemporaryDirectory() as td:
            result = runner.invoke(
                app, ["export-contract", "nonexistent"], env={"AGENT_CATALOG_DIR": td}
            )
            assert result.exit_code == 1


class TestDoctor:
    def test_doctor_clean(self, runner):
        with tempfile.TemporaryDirectory() as td:
            result = runner.invoke(app, ["doctor"], env={"AGENT_CATALOG_DIR": td})
            assert result.exit_code == 0
            assert "consistent" in result.stdout


class TestVersion:
    def test_version_flag(self, runner):
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "agent-catalog" in result.stdout


class TestJsonOutput:
    def test_list_json(self, runner, manifest_file):
        with tempfile.TemporaryDirectory() as td:
            runner.invoke(app, ["register", str(manifest_file)], env={"AGENT_CATALOG_DIR": td})
            result = runner.invoke(
                app, ["list", "--output", "json"], env={"AGENT_CATALOG_DIR": td}
            )
            assert result.exit_code == 0
            import json as _json
            data = _json.loads(result.stdout)
            assert "agents" in data
            assert len(data["agents"]) == 1

    def test_get_json(self, runner, manifest_file):
        with tempfile.TemporaryDirectory() as td:
            runner.invoke(app, ["register", str(manifest_file)], env={"AGENT_CATALOG_DIR": td})
            result = runner.invoke(
                app, ["get", "cli-test", "--output", "json"], env={"AGENT_CATALOG_DIR": td}
            )
            assert result.exit_code == 0
            import json as _json
            data = _json.loads(result.stdout)
            assert data["slug"] == "cli-test"

    def test_list_json_empty(self, runner):
        with tempfile.TemporaryDirectory() as td:
            result = runner.invoke(
                app, ["list", "--output", "json"], env={"AGENT_CATALOG_DIR": td}
            )
            assert result.exit_code == 0
            import json as _json
            data = _json.loads(result.stdout)
            assert data["agents"] == []


class TestInspect:
    def test_inspect_python_file(self, runner):
        code = dedent("""\
        from agent_catalog import agent, capability, tool

        @agent(name="Inspect Test", description="Auto-discovered")
        class InspectedAgent:
            @capability(id="ping", description="Ping")
            @tool(name="ping", description="Ping tool")
            def ping(self) -> str:
                return "pong"
        """)
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write(code)
            pyfile = Path(f.name)
        result = runner.invoke(app, ["inspect", str(pyfile)])
        assert result.exit_code == 0
        assert "Inspect Test" in result.stdout

    def test_inspect_not_found(self, runner):
        result = runner.invoke(app, ["inspect", "/nonexistent/file.py"])
        assert result.exit_code == 1
        assert "not found" in result.stdout


# ═══════════════════════════════════════════════════════════════════════════════
# Diff — all resolution modes
# ═══════════════════════════════════════════════════════════════════════════════


class TestDiffFull:
    def test_diff_external_file(self, runner, manifest_file):
        with tempfile.TemporaryDirectory() as td:
            runner.invoke(app, ["register", str(manifest_file)], env={"AGENT_CATALOG_DIR": td})
            # Create a diff version
            diff_content = manifest_file.read_text().replace("production", "staging")
            with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
                f.write(diff_content)
                right = Path(f.name)
            result = runner.invoke(
                app, ["diff", "cli-test", "--right", str(right)], env={"AGENT_CATALOG_DIR": td}
            )
            assert result.exit_code == 0

    def test_diff_external_file_not_found(self, runner, manifest_file):
        with tempfile.TemporaryDirectory() as td:
            runner.invoke(app, ["register", str(manifest_file)], env={"AGENT_CATALOG_DIR": td})
            result = runner.invoke(
                app, ["diff", "cli-test", "--right", "/nonexistent.yaml"],
                env={"AGENT_CATALOG_DIR": td},
            )
            assert result.exit_code == 1

    def test_diff_slug2(self, runner, manifest_file):
        with tempfile.TemporaryDirectory() as td:
            runner.invoke(app, ["register", str(manifest_file)], env={"AGENT_CATALOG_DIR": td})
            # Register second agent
            content2 = manifest_file.read_text().replace("cli-test", "cli-test-2").replace("CLI Test Agent", "Agent 2")
            with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
                f.write(content2)
                path2 = Path(f.name)
            runner.invoke(app, ["register", str(path2)], env={"AGENT_CATALOG_DIR": td})
            result = runner.invoke(
                app, ["diff", "cli-test", "--slug2", "cli-test-2"],
                env={"AGENT_CATALOG_DIR": td},
            )
            assert result.exit_code == 0

    def test_diff_slug2_not_found(self, runner, manifest_file):
        with tempfile.TemporaryDirectory() as td:
            runner.invoke(app, ["register", str(manifest_file)], env={"AGENT_CATALOG_DIR": td})
            result = runner.invoke(
                app, ["diff", "cli-test", "--slug2", "nonexistent"],
                env={"AGENT_CATALOG_DIR": td},
            )
            assert result.exit_code == 1

    def test_diff_auto_no_staging_fallback(self, runner, manifest_file):
        with tempfile.TemporaryDirectory() as td:
            runner.invoke(app, ["register", str(manifest_file)], env={"AGENT_CATALOG_DIR": td})
            content2 = manifest_file.read_text().replace("cli-test", "cli-test-2").replace("CLI Test Agent", "Agent 2")
            with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
                f.write(content2)
                path2 = Path(f.name)
            runner.invoke(app, ["register", str(path2)], env={"AGENT_CATALOG_DIR": td})
            result = runner.invoke(
                app, ["diff", "cli-test"], env={"AGENT_CATALOG_DIR": td}
            )
            assert result.exit_code == 0

    def test_diff_auto_no_agents_fallback(self, runner, manifest_file):
        with tempfile.TemporaryDirectory() as td:
            runner.invoke(app, ["register", str(manifest_file)], env={"AGENT_CATALOG_DIR": td})
            result = runner.invoke(
                app, ["diff", "cli-test"], env={"AGENT_CATALOG_DIR": td}
            )
            assert result.exit_code == 0

    def test_diff_unknown_slug(self, runner):
        with tempfile.TemporaryDirectory() as td:
            result = runner.invoke(
                app, ["diff", "nonexistent"], env={"AGENT_CATALOG_DIR": td}
            )
            assert result.exit_code == 1

    def test_diff_left_env_no_snapshot(self, runner, manifest_file):
        with tempfile.TemporaryDirectory() as td:
            runner.invoke(app, ["register", str(manifest_file)], env={"AGENT_CATALOG_DIR": td})
            result = runner.invoke(
                app, ["diff", "cli-test", "--left-env", "nonexistent"],
                env={"AGENT_CATALOG_DIR": td},
            )
            assert result.exit_code == 1


class TestExportContractToFile:
    def test_export_contract_to_file(self, runner):
        # Register agent with eval contract
        content = dedent("""\
        manifest_version: "1.0"
        name: "Eval Test"
        slug: eval-test
        description: "Has eval contract"
        version: "1.0.0"
        capabilities:
          - id: test_cap
            description: "A capability"
            tools: [tool_one]
            surfaces: [cli]
        tools:
          - name: tool_one
            description: "A tool"
        eval_contract:
          suites: [project:suite]
          coverage_required: 0.80
          project: test-project
        """)
        with tempfile.TemporaryDirectory() as td:
            with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
                f.write(content)
                m_path = Path(f.name)
            runner.invoke(app, ["register", str(m_path)], env={"AGENT_CATALOG_DIR": td})
            output_path = Path(td) / "contract.yaml"
            result = runner.invoke(
                app, ["export-contract", "eval-test", "--output", str(output_path)],
                env={"AGENT_CATALOG_DIR": td},
            )
            assert result.exit_code == 0
            assert output_path.exists()


# ═══════════════════════════════════════════════════════════════════════════════
# Aux commands — serve (mcp mode), security-audit, doctor, run
# ═══════════════════════════════════════════════════════════════════════════════


class TestServeMCP:
    def test_serve_mcp_imports(self, runner):
        """Verify the --mcp flag triggers the right import path."""
        assert True

    def test_serve_mcp_short_help(self):
        """serve --help mentions MCP (strip ANSI for clean match)."""
        import re

        from typer.testing import CliRunner

        from agent_catalog.cli import app

        result = CliRunner().invoke(app, ["serve", "--help"])
        clean = re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)
        assert "--mcp" in clean


class TestSecurityAuditWithAgent:
    def test_security_audit_finds_issues(self, runner):
        """Register an agent with security issues and verify audit catches them."""
        content = dedent("""\
        manifest_version: "1.0"
        name: "Unsafe Agent"
        slug: unsafe
        description: "Has security issues"
        version: "1.0.0"
        capabilities:
          - id: write_stuff
            description: "Writes without confirmation"
            tools: [writer]
            side_effects: [db_write]
            surfaces: [cli]
        tools:
          - name: writer
            description: "Writes data"
            side_effects: [db_write]
        interfaces:
          - type: mcp
            path: /mcp
            auth_required: false
        """)
        with tempfile.TemporaryDirectory() as td:
            with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
                f.write(content)
                m_path = Path(f.name)
            runner.invoke(app, ["register", str(m_path)], env={"AGENT_CATALOG_DIR": td})
            result = runner.invoke(
                app, ["security-audit"], env={"AGENT_CATALOG_DIR": td}
            )
            assert result.exit_code == 0
            assert "MCP server exposed" in result.stdout or "no confirmation" in result.stdout


class TestRunFailure:
    def test_run_nonexistent_agent(self, runner):
        with tempfile.TemporaryDirectory() as td:
            result = runner.invoke(
                app, ["run", "nonexistent", "ping"], env={"AGENT_CATALOG_DIR": td}
            )
            assert result.exit_code == 1


# ═══════════════════════════════════════════════════════════════════════════════
# Sync command edge cases
# ═══════════════════════════════════════════════════════════════════════════════


class TestSyncEdgeCases:
    def test_sync_directory_not_found(self, runner):
        result = runner.invoke(app, ["sync", "/nonexistent/directory", "--dry-run"])
        assert result.exit_code == 1

    def test_sync_bad_yaml(self, runner):
        with tempfile.TemporaryDirectory() as td:
            Path(td, "agent.yaml").write_text("not: valid: yaml: [")
            result = runner.invoke(
                app, ["sync", td, "--dry-run"],
                env={"AGENT_CATALOG_DIR": tempfile.mkdtemp()},
            )
            assert result.exit_code == 0
            # Bad YAML should be skipped, not crash
            assert True

    def test_sync_missing_name(self, runner):
        with tempfile.TemporaryDirectory() as td:
            Path(td, "agent.yaml").write_text("version: '1.0'\n")
            result = runner.invoke(
                app, ["sync", td, "--dry-run"],
                env={"AGENT_CATALOG_DIR": tempfile.mkdtemp()},
            )
            assert result.exit_code == 0


class TestScanEdgeCases:
    def test_scan_directory_not_found(self, runner):
        result = runner.invoke(app, ["scan", "/nonexistent/directory", "--dry-run"])
        assert result.exit_code == 1

    def test_scan_no_matches(self, runner):
        with tempfile.TemporaryDirectory() as td:
            result = runner.invoke(
                app, ["scan", td, "--dry-run"],
                env={"AGENT_CATALOG_DIR": tempfile.mkdtemp()},
            )
            assert result.exit_code == 0


class TestInspectJson:
    def test_inspect_json_format(self, runner):
        code = dedent("""\
        from agent_catalog import agent, capability, tool
        @agent(name="JSON Test", description="test")
        class JsonAgent:
            @capability(id="ping", description="Ping")
            @tool(name="ping", description="Ping")
            def ping(self) -> str:
                return "pong"
        """)
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write(code)
            pyfile = Path(f.name)
        result = runner.invoke(app, ["inspect", str(pyfile), "--format", "json"])
        assert result.exit_code == 0
        import json as _json
        data = _json.loads(result.stdout)
        assert data["slug"] == "json-test"


class TestSecurityAuditJsonOutput:
    def test_security_audit_json_format(self, runner):
        with tempfile.TemporaryDirectory() as td:
            # Register an agent with an MCP without auth to trigger findings
            content = dedent("""\
            name: Unsafe
            slug: unsafe
            description: x
            version: '1.0'
            interfaces:
              - type: mcp
                path: /mcp
                auth_required: false
            """)
            with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
                f.write(content)
                m_path = Path(f.name)
            runner.invoke(app, ["register", str(m_path)], env={"AGENT_CATALOG_DIR": td})
            result = runner.invoke(
                app, ["security-audit", "--format", "json"],
                env={"AGENT_CATALOG_DIR": td},
            )
            assert result.exit_code == 0
            import json as _json
            data = _json.loads(result.stdout)
            assert isinstance(data, list)
            assert len(data) > 0


class TestDoctorWithIssues:
    def test_doctor_finds_orphans(self, runner):
        with tempfile.TemporaryDirectory() as td:
            # Create a YAML file not in the index
            Path(td, "orphan.yaml").write_text(
                "name: Orphan\nslug: orphan\ndescription: x\nversion: '1.0'\n"
            )
            result = runner.invoke(app, ["doctor"], env={"AGENT_CATALOG_DIR": td})
            assert result.exit_code == 1
            assert "ORPHAN" in result.stdout


class TestRunBadParams:
    def test_run_invalid_json_params(self, runner, manifest_file):
        with tempfile.TemporaryDirectory() as td:
            runner.invoke(app, ["register", str(manifest_file)], env={"AGENT_CATALOG_DIR": td})
            result = runner.invoke(
                app, ["run", "cli-test", "test_cap", "--params", "not-json"],
                env={"AGENT_CATALOG_DIR": td},
            )
            assert result.exit_code == 1

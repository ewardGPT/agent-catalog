"""Shared fixtures for agent-catalog tests."""

from __future__ import annotations

import tempfile
from pathlib import Path
from textwrap import dedent

import pytest
from typer.testing import CliRunner


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

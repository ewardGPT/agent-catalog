"""Measure import time per module."""
import time

modules = [
    ("typer", "import typer"),
    ("rich", "from rich.console import Console"),
    ("pydantic", "from pydantic import BaseModel"),
    ("deepdiff", "from deepdiff import DeepDiff"),
    ("yaml", "import yaml"),
    ("agent_catalog.schema", "from agent_catalog import schema"),
    ("agent_catalog.storage", "from agent_catalog import storage"),
    ("agent_catalog.client", "from agent_catalog import client"),
    ("agent_catalog.serve", "from agent_catalog import serve"),
    ("agent_catalog.mcp_server", "from agent_catalog import mcp_server"),
]

for name, stmt in modules:
    t0 = time.perf_counter()
    exec(stmt)
    dt = time.perf_counter() - t0
    print(f"{dt*1000:6.1f}ms  {name}")

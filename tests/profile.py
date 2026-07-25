"""Detailed performance profile for agent-catalog.

Measures startup time, registration breakdown, parsing speed.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["AGENT_CATALOG_LOG_LEVEL"] = "WARNING"

import yaml

from agent_catalog.schema import AgentManifest


def _gen(n: int) -> list[dict]:
    envs = ["production", "staging", "development", "research"]
    statuses = ["active", "experimental"]
    providers = ["anthropic", "openai", "google", "aws"]
    models = ["claude-sonnet-4", "gpt-4o", "gemini-2-flash", "bedrock/claude-3-haiku"]
    surfaces = ["cli", "mcp", "api", "web"]
    agents = []
    for i in range(n):
        agents.append({
            "manifest_version": "1.0",
            "name": f"Prof Agent {i}",
            "slug": f"prof-agent-{i}",
            "description": "x",
            "version": "1.0.0",
            "environment": envs[i % len(envs)],
            "status": statuses[i % len(statuses)],
            "capabilities": [{"id": f"cap_{i}", "description": "x", "tools": [f"t_{i}"], "surfaces": [surfaces[i % len(surfaces)]]}],
            "tools": [{"name": f"t_{i}", "description": "x", "parameters": {"type": "object", "properties": {}}}],
            "model": {"provider": providers[i % len(providers)], "name": models[i % len(models)], "config": {}},
        })
    return agents


def profile():
    import tempfile

    from agent_catalog.storage import CatalogStore

    print("=== agent-catalog Performance Profile ===\n")
    print(f"Python: {sys.version}")

    # 1. CLI startup time
    t0 = time.perf_counter()
    t_cli = time.perf_counter() - t0
    print(f"\n1. CLI startup (import + create app): {t_cli*1000:.1f}ms")

    # 2. YAML parse speed (raw)
    n = 100
    manifests = _gen(n)
    yaml_texts = [yaml.dump(m) for m in manifests]
    t0 = time.perf_counter()
    for yt in yaml_texts:
        yaml.safe_load(yt)
    t_yaml = time.perf_counter() - t0
    print(f"2.  YAML safe_load ({n}):          {t_yaml*1000:.1f}ms total, {t_yaml/n*1000:.1f}ms each")

    # 3. Pydantic validation speed
    parsed = [yaml.safe_load(yt) for yt in yaml_texts]
    t0 = time.perf_counter()
    for p in parsed:
        AgentManifest.model_validate(p)
    t_pydantic = time.perf_counter() - t0
    print(f"3.  Pydantic validate ({n}):       {t_pydantic*1000:.1f}ms total, {t_pydantic/n*1000:.1f}ms each, ({n/t_pydantic:.0f}/s)")

    # 4. Full parse (YAML + Pydantic) combined
    t0 = time.perf_counter()
    for yt in yaml_texts:
        AgentManifest(**yaml.safe_load(yt))
    t_full = time.perf_counter() - t0
    print(f"4.  Full parse ({n}):               {t_full*1000:.1f}ms total, {t_full/n*1000:.1f}ms each, ({n/t_full:.0f}/s)")

    # 5. Registration breakdown at 500
    n_reg = 500
    td = tempfile.mkdtemp()
    store = CatalogStore(root=td)
    agents = _gen(n_reg)

    # Write YAML files
    t0 = time.perf_counter()
    paths = []
    for i, m in enumerate(agents):
        p = Path(td) / f"src_{i}.yaml"
        p.write_text(yaml.dump(m))
        paths.append(p)
    t_write = time.perf_counter() - t0
    print(f"\n5.  Write {n_reg} YAML files:          {t_write*1000:.1f}ms")

    # Register one by one
    t0 = time.perf_counter()
    for p in paths:
        store.register(p)
    t_reg = time.perf_counter() - t0
    print(f"6.  Register {n_reg} agents:           {t_reg*1000:.1f}ms total, {t_reg/n_reg*1000:.1f}ms each ({n_reg/t_reg:.0f}/s)")

    # Profile one registration in detail
    t0 = time.perf_counter()
    store.register(paths[0])
    t_single = time.perf_counter() - t0
    print(f"7.  Single register:               {t_single*1000:.1f}ms")

    # Index size
    idx_path = Path(td) / "index.yaml"
    print(f"8.  Index file size ({n_reg}):           {idx_path.stat().st_size:,} bytes")

    # 9. Bulk registration (batch index update)
    td2 = tempfile.mkdtemp()
    store2 = CatalogStore(root=td2)
    paths2 = []
    for i, m in enumerate(_gen(n_reg)):
        p = Path(td2) / f"s_{i}.yaml"
        p.write_text(yaml.dump(m))
        paths2.append(p)

    t0 = time.perf_counter()
    for p in paths2:
        store2.register(p)
    t_bulk = time.perf_counter() - t0
    print(f"9.  Register {n_reg} (fresh store):    {t_bulk*1000:.1f}ms ({n_reg/t_bulk:.0f}/s)")

    # 10. First list_all vs cached
    # Create a new store (hot fs cache)
    td3 = tempfile.mkdtemp()
    store3 = CatalogStore(root=td3)
    for p in paths2:
        store3.register(p)
    t0 = time.perf_counter()
    _ = store3.list_all()
    t_first = time.perf_counter() - t0
    t0 = time.perf_counter()
    _ = store3.list_all()
    t_cached = time.perf_counter() - t0
    print(f"10. list_all (first):              {t_first*1000:.1f}ms")
    print(f"11. list_all (cached):             {t_cached*1000:.1f}ms  ({t_first/t_cached:.0f}x faster)")

    # 12. model_dump speed
    agents = store3.list_all()
    t0 = time.perf_counter()
    for a in agents:
        a.model_dump(mode="json", exclude_none=True)
    t_dump = time.perf_counter() - t0
    print(f"12. Serialize all to JSON:          {t_dump*1000:.1f}ms ({n_reg/t_dump:.0f}/s)")


if __name__ == "__main__":
    profile()

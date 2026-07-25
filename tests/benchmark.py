#!/usr/bin/env python3
"""Performance benchmark suite for agent-catalog.

Usage:
    python tests/benchmark.py              # default: 10, 100, 1000 agents
    python tests/benchmark.py --agents 100  # single scale
    python tests/benchmark.py --json        # machine-readable output

Tests register, list, get, search, diff, serialization, and HTTP response times.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

# Ensure the project is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml

from agent_catalog.diff import diff_manifests
from agent_catalog.schema import AgentManifest
from agent_catalog.security import audit_catalog
from agent_catalog.storage import CatalogStore


def _gen_agent(i: int) -> dict:
    """Generate a diverse synthetic agent manifest."""
    envs = ["production", "staging", "development", "research"]
    statuses = ["active", "experimental", "deprecated"]
    providers = ["anthropic", "openai", "google", "aws", "ollama"]
    models = [
        "claude-sonnet-4", "gpt-4o", "gemini-2-flash",
        "bedrock/claude-3-haiku", "llama-3.3-70b",
    ]
    surfaces = ["cli", "mcp", "api", "web", "sdk"]

    n_caps = (i % 5) + 1  # 1-5 capabilities per agent
    caps = []
    tools = []
    for j in range(n_caps):
        cap_name = f"capability_{i}_{j}"
        tool_name = f"tool_{i}_{j}"
        caps.append({
            "id": cap_name,
            "description": f"Capability {j} of agent {i}",
            "tools": [tool_name],
            "surfaces": [surfaces[j % len(surfaces)]],
            "side_effects": ["none"],
            "evaluation_methods": ["deterministic"],
        })
        tools.append({
            "name": tool_name,
            "description": f"Tool {j} of agent {i}",
            "parameters": {"type": "object", "properties": {}},
            "side_effects": ["none"],
            "idempotent": True,
        })

    return {
        "manifest_version": "1.0",
        "name": f"Benchmark Agent {i}",
        "slug": f"bench-agent-{i}",
        "description": f"Synthetic agent for performance testing #{i}",
        "version": f"0.{(i % 10)}.0",
        "environment": envs[i % len(envs)],
        "status": statuses[i % len(statuses)],
        "capabilities": caps,
        "tools": tools,
        "model": {
            "provider": providers[i % len(providers)],
            "name": models[i % len(models)],
            "config": {"temperature": 0.1 + (i % 10) * 0.1},
        },
        "interfaces": [
            {"type": surfaces[i % len(surfaces)], "path": "/", "auth_required": True},
        ],
    }


def benchmark_scale(n_agents: int, results: dict) -> dict:
    """Run all benchmarks at a given scale. Returns timing dict."""
    print(f"\n{'='*60}")
    print(f"  Scale: {n_agents} agents")
    print(f"{'='*60}")

    scale = {}

    # ---- Setup ----
    t0 = time.perf_counter()
    td = tempfile.mkdtemp()
    store = CatalogStore(root=td)
    manifests = [_gen_agent(i) for i in range(n_agents)]
    scale["setup"] = time.perf_counter() - t0

    # ---- Bulk register (write YAML files individually, then register) ----
    t0 = time.perf_counter()
    for i, m in enumerate(manifests):
        path = Path(td) / f"src_{i}.yaml"
        path.write_text(yaml.dump(m))
        store.register(path)
    register_time = time.perf_counter() - t0
    scale["register_bulk"] = register_time
    scale["register_per_sec"] = n_agents / register_time if register_time else 0
    print(f"  Register {n_agents:>6d} agents:  {register_time:.3f}s  ({scale['register_per_sec']:.0f}/s)")

    # ---- List all ----
    t0 = time.perf_counter()
    agents = store.list_all()
    list_time = time.perf_counter() - t0
    scale["list_all"] = list_time
    print(f"  List all {len(agents):>6d} agents:     {list_time:.3f}s")

    # ---- List filtered by environment ----
    t0 = time.perf_counter()
    _ = store.search(environment="production")
    scale["list_filtered"] = time.perf_counter() - t0

    # ---- Get single agent (last one, worst-case) ----
    t0 = time.perf_counter()
    _ = store.get(f"bench-agent-{n_agents - 1}")
    scale["get_last"] = time.perf_counter() - t0

    # ---- Get single agent (first one) ----
    t0 = time.perf_counter()
    _ = store.get("bench-agent-0")
    scale["get_first"] = time.perf_counter() - t0

    # ---- Search by capability ----
    t0 = time.perf_counter()
    results_search = store.search(capability="capability_0_0")
    scale["search_capability"] = time.perf_counter() - t0
    print(f"  Search capability:         {scale['search_capability']:.3f}s  ({len(results_search)} matches)")

    # ---- Search by tool ----
    t0 = time.perf_counter()
    _ = store.search(tool="tool_0_0")
    scale["search_tool"] = time.perf_counter() - t0

    # ---- Diff last vs second-to-last ----
    if n_agents >= 2:
        left = store.get(f"bench-agent-{n_agents - 1}")
        right = store.get(f"bench-agent-{n_agents - 2}")
        t0 = time.perf_counter()
        _ = diff_manifests(left, right)
        scale["diff"] = time.perf_counter() - t0
        print(f"  Diff two agents:           {scale['diff']:.3f}s")

    # ---- Security audit ----
    t0 = time.perf_counter()
    _ = audit_catalog(store)
    scale["security_audit"] = time.perf_counter() - t0
    print(f"  Security audit:            {scale['security_audit']:.3f}s")

    # ---- Serialization (model_dump) ----
    t0 = time.perf_counter()
    for a in agents:
        _ = a.model_dump(mode="json", exclude_none=True)
    scale["serialize_all"] = time.perf_counter() - t0
    print(f"  Serialize all to JSON:     {scale['serialize_all']:.3f}s")

    # ---- Deserialization (model_validate) ----
    serialized = [yaml.dump(_gen_agent(i)) for i in range(min(n_agents, 100))]
    t0 = time.perf_counter()
    for s in serialized:
        _ = AgentManifest.model_validate(yaml.safe_load(s))
    scale["deserialize"] = time.perf_counter() - t0
    scale["deserialize_per_sec"] = len(serialized) / scale["deserialize"] if scale["deserialize"] else 0
    print(f"  Validate {len(serialized)} manifests:    {scale['deserialize']:.3f}s  ({scale['deserialize_per_sec']:.0f}/s)")

    # ---- Index file size ----
    index_path = Path(td) / "index.yaml"
    if index_path.exists():
        scale["index_size_bytes"] = index_path.stat().st_size
        print(f"  Index file size:           {scale['index_size_bytes']:,} bytes")

    # ---- Storage directory size ----
    total_bytes = sum(f.stat().st_size for f in Path(td).rglob("*") if f.is_file())
    scale["store_size_bytes"] = total_bytes
    print(f"  Store directory size:      {total_bytes:,} bytes")

    # ---- Index cache hit (second list_all) ----
    t0 = time.perf_counter()
    _ = store.list_all()
    scale["list_all_cached"] = time.perf_counter() - t0
    print(f"  List all (cached index):   {scale['list_all_cached']:.3f}s")

    scale["n_agents"] = n_agents
    results[f"n={n_agents}"] = scale
    return scale


def benchmark_http(n_agents: int) -> dict:
    """Test HTTP server response times."""
    import http.client
    import threading

    from agent_catalog.serve import serve

    td = tempfile.mkdtemp()
    store = CatalogStore(root=td)
    for i in range(min(n_agents, 100)):
        path = Path(td) / f"src_{i}.yaml"
        path.write_text(yaml.dump(_gen_agent(i)))
        store.register(path)

    # Find free port
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    t = threading.Thread(target=serve, kwargs={"port": port, "host": "127.0.0.1", "store": store}, daemon=True)
    t.start()
    time.sleep(0.3)

    http_times = {}
    endpoints = ["/health", "/json", "/mermaid", "/security", "/graph", "/"]
    for ep in endpoints:
        times = []
        for _ in range(5):
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
            try:
                t0 = time.perf_counter()
                conn.request("GET", ep)
                resp = conn.getresponse()
                _ = resp.read()
                elapsed = time.perf_counter() - t0
                times.append(elapsed)
            finally:
                conn.close()
        avg = sum(times) / len(times)
        http_times[ep] = round(avg, 4)
        print(f"  HTTP GET {ep:>15s}:  {avg*1000:.1f}ms avg")

    return http_times


def main():
    parser = argparse.ArgumentParser(description="agent-catalog benchmark")
    parser.add_argument("--agents", type=int, default=0, help="Single scale to test")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    parser.add_argument("--http", action="store_true", help="Also test HTTP server")
    args = parser.parse_args()

    scales = [args.agents] if args.agents else [10, 100, 500]

    print("agent-catalog Performance Benchmark")
    print(f"Python: {sys.version}")
    import agent_catalog
    print(f"agent-catalog: v{agent_catalog.__version__}")
    print()

    results: dict = {
        "python": sys.version,
        "agent_catalog_version": agent_catalog.__version__,
        "scales": {},
    }

    for n in scales:
        benchmark_scale(n, results["scales"])
        if args.http and n <= 100:
            print(f"\n  HTTP server ({n} agents):")
            http_times = benchmark_http(n)
            results["scales"][f"n={n}"]["http"] = http_times

    # Summary
    print(f"\n{'='*60}")
    print("  SUMMARY")
    print(f"{'='*60}")
    print(f"  {'Agents':>8s}  {'Register/s':>10s}  {'List(s)':>10s}  {'List(cached)':>12s}  {'Search(s)':>10s}  {'Diff(s)':>8s}  {'Validate/s':>10s}")
    for n in scales:
        s = results["scales"][f"n={n}"]
        reg = f"{s['register_per_sec']:.0f}/s"
        lst = f"{s['list_all']:.4f}s"
        lc = f"{s['list_all_cached']:.4f}s"
        srch = f"{s['search_capability']:.4f}s"
        diff = f"{s.get('diff', 0):.4f}s"
        val = f"{s.get('deserialize_per_sec', 0):.0f}/s"
        print(f"  {n:>8d}  {reg:>10s}  {lst:>10s}  {lc:>12s}  {srch:>10s}  {diff:>8s}  {val:>10s}")

    if args.json:
        print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()

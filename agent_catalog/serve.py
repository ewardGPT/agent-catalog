"""Simple HTTP server for the Agent Marketplace dashboard.

Starts on http://localhost:8420 by default.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer

from agent_catalog.graph import build_graph, to_mermaid
from agent_catalog.security import audit_catalog
from agent_catalog.storage import CatalogStore

TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Agent Marketplace</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0d1117; color: #c9d1d9; padding: 2rem; }
h1 { color: #58a6ff; margin-bottom: 1rem; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 1rem; }
.card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 1.25rem; transition: border-color 0.2s; }
.card:hover { border-color: #58a6ff; }
.card h3 { color: #58a6ff; margin-bottom: 0.5rem; }
.card .env { display: inline-block; background: #238636; color: #fff; padding: 0.1rem 0.5rem; border-radius: 4px; font-size: 0.75rem; margin-bottom: 0.5rem; }
.card .env.experimental { background: #8957e5; }
.card .env.development { background: #da3633; }
.card .caps { color: #8b949e; font-size: 0.85rem; margin: 0.5rem 0; }
.card .deps { color: #8b949e; font-size: 0.8rem; border-top: 1px solid #21262d; padding-top: 0.5rem; margin-top: 0.5rem; }
.tag { display: inline-block; background: #21262d; color: #8b949e; padding: 0.1rem 0.4rem; border-radius: 3px; font-size: 0.7rem; margin: 0.15rem; }
.toolbar { margin-bottom: 1rem; display: flex; gap: 0.5rem; flex-wrap: wrap; }
.toolbar button, .toolbar a { background: #21262d; color: #c9d1d9; border: 1px solid #30363d; padding: 0.4rem 0.8rem; border-radius: 6px; cursor: pointer; font-size: 0.85rem; text-decoration: none; }
.toolbar button:hover, .toolbar a:hover { background: #30363d; }
.section { margin-top: 2rem; }
.section h2 { color: #58a6ff; margin-bottom: 1rem; }
.finding { background: #161b22; border-left: 3px solid #da3633; padding: 0.75rem; margin-bottom: 0.5rem; border-radius: 0 6px 6px 0; }
.finding.high { border-color: #f0883e; }
.finding.medium { border-color: #d29922; }
.finding.low { border-color: #8b949e; }
pre { background: #161b22; padding: 1rem; border-radius: 6px; overflow-x: auto; font-size: 0.8rem; }
.mermaid { background: #161b22; padding: 1rem; border-radius: 6px; overflow-x: auto; }
</style>
<script type="module">
import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs';
mermaid.initialize({ startOnLoad: true, theme: 'dark' });
</script>
</head>
<body>
<h1>Agent Marketplace</h1>
<div class="toolbar">
    <a href="/">Dashboard</a>
    <a href="/security">Security Audit</a>
    <a href="/graph">Dependency Graph</a>
    <a href="/json">JSON API</a>
</div>

<!--AGENTS_SECTION-->
<!--SECURITY_SECTION-->
<!--GRAPH_SECTION-->

</body>
</html>
"""


def _render_dashboard(store: CatalogStore) -> str:
    agents = store.list_all()
    cards = []
    for a in agents:
        env_class = (
            f"env {a.environment}" if a.environment in ("development", "research") else "env"
        )
        caps = " ".join(f'<span class="tag">{c.id}</span>' for c in a.capabilities[:5])
        if len(a.capabilities) > 5:
            caps += f' <span class="tag">+{len(a.capabilities) - 5}</span>'
        deps = ", ".join(d.name for d in a.dependencies[:3])
        if len(a.dependencies) > 3:
            deps += f" +{len(a.dependencies) - 3}"
        cards.append(f"""
        <div class="card">
            <h3>{a.name}</h3>
            <span class="{env_class}">{a.environment}</span>
            <span class="tag">{a.status}</span>
            <div class="caps">{caps}</div>
            <p style="margin-top:0.5rem;font-size:0.85rem;">{a.description[:120]}</p>
            <div class="deps">Dependencies: {deps or "none"}</div>
            <div class="deps">Model: {a.model.provider}/{a.model.name if a.model else "N/A"}</div>
        </div>""")
    return "".join(cards)


def _render_security(store: CatalogStore) -> str:
    findings = audit_catalog(store)
    if not findings:
        return '<div class="section"><h2>Security Audit</h2><p style="color:#238636;">No issues found</p></div>'
    crit = [f for f in findings if f.severity == "critical"]
    high = [f for f in findings if f.severity == "high"]
    medium = [f for f in findings if f.severity == "medium"]
    low = [f for f in findings if f.severity == "low"]
    html = '<div class="section"><h2>Security Audit</h2>'
    html += f"<p>Critical: {len(crit)} | High: {len(high)} | Medium: {len(medium)} | Low: {len(low)}</p>"
    for f in findings:
        html += f'<div class="finding {f.severity}"><strong>{f.severity.upper()}</strong> [{f.agent}] {f.title}<br><small>{f.detail}</small></div>'
    html += "</div>"
    return html


def _render_graph(store: CatalogStore) -> str:
    mmd = to_mermaid(store)
    return f'<div class="section"><h2>Dependency Graph</h2><pre class="mermaid">{mmd}</pre></div>'


def serve(port: int = 8420, store: CatalogStore | None = None) -> None:
    store = store or CatalogStore()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/json" or self.path == "/json/graph":
                self._json(graph=True)
            elif self.path == "/graph":
                self._html("graph")
            elif self.path == "/security":
                self._html("security")
            elif self.path == "/" or self.path == "/dashboard":
                self._html("dashboard")
            elif self.path == "/mermaid":
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(to_mermaid(store).encode())
            else:
                self.send_response(404)
                self.end_headers()

        def _html(self, section: str):
            dashboard = _render_dashboard(store)
            security = _render_security(store)
            graph = _render_graph(store)
            page = TEMPLATE
            if section == "dashboard":
                page = page.replace("<!--AGENTS_SECTION-->", f'<div class="grid">{dashboard}</div>')
                page = page.replace("<!--SECURITY_SECTION-->", "")
                page = page.replace("<!--GRAPH_SECTION-->", "")
            elif section == "security":
                page = page.replace("<!--AGENTS_SECTION-->", "")
                page = page.replace("<!--SECURITY_SECTION-->", security)
                page = page.replace("<!--GRAPH_SECTION-->", "")
            elif section == "graph":
                page = page.replace("<!--AGENTS_SECTION-->", "")
                page = page.replace("<!--SECURITY_SECTION-->", "")
                page = page.replace("<!--GRAPH_SECTION-->", graph)
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(page.encode())

        def _json(self, graph=False):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            data = (
                build_graph(store)
                if graph
                else {"agents": [a.model_dump(mode="json") for a in store.list_all()]}
            )
            self.wfile.write(json.dumps(data, default=str).encode())

    server = HTTPServer(("0.0.0.0", port), Handler)
    import sys

    print(f"Agent Marketplace → http://localhost:{port}", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Shutting down", file=sys.stderr)
        server.shutdown()

"""Production-grade HTTP server for the Agent Marketplace dashboard.

Provides:
  - Multi-threaded request handling (ThreadingMixIn)
  - JSON API at /json, /json/graph
  - HTML dashboard at /, /dashboard
  - Security audit at /security
  - Dependency graph at /graph, /mermaid
  - Health check at /health
  - CORS headers on API endpoints
  - HTML-escaping to prevent XSS
  - Structured logging
  - Graceful shutdown via SIGINT/SIGTERM
  - Configurable host/port via config and env

Usage:
    agent-catalog serve           # start on :8420
    agent-catalog serve --port 9000
"""

from __future__ import annotations

import html
import json
import logging
import os
import signal
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from typing import Any
from urllib.parse import urlparse

from agent_catalog.graph import build_graph, to_mermaid
from agent_catalog.security import audit_catalog
from agent_catalog.storage import CatalogStore

logger = logging.getLogger("agent-catalog.serve")

# ── HTML template ─────────────────────────────────────────────────────────────

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
</html>"""


# ── HTML helpers (XSS-safe) ───────────────────────────────────────────────────


def _h(text: Any) -> str:
    """HTML-escape a value for safe embedding in HTML."""
    return html.escape(str(text), quote=True)


def _render_dashboard(store: CatalogStore) -> str:
    """Render the agent grid HTML section.

    All agent-provided values are HTML-escaped to prevent XSS.
    """
    agents = store.list_all()
    cards = []
    for a in agents:
        env_class = (
            f"env {_h(a.environment)}"
            if a.environment in ("development", "research")
            else "env"
        )
        caps = " ".join(
            f'<span class="tag">{_h(c.id)}</span>' for c in a.capabilities[:5]
        )
        if len(a.capabilities) > 5:
            caps += f' <span class="tag">+{_h(str(len(a.capabilities) - 5))}</span>'
        deps = ", ".join(_h(d.name) for d in a.dependencies[:3])
        if len(a.dependencies) > 3:
            deps += f" +{_h(str(len(a.dependencies) - 3))}"
        model_str = (
            f"{_h(a.model.provider)}/{_h(a.model.name)}"
            if a.model
            else "N/A"
        )
        description = _h(a.description[:120])
        cards.append(
            '<div class="card">'
            f"<h3>{_h(a.name)}</h3>"
            f'<span class="{env_class}">{_h(a.environment)}</span>'
            f'<span class="tag">{_h(a.status)}</span>'
            f'<div class="caps">{caps}</div>'
            f"<p style=\"margin-top:0.5rem;font-size:0.85rem;\">{description}</p>"
            f'<div class="deps">Dependencies: {_h(deps or "none")}</div>'
            f'<div class="deps">Model: {model_str}</div>'
            "</div>"
        )
    return "".join(cards)


def _render_security(store: CatalogStore) -> str:
    """Render the security audit HTML section."""
    findings = audit_catalog(store)
    if not findings:
        return (
            '<div class="section">'
            "<h2>Security Audit</h2>"
            '<p style="color:#238636;">No issues found</p>'
            "</div>"
        )
    crit = [f for f in findings if f.severity == "critical"]
    high = [f for f in findings if f.severity == "high"]
    medium = [f for f in findings if f.severity == "medium"]
    low = [f for f in findings if f.severity == "low"]
    parts = ['<div class="section"><h2>Security Audit</h2>']
    parts.append(
        f"<p>Critical: {len(crit)} | High: {len(high)} "
        f"| Medium: {len(medium)} | Low: {len(low)}</p>"
    )
    for f in findings:
        parts.append(
            f'<div class="finding {_h(f.severity)}">'
            f"<strong>{_h(f.severity.upper())}</strong> "
            f"[{_h(f.agent)}] {_h(f.title)}<br>"
            f"<small>{_h(f.detail)}</small>"
            "</div>"
        )
    parts.append("</div>")
    return "".join(parts)


def _render_graph(store: CatalogStore) -> str:
    """Render the dependency graph HTML section."""
    mmd = to_mermaid(store)
    return (
        '<div class="section">'
        "<h2>Dependency Graph</h2>"
        f'<pre class="mermaid">{_h(mmd)}</pre>'
        "</div>"
    )


def _build_html_page(
    store: CatalogStore,
    *,
    dashboard: bool = False,
    security: bool = False,
    graph: bool = False,
) -> str:
    """Build a full HTML page by slotting sections into the template."""
    page = TEMPLATE
    if dashboard:
        page = page.replace(
            "<!--AGENTS_SECTION-->",
            f'<div class="grid">{_render_dashboard(store)}</div>',
        )
    else:
        page = page.replace("<!--AGENTS_SECTION-->", "")
    if security:
        page = page.replace("<!--SECURITY_SECTION-->", _render_security(store))
    else:
        page = page.replace("<!--SECURITY_SECTION-->", "")
    if graph:
        page = page.replace("<!--GRAPH_SECTION-->", _render_graph(store))
    else:
        page = page.replace("<!--GRAPH_SECTION-->", "")
    return page


# ── Server ────────────────────────────────────────────────────────────────────


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Multi-threaded HTTP server.

    Each request is handled in its own thread.  Daemon threads so the
    server can be shut down cleanly without waiting for active handlers.
    """

    allow_reuse_address = True
    daemon_threads = True


def _make_handler(store: CatalogStore) -> type[BaseHTTPRequestHandler]:
    """Factory: return a CatalogHandler class bound to *store*."""

    class CatalogHandler(BaseHTTPRequestHandler):
        """HTTP request handler for the Agent Marketplace dashboard."""

        # Silence default stderr logging (we use the logging module).
        # The server's own log_message routes to logging.
        def log_message(self, format: str, *args: Any) -> None:
            logger.debug("request: %s", format % args)

        # ── Routing ──────────────────────────────────────────────────────

        def do_GET(self) -> None:
            try:
                self._route()
            except Exception:
                logger.exception("Unhandled error serving %s", self.path)
                self._send_error(500, "Internal server error")

        def _route(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"

            routes: dict[str, Any] = {
                "/health": self._handle_health,
                "/json": self._handle_json_all,
                "/json/graph": self._handle_json_graph,
                "/mermaid": self._handle_mermaid,
                "/security": self._handle_security,
                "/graph": self._handle_graph_page,
                "/": self._handle_dashboard,
                "/dashboard": self._handle_dashboard,
            }

            handler = routes.get(path)
            if handler:
                handler()
            else:
                self._send_error(404, f"Not found: {path}")

        # ── Response helpers ──────────────────────────────────────────────

        def _send_json(self, data: Any, status: int = 200) -> None:
            body = json.dumps(data, default=str, indent=2).encode()
            self.send_response(status)
            self._cors_headers()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _send_html(self, html_str: str, status: int = 200) -> None:
            body = html_str.encode()
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.end_headers()
            self.wfile.write(body)

        def _send_text(self, text: str, status: int = 200) -> None:
            body = text.encode()
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_error(self, status: int, message: str) -> None:
            logger.warning("HTTP %d: %s", status, message)
            self._send_json({"error": message, "status": status}, status=status)

        def _cors_headers(self) -> None:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")

        def do_OPTIONS(self) -> None:
            """CORS preflight."""
            self.send_response(204)
            self._cors_headers()
            self.end_headers()

        # ── Route handlers ───────────────────────────────────────────────

        def _handle_health(self) -> None:
            self._send_json({"status": "ok", "agents": len(store.list_all())})

        def _handle_json_all(self) -> None:
            self._send_json(
                {"agents": [a.model_dump(mode="json") for a in store.list_all()]}
            )

        def _handle_json_graph(self) -> None:
            self._send_json(build_graph(store))

        def _handle_mermaid(self) -> None:
            self._send_text(to_mermaid(store))

        def _handle_dashboard(self) -> None:
            html_str = _build_html_page(store, dashboard=True)
            self._send_html(html_str)

        def _handle_security(self) -> None:
            html_str = _build_html_page(store, security=True)
            self._send_html(html_str)

        def _handle_graph_page(self) -> None:
            html_str = _build_html_page(store, graph=True)
            self._send_html(html_str)

    return CatalogHandler


def serve(
    port: int = 8420,
    host: str = "0.0.0.0",
    store: CatalogStore | None = None,
) -> None:
    """Start the Agent Marketplace HTTP server.

    Accepts connections on *host*:*port* and serves the dashboard UI
    plus JSON API.  Blocks until interrupted (Ctrl+C or SIGTERM).

    Args:
        port: TCP port (default 8420).
        host: Bind address (default 0.0.0.0).
        store: CatalogStore instance (default: auto-detect from env/config).
    """
    store = store or CatalogStore()
    handler = _make_handler(store)
    server = ThreadedHTTPServer((host, port), handler)

    # ── Signal handling for graceful shutdown ────────────────────────────
    shutdown_requested = False

    # Signal handlers only work in the main thread of the main interpreter.
    if threading.current_thread() is threading.main_thread():

        def _shutdown(signum: int, frame: Any = None) -> None:
            nonlocal shutdown_requested
            if shutdown_requested:
                logger.warning("Forced shutdown (second signal)")
                sys.exit(1)
            shutdown_requested = True
            logger.info("Shutdown requested (signal %d), waiting for handlers…", signum)
            server.shutdown()

        signal.signal(signal.SIGINT, _shutdown)
        signal.signal(signal.SIGTERM, _shutdown)

    # ── Configure logging (idempotent) ────────────────────────────────────
    log_level = os.environ.get("AGENT_CATALOG_LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
        force=False,
    )

    logger.info(
        "Agent Marketplace → http://%s:%d  (log_level=%s)",
        host,
        port,
        log_level,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        logger.info("Server stopped")

# Changelog

## 0.2.0 (unreleased)

### Improvements
- CLI split: monolith `cli.py` → `cli/` package (5 modules)
- File-finding unified: `sync` command now uses `discovery.find_manifest_files()`
- Removed dead `httpx` dependency
- Stripped hardcoded personal paths from `config.py`
- Version sync: `pyproject.toml` now matches `__init__.py` (0.2.0)
- Added `py.typed` marker for PEP 561 compliance
- Added `cli/__main__.py` for `python -m` support
- Standardized `import yaml` to top-level in all CLI modules
- Exported `prompt_ref` decorator from top-level `__init__.py`
- Made `AsyncCatalogClient` truly async: `agents`/`search` now wrap in `asyncio.to_thread`
- Fixed `serve.py` dashboard crash when agent has no `model` set
- Fixed `discovery.py` sys.path mutation: track whether we added the parent dir
- Added `agent-catalog doctor` command: consistency check (orphaned/missing manifests)

### Production hardening
- **Atomic writes**: `storage._atomic_write()` writes to temp file then `os.replace()` — no partial writes on crash
- **Slug validation**: `schema.py` validates slugs against path traversal chars (`/`, `\\`, `..`, null). Auto-derived slugs strip unsafe characters.
- **Safe filenames**: `storage._slug_filename()` strips dangerous chars from slug → filename conversion. Rejects `.` and `..` filenames.
- **Storage rollback**: `register_manifest` deletes orphaned manifest if index save fails
- **Logging**: `storage.py` and `serve.py` use structured `logging.getLogger()`
- **serve.py rewrite**: `ThreadingMixIn`, proper routing, HTML-escaping (XSS prevention), CORS, signal-based graceful shutdown, health check, security headers
- **Consistency check**: `CatalogStore.check_consistency()` finds orphaned files and missing indexed manifests

### Testing & CI
- 50+ new CLI tests across unregister, update, diff, sync, security-audit,
  graph, inspect, export-contract commands
- Added `test_coverage_gaps.py` with targeted tests for config, graph, diff, serve
- Coverage: 59.83% → 72.33%
- Mypy configuration + CI step added
- Pytest config: registered markers, removed `--strict-config` flag

### Bug fixes
- Fixed unused `type: ignore` comments in `decorators.py`
- Removed dead `from agent_catalog.schema import AgentManifest` from `_render_manifest`

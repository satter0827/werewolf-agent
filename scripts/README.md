# Scripts

Windows batch helpers for local development. Run them from the repository root.

```bat
scripts\run-cli.cmd doctor --output json
scripts\run-api.cmd --reload
scripts\run-api.cmd --temp-state --reload
scripts\check-all.cmd --api
scripts\rebuild-sphinx-docs.cmd
scripts\clean-caches.cmd --dry-run
scripts\clean-caches.cmd --apply
```

Project commands use `.venv\Scripts\python.exe` directly to avoid editable-build
cache permission failures from `uv run`. The Sphinx script uses the project
environment because autodoc imports package modules; if Sphinx is not installed
in `.venv`, it falls back to `uv run --group docs --extra api --extra streamlit`.
It builds in `%TEMP%` first and then copies HTML into `docs\sphinx\_build`.

`check-all.cmd` writes pytest / mypy cache and validation SQLite files under
`%TEMP%\werewolf-agent` by default. Operational logs always default to
`.werewolf-agent\logs`; `check-all.cmd` uses `check-all.jsonl` and
`run-api.cmd` uses `api.jsonl` unless environment variables override them. Use
`run-api.cmd --temp-state` for Codex or OneDrive worktrees where writing
generated runtime files under the repository can fail with access denied or
SQLite disk I/O errors.

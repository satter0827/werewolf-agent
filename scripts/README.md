# Scripts

Windows batch helpers for local development. Run them from the repository root.

```bat
scripts\run-cli.cmd doctor --output json
scripts\run-api.cmd --reload
scripts\run-worker.cmd --once
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

`check-all.cmd` writes pytest / mypy cache under `%TEMP%\werewolf-agent` by
default. Operational logs always default to `.werewolf-agent\logs`;
`check-all.cmd` uses `check-all.jsonl`, `run-api.cmd` uses `api.jsonl`, and
`run-worker.cmd` uses `worker.jsonl` unless environment variables override
them. Supabase migrations are handled by the Supabase CLI, not by these helper
scripts.

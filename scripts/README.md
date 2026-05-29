# Scripts

Windows batch helpers for local development. Run them from the repository root.

```bat
scripts\run-cli.cmd doctor --output json
scripts\run-api.cmd --reload
scripts\check-all.cmd --api
scripts\rebuild-sphinx-docs.cmd
scripts\clean-caches.cmd --dry-run
scripts\clean-caches.cmd --apply
```

Project commands use `.venv\Scripts\python.exe` directly to avoid editable-build
cache permission failures from `uv run`. The Sphinx script may use
`uv run --no-project --with ...` when Sphinx is not installed in `.venv`; it
builds in `%TEMP%` first and then copies HTML into `docs\sphinx\_build`.

"""RepositoryのSupabase migrationを再現可能に適用する。"""

from __future__ import annotations

import os
from pathlib import Path

import psycopg


def main() -> None:
    """Apply each migration once using Supabase's canonical migration history."""
    dsn = os.environ["WEREWOLF_SUPABASE_DB_DSN"]
    root = Path(__file__).resolve().parents[1]
    migrations = sorted((root / "supabase" / "migrations").glob("*.sql"))
    with psycopg.connect(dsn) as connection:
        applied = {
            str(row[0])
            for row in connection.execute(
                "select version from supabase_migrations.schema_migrations"
            ).fetchall()
        }
        for migration in migrations:
            version, name = _migration_identity(migration)
            if version in applied:
                continue
            with connection.transaction():
                sql = migration.read_text(encoding="utf-8")
                connection.execute(sql)
                connection.execute(
                    """
                    insert into supabase_migrations.schema_migrations (
                      version, statements, name
                    )
                    values (%s, %s, %s)
                    """,
                    (version, [sql], name),
                )


def _migration_identity(path: Path) -> tuple[str, str]:
    """Return the Supabase version and descriptive name from one migration path."""
    version, separator, name = path.stem.partition("_")
    if not separator or not version.isdigit() or not name:
        raise ValueError(f"Invalid Supabase migration file name: {path.name}")
    return version, name


if __name__ == "__main__":
    main()

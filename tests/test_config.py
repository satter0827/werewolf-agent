from pathlib import Path

from werewolf_agent.config import AppSettings, repository_root, split_csv


def test_split_csv_removes_empty_items_and_whitespace() -> None:
    assert split_csv("localhost, 127.0.0.1,, testserver ") == [
        "localhost",
        "127.0.0.1",
        "testserver",
    ]


def test_django_settings_derive_lists_and_paths() -> None:
    settings = AppSettings(
        _env_file=None,
        django_allowed_hosts="localhost,127.0.0.1",
        django_csrf_trusted_origins="http://localhost:8000,https://example.test",
        django_sqlite_path=Path("tmp/test.sqlite3"),
    )

    assert settings.django_allowed_hosts_list == ["localhost", "127.0.0.1"]
    assert settings.django_csrf_trusted_origins_list == [
        "http://localhost:8000",
        "https://example.test",
    ]
    assert settings.django_sqlite_database == repository_root() / "tmp/test.sqlite3"

from pathlib import Path

from scripts._infra.process import CommandResult
from scripts.agents import ui

LOCAL_DATABASE_DSN = (
    "postgresql://postgres:local@127.0.0.1:54322/postgres"  # pragma: allowlist secret
)


def _environment() -> dict[str, str]:
    return {
        "WEREWOLF_SUPABASE_DB_DSN": LOCAL_DATABASE_DSN,
        "WEREWOLF_SUPABASE_PUBLISHABLE_KEY": "local-public-key",
        "WEREWOLF_SUPABASE_URL": "http://127.0.0.1:54321",
    }


def test_local_ui_compose_environment_hard_locks_local_provider(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("WEREWOLF_LOCAL_LLM_BASE_URL", "http://127.0.0.1:1234/v1")
    monkeypatch.setenv("WEREWOLF_LOCAL_LLM_MODEL", "local-model")

    environment = ui._compose_environment(
        _environment(),
        tmp_path,
        "review@example.test",
        "local-password",
    )

    assert environment["PLAYWRIGHT_LOCAL_LLM"] == "1"
    assert environment["OPENAI_API_KEY"] == ""
    assert environment["WEREWOLF_WORKER_PAID_LLM_PROVIDER"] == "lmstudio"
    assert environment["WEREWOLF_WORKER_PAID_LLM_MODEL"] == "local-model"
    assert environment["WEREWOLF_WORKER_PAID_LLM_BASE_URL"] == (
        "http://host.docker.internal:1234/v1"
    )
    assert environment["COMPOSE_PROJECT_NAME"] == "werewolf-agent-local-ui"
    assert environment["PLAYWRIGHT_OUTPUT_DIR"] == "/tmp/werewolf-agent/playwright"


def test_local_ui_uses_environment_prepared_images(tmp_path: Path) -> None:
    commands = ui._commands(tmp_path)

    assert commands[0][-4:] == ("migrate", "api", "worker", "streamlit")
    assert "--no-build" in commands[0]
    assert commands[1][-1] == "scripts/browser/scenarios/test_local_llm.py"
    assert "pytest" in commands[1]


def test_local_ui_restores_container_artifact_ownership(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Local UIも成果物を読む前にhost利用者へ所有権を戻す。"""
    (tmp_path / "private").mkdir()
    calls: list[Path] = []
    monkeypatch.setattr(ui, "_create_review_user", lambda _environment: ("user", "password"))
    monkeypatch.setattr(
        ui,
        "_compose_environment",
        lambda environment, _run_dir, _email, _password: environment,
    )
    monkeypatch.setattr(ui, "_commands", lambda _run_dir: ())
    monkeypatch.setattr(ui, "_compose_down", lambda _environment, _transcript: 0)
    monkeypatch.setattr(
        ui,
        "restore_container_artifact_ownership",
        lambda path, **_kwargs: (calls.append(path) or CommandResult([], 0, 0.0, "")),
    )

    state, _report = ui._execute_local_ui(tmp_path, _environment())

    assert state == "error"
    assert calls == [tmp_path]


def test_local_ui_result_rejects_fake_or_openai_trace() -> None:
    metrics: dict[str, object] = {
        "game_status": "completed",
        "winner": "village",
        "invocations": 10,
        "providers": ["fake", "lmstudio"],
        "models": ["local-model"],
        "fallbacks": 0,
        "provider_errors": 0,
    }

    assert ui._state_from_metrics(metrics, expected_model="local-model") == "failed"


def test_local_ui_result_marks_fallback_completion_degraded() -> None:
    metrics: dict[str, object] = {
        "game_status": "completed",
        "winner": "village",
        "invocations": 10,
        "providers": ["lmstudio"],
        "models": ["local-model"],
        "fallbacks": 1,
        "provider_errors": 0,
    }

    assert ui._state_from_metrics(metrics, expected_model="local-model") == "degraded"


def test_local_ui_result_rejects_unexpected_model() -> None:
    metrics: dict[str, object] = {
        "game_status": "completed",
        "winner": "village",
        "invocations": 10,
        "providers": ["lmstudio"],
        "models": ["different-model"],
        "fallbacks": 0,
        "provider_errors": 0,
    }

    assert ui._state_from_metrics(metrics, expected_model="local-model") == "failed"


def test_local_ui_evidence_requires_api_dom_trace_and_browser_records(tmp_path: Path) -> None:
    (tmp_path / "public" / "screenshots").mkdir(parents=True)

    issues = ui._ui_evidence_issues(tmp_path, {"api_status": "running", "dom_status": "running"})

    assert any("API" in issue for issue in issues)
    assert any("DOM" in issue for issue in issues)
    assert any("trace" in issue for issue in issues)
    assert any("API state" in issue for issue in issues)
    assert any("API timeline" in issue for issue in issues)


def test_local_ui_evidence_reports_malformed_browser_records(tmp_path: Path) -> None:
    public = tmp_path / "public"
    (public / "screenshots").mkdir(parents=True)
    (public / "network.json").write_text("{}", encoding="utf-8")
    (public / "console.json").write_text("not-json", encoding="utf-8")

    issues = ui._ui_evidence_issues(
        tmp_path,
        {"api_status": "completed", "dom_status": "completed"},
    )

    assert any("object配列" in issue for issue in issues)
    assert any("console.jsonを読めません" in issue for issue in issues)


def test_local_ui_evidence_compares_public_timeline_sequence(tmp_path: Path) -> None:
    public = tmp_path / "public"
    screenshots = public / "screenshots"
    screenshots.mkdir(parents=True)
    for name in ui.REQUIRED_UI_SCREENSHOTS:
        (screenshots / name).write_bytes(b"png")
    (public / "network.json").write_text("[]", encoding="utf-8")
    (public / "console.json").write_text("[]", encoding="utf-8")
    (tmp_path / "private").mkdir()
    (tmp_path / "private" / "playwright").mkdir()
    (tmp_path / "private" / "playwright" / "trace.zip").write_bytes(b"zip")

    issues = ui._ui_evidence_issues(
        tmp_path,
        {
            "api_status": "completed",
            "dom_status": "completed",
            "api_state": {"state": {"status": "completed"}},
            "api_timeline": {"items": [{"sequence": 21}]},
        },
        metrics={"public_last_sequence": 21},
    )

    assert issues == []


def test_local_ui_redacts_public_browser_records(tmp_path: Path) -> None:
    public = tmp_path / "public"
    public.mkdir()
    (public / "network.json").write_text(
        '[{"url":"https://example.test/?access_token=secret-value"}]',
        encoding="utf-8",
    )
    (public / "console.json").write_text(
        '[{"type":"log","text":"Authorization: Bearer secret-value"}]',
        encoding="utf-8",
    )

    ui._sanitize_public_browser_records(tmp_path)

    content = (public / "network.json").read_text(encoding="utf-8") + (
        public / "console.json"
    ).read_text(encoding="utf-8")
    assert "secret-value" not in content

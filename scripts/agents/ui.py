"""Local LLMだけを使う明示的なStreamlit統合確認。"""

from __future__ import annotations

import json
import os
import secrets
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx
from dotenv import dotenv_values

from scripts._infra.artifacts import LAYOUT, REPOSITORY_ROOT
from scripts._infra.process import (
    EnvironmentBlockedError,
    redact,
    run_command,
)
from scripts.agents.review import (
    ReviewState,
    _finalize_review_run,
    _write_manifest,
    local_settings,
    preflight,
    validate_loopback_base_url,
)
from scripts.browser.e2e import create_contact_sheet, restore_container_artifact_ownership
from scripts.supabase.preflight import (
    SupabaseOperationError,
    SupabasePreflight,
    prepare_supabase,
    stop_supabase,
)

LOCAL_UI_PROJECT = "werewolf-agent-local-ui"
LOCAL_UI_TIMEOUT_SECONDS = 3600
REQUIRED_UI_SCREENSHOTS = frozenset(
    {
        "streamlit-created.png",
        "streamlit-error.png",
        "streamlit-progress.png",
        "streamlit-finished.png",
    }
)


def run_local_ui() -> tuple[ReviewState, Path]:
    """Local modelで一局を完走し、Streamlitの証拠を保存する。"""
    run_dir = _new_run_dir()
    environment = _runtime_environment()
    prepared: SupabasePreflight | None = None
    try:
        _validate_environment(environment)
        preflight_state, preflight_evidence = preflight()
        if preflight_state != "passed":
            outcome = _finish_without_compose(
                run_dir,
                "blocked" if preflight_state == "blocked" else "failed",
                {"preflight": preflight_evidence},
            )
        else:
            prepared = prepare_supabase(
                timeout_seconds=180,
                isolated_root=LAYOUT.runtime / "agents-local-ui" / run_dir.name,
                base_environment=environment,
            )
            environment.update(prepared.environment)
            _write_json(
                run_dir / "private" / "infrastructure.json",
                {
                    "supabase": {
                        "isolated": prepared.workdir is not None,
                        "started_by_process": prepared.started_by_process,
                        "project_id": prepared.project_id,
                    }
                },
            )
            outcome = _execute_local_ui(run_dir, environment)
    except (EnvironmentBlockedError, httpx.HTTPError, OSError) as exc:
        outcome = _finish_without_compose(
            run_dir,
            "blocked",
            {"error_type": type(exc).__name__, "message": str(exc)},
        )
    except Exception as exc:
        outcome = _finish_without_compose(
            run_dir,
            "error",
            {"error_type": type(exc).__name__, "message": str(exc)},
        )
    finally:
        if prepared is not None:
            try:
                stop_supabase(prepared, base_environment=environment)
                _write_json(run_dir / "private" / "cleanup.json", {"supabase": "stopped"})
            except (EnvironmentBlockedError, SupabaseOperationError, OSError) as exc:
                _write_json(
                    run_dir / "private" / "cleanup.json",
                    {
                        "supabase": "failed",
                        "error_type": type(exc).__name__,
                        "message": str(exc),
                    },
                )
        _finalize_review_run(run_dir)
    return outcome


def _execute_local_ui(run_dir: Path, environment: dict[str, str]) -> tuple[ReviewState, Path]:
    """準備済みのLocal Supabaseで画面統合を実行する。"""
    email, password = _create_review_user(environment)
    compose_environment = _compose_environment(environment, run_dir, email, password)
    transcript: list[str] = []
    execution_returncode = 0
    _compose_down(compose_environment, transcript)
    try:
        for command in _commands(run_dir):
            result = run_command(
                command,
                timeout_seconds=LOCAL_UI_TIMEOUT_SECONDS,
                environment=compose_environment,
            )
            transcript.append(result.output)
            if result.returncode != 0:
                execution_returncode = result.returncode
                break
    finally:
        ownership = restore_container_artifact_ownership(
            run_dir,
            environment=compose_environment,
        )
        transcript.append(ownership.output)
        execution_returncode = execution_returncode or ownership.returncode
        if execution_returncode != 0:
            try:
                _write_json(
                    run_dir / "private" / "failure-diagnostics.json",
                    _failure_database_diagnostics(environment["WEREWOLF_SUPABASE_DB_DSN"]),
                )
            except (KeyError, OSError, RuntimeError, ValueError) as exc:
                _write_json(
                    run_dir / "private" / "failure-diagnostics.json",
                    {"collection_error": type(exc).__name__, "message": str(exc)},
                )
            diagnostics = run_command(
                ["docker", "compose", "--profile", "e2e", "logs", "--no-color"],
                timeout_seconds=60,
                environment=compose_environment,
            )
            transcript.append(diagnostics.output)
        cleanup = _compose_down(compose_environment, transcript)
        execution_returncode = execution_returncode or cleanup
    (run_dir / "private" / "compose.log").write_text(redact("".join(transcript)), encoding="utf-8")
    if execution_returncode != 0:
        return _finish_without_compose(
            run_dir,
            "failed",
            {"message": "Local UI Playwright execution failed."},
        )
    result_path = run_dir / "public" / "local-ui-result.json"
    if not result_path.is_file():
        return _finish_without_compose(
            run_dir,
            "error",
            {"message": "Playwright did not record the completed game id."},
        )
    try:
        ui_result = json.loads(result_path.read_text(encoding="utf-8"))
        if not isinstance(ui_result, dict) or not str(ui_result.get("game_id") or "").strip():
            raise ValueError("Local UI result must contain game_id.")
        game_id = str(ui_result["game_id"])
        metrics = _database_metrics(environment["WEREWOLF_SUPABASE_DB_DSN"], game_id)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        return _finish_without_compose(
            run_dir,
            "failed",
            {"message": "Local UI evidence contract is invalid.", "detail": str(exc)},
        )
    expected_model = local_settings()[1]
    evidence_issues = _ui_evidence_issues(run_dir, ui_result, metrics=metrics)
    _sanitize_public_browser_records(run_dir)
    state = _state_from_metrics(metrics, expected_model=expected_model)
    if evidence_issues:
        state = "failed"
        metrics["evidence_issues"] = evidence_issues
    _write_json(run_dir / "metrics.json", metrics)
    _write_json(
        run_dir / "report.json",
        {
            "run_id": run_dir.name,
            "state": state,
            "provider": "local",
            "adapter_provider": "lmstudio",
            "model": expected_model,
            "game_id": game_id,
            "interfaces": ["streamlit"],
        },
    )
    _write_jsonl(
        run_dir / "events.jsonl",
        [{"event": "local_ui.completed", "state": state, "game_id": game_id}],
    )
    (run_dir / "summary.md").write_text(
        _ui_summary(state, expected_model, metrics, evidence_issues),
        encoding="utf-8",
    )
    create_contact_sheet(run_dir / "public")
    return state, run_dir


def _runtime_environment() -> dict[str, str]:
    environment = dict(os.environ)
    env_path = REPOSITORY_ROOT / ".env"
    if env_path.is_file():
        for key, value in dotenv_values(env_path).items():
            if value is not None:
                environment.setdefault(key, value)
    return environment


def _validate_environment(environment: dict[str, str]) -> None:
    if shutil.which("docker") is None:
        raise EnvironmentBlockedError("Docker CLIが見つかりません。")
    base_url, model = local_settings()
    validate_loopback_base_url(base_url)
    if not model:
        raise EnvironmentBlockedError("WEREWOLF_LOCAL_LLM_MODELがありません。")


def _create_review_user(environment: dict[str, str]) -> tuple[str, str]:
    email = f"local-ui-{secrets.token_hex(8)}@example.test"
    password = f"Local-{secrets.token_urlsafe(18)}"
    base_url = environment["WEREWOLF_SUPABASE_URL"].rstrip("/")
    publishable_key = environment["WEREWOLF_SUPABASE_PUBLISHABLE_KEY"]
    with httpx.Client(timeout=15, trust_env=False) as client:
        response = client.post(
            f"{base_url}/auth/v1/signup",
            headers={"apikey": publishable_key, "Authorization": f"Bearer {publishable_key}"},
            json={"email": email, "password": password},
        )
        response.raise_for_status()
    return email, password


def _compose_environment(
    base: dict[str, str],
    run_dir: Path,
    email: str,
    password: str,
) -> dict[str, str]:
    environment = dict(base)
    supabase_url = base["WEREWOLF_SUPABASE_URL"]
    container_supabase_url = _replace_host(supabase_url, "host.docker.internal")
    container_dsn = _replace_host(base["WEREWOLF_SUPABASE_DB_DSN"], "host.docker.internal")
    local_base_url, model = local_settings()
    environment.update(
        {
            "ANONYMIZED_TELEMETRY": "false",
            "COMPOSE_PROJECT_NAME": LOCAL_UI_PROJECT,
            "DO_NOT_TRACK": "1",
            "LANGCHAIN_TRACING_V2": "false",
            "OPENAI_API_KEY": "",
            "OTEL_SDK_DISABLED": "true",
            "WEREWOLF_LOG_OUTPUT": "stdout",
            "PLAYWRIGHT_EXPECTED_INSTANCE_ID": f"local-ui-{secrets.token_hex(8)}",
            "PLAYWRIGHT_LOCAL_EMAIL": email,
            "PLAYWRIGHT_LOCAL_LLM": "1",
            "PLAYWRIGHT_LOCAL_PASSWORD": password,
            "PLAYWRIGHT_API_URL": "http://api:8000",
            "PLAYWRIGHT_OUTPUT_DIR": "/tmp/werewolf-agent/playwright",
            "PLAYWRIGHT_SCREENSHOT_DIR": "/tmp/werewolf-agent/playwright/public/screenshots",
            "PLAYWRIGHT_VISUAL_REGRESSION": "0",
            "PLAYWRIGHT_STREAMLIT_URL": "http://streamlit:8501",
            "PLAYWRIGHT_SUPABASE_PUBLISHABLE_KEY": base["WEREWOLF_SUPABASE_PUBLISHABLE_KEY"],
            "PLAYWRIGHT_SUPABASE_URL": container_supabase_url,
            "SUPABASE_TELEMETRY_DISABLED": "true",
            "WEREWOLF_ADVANCE_JOB_POLL_TIMEOUT_SECONDS": "1200",
            "WEREWOLF_API_INSTANCE_ID": "",
            "WEREWOLF_API_RATE_LIMIT_REQUESTS": "1000",
            "WEREWOLF_COMPOSE_MIGRATION_DB_DSN": container_dsn,
            "WEREWOLF_COMPOSE_API_DB_DSN": container_dsn,
            "WEREWOLF_COMPOSE_WORKER_DB_DSN": container_dsn,
            "WEREWOLF_LLM_MAX_TOKENS": "256",
            "WEREWOLF_LLM_TEMPERATURE": "0",
            "WEREWOLF_LLM_TIMEOUT_SECONDS": "120",
            "WEREWOLF_STREAMLIT_AUTO_ADVANCE_INTERVAL_SECONDS": "1",
            "WEREWOLF_SUPABASE_JWKS_URL": (
                f"{container_supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
            ),
            "WEREWOLF_SUPABASE_JWT_ISSUER": f"{supabase_url.rstrip('/')}/auth/v1",
            "WEREWOLF_SUPABASE_PUBLISHABLE_KEY": base["WEREWOLF_SUPABASE_PUBLISHABLE_KEY"],
            "WEREWOLF_SUPABASE_URL": container_supabase_url,
            "WEREWOLF_WORKER_PAID_LLM_BASE_URL": _replace_host(
                local_base_url, "host.docker.internal"
            ),
            "WEREWOLF_WORKER_PAID_LLM_MODEL": model,
            "WEREWOLF_WORKER_PAID_LLM_PROVIDER": "lmstudio",
        }
    )
    instance_id = environment["PLAYWRIGHT_EXPECTED_INSTANCE_ID"]
    environment["WEREWOLF_API_INSTANCE_ID"] = instance_id
    return environment


def _commands(run_dir: Path) -> tuple[tuple[str, ...], ...]:
    mount = f"{run_dir.resolve()}:/tmp/werewolf-agent/playwright"
    return (
        (
            "docker",
            "compose",
            "--profile",
            "e2e",
            "up",
            "-d",
            "--wait",
            "--no-build",
            "--pull",
            "never",
            "migrate",
            "api",
            "worker",
            "streamlit",
        ),
        (
            "docker",
            "compose",
            "--profile",
            "e2e",
            "run",
            "--rm",
            "--no-deps",
            "--pull",
            "never",
            "--volume",
            mount,
            "e2e",
            "python",
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "--browser",
            "chromium",
            "--tracing",
            "off",
            "--screenshot",
            "only-on-failure",
            "--output",
            "/tmp/werewolf-agent/playwright/private/playwright",
            "--junitxml",
            "/tmp/werewolf-agent/playwright/results.xml",
            "--json-report",
            "--json-report-file",
            "/tmp/werewolf-agent/playwright/results.json",
            "--html",
            "/tmp/werewolf-agent/playwright/html/index.html",
            "--self-contained-html",
            "scripts/browser/scenarios/test_local_llm.py",
        ),
    )


def _compose_down(environment: dict[str, str], transcript: list[str]) -> int:
    result = run_command(
        ["docker", "compose", "--profile", "e2e", "down", "--volumes", "--remove-orphans"],
        timeout_seconds=120,
        environment=environment,
    )
    transcript.append(result.output)
    return result.returncode


def _database_metrics(dsn: str, game_id: str) -> dict[str, object]:
    import psycopg

    with psycopg.connect(dsn) as connection, connection.cursor() as cursor:
        cursor.execute(
            "select status, winner from public.game_summaries where game_id = %s",
            (game_id,),
        )
        summary = cursor.fetchone()
        cursor.execute(
            """
            select count(*), array_agg(distinct provider), array_agg(distinct model),
                   count(*) filter (where fallback_used),
                   count(*) filter (where provider_error <> ''),
                   sum(input_tokens), sum(output_tokens), sum(total_tokens),
                   coalesce(sum(latency_ms), 0)
              from private.llm_traces
             where game_id = %s
            """,
            (game_id,),
        )
        trace = cursor.fetchone()
        cursor.execute(
            """
            select count(*), coalesce(max(sequence), 0)
              from public.game_public_turns
             where game_id = %s
            """,
            (game_id,),
        )
        public_events = cursor.fetchone()
    if summary is None or trace is None or public_events is None:
        raise ValueError("Local UI game evidence is missing from the database.")
    return {
        "game_status": summary[0],
        "winner": summary[1],
        "invocations": trace[0],
        "providers": sorted(trace[1] or []),
        "models": sorted(trace[2] or []),
        "fallbacks": trace[3],
        "provider_errors": trace[4],
        "input_tokens": trace[5],
        "output_tokens": trace[6],
        "total_tokens": trace[7],
        "latency_ms": float(trace[8]),
        "public_event_count": public_events[0],
        "public_last_sequence": public_events[1],
    }


def _failure_database_diagnostics(dsn: str) -> dict[str, object]:
    """画面統合失敗時にvolume削除前の進行状態と確定済みtraceを回収する."""
    import psycopg

    with psycopg.connect(dsn) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            select game_id, status, phase, day, version, seed, updated_at
              from public.games
             order by created_at desc
             limit 1
            """
        )
        game = cursor.fetchone()
        cursor.execute(
            """
            select request_id, operation_type, status, game_id, attempt_count,
                   started_at, completed_at, updated_at
              from public.game_operation_requests
             order by created_at
            """
        )
        operations = cursor.fetchall()
        cursor.execute(
            """
            select count(*), array_agg(distinct provider), array_agg(distinct model),
                   count(*) filter (where fallback_used),
                   count(*) filter (where provider_error <> ''),
                   sum(input_tokens), sum(output_tokens), sum(total_tokens),
                   coalesce(sum(latency_ms), 0)
              from private.llm_traces
            """
        )
        trace = cursor.fetchone()
    return {
        "collected_at": datetime.now(UTC).isoformat(),
        "latest_game": (
            {
                "game_id": str(game[0]),
                "status": game[1],
                "phase": game[2],
                "day": game[3],
                "version": game[4],
                "seed": game[5],
                "updated_at": game[6].isoformat(),
            }
            if game is not None
            else None
        ),
        "operations": [
            {
                "request_id": str(item[0]),
                "operation_type": item[1],
                "status": item[2],
                "game_id": str(item[3]) if item[3] is not None else None,
                "attempt_count": item[4],
                "started_at": item[5].isoformat() if item[5] is not None else None,
                "completed_at": item[6].isoformat() if item[6] is not None else None,
                "updated_at": item[7].isoformat() if item[7] is not None else None,
            }
            for item in operations
        ],
        "persisted_trace_metrics": {
            "invocations": trace[0] if trace is not None else 0,
            "providers": sorted(trace[1] or []) if trace is not None else [],
            "models": sorted(trace[2] or []) if trace is not None else [],
            "fallbacks": trace[3] if trace is not None else 0,
            "provider_errors": trace[4] if trace is not None else 0,
            "input_tokens": trace[5] if trace is not None else None,
            "output_tokens": trace[6] if trace is not None else None,
            "total_tokens": trace[7] if trace is not None else None,
            "latency_ms": float(trace[8]) if trace is not None else 0.0,
        },
    }


def _state_from_metrics(metrics: dict[str, object], *, expected_model: str) -> ReviewState:
    if metrics["game_status"] != "completed" or not metrics["winner"]:
        return "failed"
    if metrics["providers"] != ["lmstudio"] or _integer(metrics["invocations"]) < 1:
        return "failed"
    if metrics["models"] != [expected_model]:
        return "failed"
    if _integer(metrics["provider_errors"]) > 0:
        return "failed"
    if _integer(metrics["fallbacks"]):
        return "degraded"
    return "passed"


def _ui_evidence_issues(
    run_dir: Path,
    result: dict[str, object],
    *,
    metrics: dict[str, object] | None = None,
) -> list[str]:
    issues: list[str] = []
    if result.get("api_status") != "completed":
        issues.append("APIの終了状態を確認できません。")
    if result.get("dom_status") != "completed":
        issues.append("DOMの終了状態を確認できません。")
    api_state = result.get("api_state")
    state_value = api_state.get("state") if isinstance(api_state, dict) else None
    if not isinstance(state_value, dict) or state_value.get("status") != "completed":
        issues.append("最終API stateが終了状態ではありません。")
    api_timeline = result.get("api_timeline")
    timeline_items = api_timeline.get("items") if isinstance(api_timeline, dict) else None
    if not isinstance(timeline_items, list) or not timeline_items:
        issues.append("最終API timelineがありません。")
    elif metrics is not None:
        last = timeline_items[-1]
        last_sequence = last.get("sequence") if isinstance(last, dict) else None
        if last_sequence != metrics.get("public_last_sequence"):
            issues.append("API timelineとDBの最終公開sequenceが一致しません。")
    public = run_dir / "public"
    screenshots = public / "screenshots"
    actual_screenshots = {path.name for path in screenshots.glob("*.png")}
    for name in sorted(REQUIRED_UI_SCREENSHOTS - actual_screenshots):
        issues.append(f"必須screenshotがありません: {name}")
    network_path = public / "network.json"
    console_path = public / "console.json"
    if not network_path.is_file():
        issues.append("network.jsonがありません。")
    else:
        network = _json_object_list(network_path, issues)
        if any(":1234" in str(event.get("url", "")) for event in network):
            issues.append("browserからLocal LLM endpointへ直接通信しています。")
    if not console_path.is_file():
        issues.append("console.jsonがありません。")
    else:
        console = _json_object_list(console_path, issues)
        if any(event.get("type") == "error" for event in console):
            issues.append("browser console errorがあります。")
    if not any(path.name == "trace.zip" for path in run_dir.rglob("trace.zip")):
        issues.append("Playwright traceがありません。")
    return issues


def _json_object_list(path: Path, issues: list[str]) -> list[dict[str, object]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        issues.append(f"{path.name}を読めません: {type(exc).__name__}")
        return []
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        issues.append(f"{path.name}はobject配列ではありません。")
        return []
    return value


def _sanitize_public_browser_records(run_dir: Path) -> None:
    for name in ("network.json", "console.json"):
        path = run_dir / "public" / name
        if not path.is_file():
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        _write_json(path, _redacted_value(value))


def _redacted_value(value: object) -> object:
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, list):
        return [_redacted_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _redacted_value(item) for key, item in value.items()}
    return value


def _finish_without_compose(
    run_dir: Path,
    state: ReviewState,
    detail: dict[str, object],
) -> tuple[ReviewState, Path]:
    _write_json(
        run_dir / "report.json",
        {"run_id": run_dir.name, "state": state, **detail},
    )
    _write_jsonl(
        run_dir / "events.jsonl",
        [{"event": "local_ui.finished", "state": state, **detail}],
    )
    (run_dir / "summary.md").write_text(
        "# Local UI review\n\n"
        f"- state: `{state}`\n"
        f"- detail: `{redact(str(detail.get('message') or ''))}`\n",
        encoding="utf-8",
    )
    _write_manifest(run_dir)
    return state, run_dir


def _new_run_dir() -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    root = LAYOUT.reviews / "agents" / "ui-local" / stamp
    suffix = 1
    while root.exists():
        root = LAYOUT.reviews / "agents" / "ui-local" / f"{stamp}-{suffix}"
        suffix += 1
    (root / "public" / "screenshots").mkdir(parents=True)
    (root / "private").mkdir()
    (root / ".active").write_text("", encoding="utf-8")
    return root


def _replace_host(url: str, host: str) -> str:
    parsed = urlsplit(url)
    if parsed.hostname is None:
        raise ValueError(f"hostを含むURLを指定してください: {url}")
    userinfo = ""
    if parsed.username is not None:
        userinfo = parsed.username
        if parsed.password is not None:
            userinfo += f":{parsed.password}"
        userinfo += "@"
    port = f":{parsed.port}" if parsed.port is not None else ""
    return urlunsplit(
        (parsed.scheme, f"{userinfo}{host}{port}", parsed.path, parsed.query, parsed.fragment)
    )


def _write_json(path: Path, document: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(
            json.dumps(_redacted_value(record), ensure_ascii=False) + "\n" for record in records
        ),
        encoding="utf-8",
    )


def _ui_summary(
    state: ReviewState,
    model: str,
    metrics: dict[str, object],
    evidence_issues: list[str],
) -> str:
    lines = [
        "# Local UI review",
        "",
        f"- state: `{state}`",
        "- provider: `lmstudio`",
        f"- model: `{model}`",
        f"- game status: `{metrics.get('game_status')}`",
        f"- winner: `{metrics.get('winner')}`",
        f"- invocations: `{metrics.get('invocations')}`",
        f"- fallbacks/errors: `{metrics.get('fallbacks')}` / `{metrics.get('provider_errors')}`",
        f"- input/output/total tokens: `{metrics.get('input_tokens')}` / "
        f"`{metrics.get('output_tokens')}` / `{metrics.get('total_tokens')}`",
        f"- latency: `{metrics.get('latency_ms')}` ms",
    ]
    if evidence_issues:
        lines.extend(["", "## Evidence issues", ""])
        lines.extend(f"- {issue}" for issue in evidence_issues)
    return "\n".join(lines) + "\n"


def _integer(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float, str)):
        return int(value)
    return 0


__all__ = ["run_local_ui"]

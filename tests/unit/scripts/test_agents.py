import json
from dataclasses import replace
from pathlib import Path

import pytest
from scripts._infra.artifacts import ArtifactLayout
from scripts.agents import review


def test_local_review_rejects_non_loopback_endpoint() -> None:
    with pytest.raises(ValueError, match="loopback"):
        review.validate_loopback_base_url("https://example.com/v1")


def test_local_review_rejects_credentials_in_loopback_endpoint() -> None:
    with pytest.raises(ValueError, match="credentials"):
        review.validate_loopback_base_url("http://user:password@127.0.0.1:1234/v1")


def test_local_preflight_provider_error_is_blocked_before_bounded_stop() -> None:
    state = review._classify_scenario_state(
        stopped_for_preflight=True,
        has_traces=True,
        completed=False,
        fallbacks=1,
        provider_errors=1,
        provider="lmstudio",
    )

    assert state == "blocked"


def test_local_provider_uses_deterministic_review_limits(monkeypatch) -> None:
    monkeypatch.setenv("WEREWOLF_LOCAL_LLM_BASE_URL", "http://127.0.0.1:1234/v1")
    monkeypatch.setenv("WEREWOLF_LOCAL_LLM_MODEL", "local-model")

    config = review.provider_config("local")

    assert config.provider == "lmstudio"
    assert config.model == "local-model"
    assert config.temperature == 0
    assert config.max_tokens == 256
    assert config.timeout_seconds == 40


def test_openai_review_requires_explicit_paid_confirmation(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "paid-secret")

    with pytest.raises(ValueError, match="confirm-paid"):
        review.provider_config("openai")


def test_preflight_records_blocked_model_evidence(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(review, "LAYOUT", ArtifactLayout(tmp_path))
    config = replace(
        review.provider_config("fake"),
        provider="lmstudio",
        model="missing-model",
        base_url="http://127.0.0.1:1234/v1",
    )
    monkeypatch.setattr(review, "provider_config", lambda *_args, **_kwargs: config)

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"data": [{"id": "loaded-model"}]}

    class Client:
        def __init__(self, **_kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def get(self, _url: str) -> Response:
            return Response()

    monkeypatch.setattr(review.httpx, "Client", Client)

    state, evidence = review.preflight()

    run_dir = Path(str(evidence["artifacts"]))
    assert state == "blocked"
    assert (run_dir / "public" / "result.json").is_file()
    assert (run_dir / "manifest.json").is_file()
    assert (run_dir / "run.json").is_file()
    assert (run_dir / "metrics.json").is_file()
    assert (run_dir / "events.jsonl").is_file()
    assert (run_dir / "summary.md").is_file()


def test_local_run_blocks_before_game_when_model_is_not_loaded(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(review, "LAYOUT", ArtifactLayout(tmp_path))
    monkeypatch.setenv("WEREWOLF_LOCAL_LLM_BASE_URL", "http://127.0.0.1:1234/v1")
    monkeypatch.setenv("WEREWOLF_LOCAL_LLM_MODEL", "missing-model")
    monkeypatch.setattr(review, "_local_model_ids", lambda _config: ["loaded-model"])
    monkeypatch.setattr(
        review,
        "_run_preset",
        lambda *_args, **_kwargs: pytest.fail("game must not start"),
    )

    state, run_dir = review.run_suite("local", "smoke")

    run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert state == "blocked"
    assert run["state"] == "blocked"
    assert run["error"]["type"] == "AgentReviewBlockedError"


def test_local_standard_run_is_rejected_before_model_discovery(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(review, "LAYOUT", ArtifactLayout(tmp_path))
    monkeypatch.setattr(
        review,
        "_local_model_ids",
        lambda _config: pytest.fail("unbounded Local review must stop before discovery"),
    )

    state, run_dir = review.run_suite("local", "standard")

    run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert state == "error"
    assert run["error"]["type"] == "ValueError"
    assert "bounded smoke suite" in run["error"]["message"]


def test_fake_smoke_writes_reviewable_public_and_private_artifacts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(review, "LAYOUT", ArtifactLayout(tmp_path))

    state, run_dir = review.run_suite("fake", "smoke", seed=7)

    assert state in {"passed", "degraded"}
    run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    metrics = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
    public = json.loads((run_dir / "public" / "scenarios.json").read_text(encoding="utf-8"))
    private = json.loads((run_dir / "private" / "traces.json").read_text(encoding="utf-8"))
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    summary = (run_dir / "summary.md").read_text(encoding="utf-8")

    assert run["provider"] == "fake"
    assert run["deliberation_level"] == "standard"
    assert run["configuration_checksum"]
    assert metrics["completed_count"] == 1
    assert metrics["scenarios"][0]["preset_id"] == "standard_6"
    assert metrics["scenarios"][0]["deliberation_level"] == "standard"
    assert metrics["scenarios"][0]["finished_day"] >= 1
    assert public[0]["completed"] is True
    assert private["standard_6"]
    invocation_lines = (
        (run_dir / "private" / "invocations.jsonl").read_text(encoding="utf-8").splitlines()
    )
    progress = json.loads((run_dir / "progress.json").read_text(encoding="utf-8"))
    assert len(invocation_lines) == metrics["invocations"]
    assert progress["invocations"] == metrics["invocations"]
    assert progress["state"] == run["state"]
    assert progress["completed"] is True
    assert all("prompt_messages" not in scenario for scenario in public)
    assert "$player_name" not in json.dumps(public, ensure_ascii=False)
    assert {item["category"] for item in manifest["artifacts"]} >= {"evidence", "private"}
    assert all(item["mime_type"] for item in manifest["artifacts"])
    event_artifact = next(item for item in manifest["artifacts"] if item["path"] == "events.jsonl")
    assert event_artifact["mime_type"] == "application/x-ndjson"
    checkpoint = json.loads((run_dir / "checkpoint.json").read_text(encoding="utf-8"))
    assert checkpoint["state"] == run["state"]
    assert checkpoint["deliberation_level"] == "standard"
    assert checkpoint["finished_at"] == run["finished_at"]
    assert "input/output/total tokens" in summary
    assert "LLM latency" in summary


def test_trace_sink_persists_each_completed_invocation_immediately() -> None:
    recorded = []
    sink = review.InMemoryTraceSink(recorded.append)
    trace = object()

    sink.record_invocation(trace)  # type: ignore[arg-type]

    assert sink.records == [trace]
    assert recorded == [trace]


def test_standard_checkpoints_completed_presets_before_later_interruption(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(review, "LAYOUT", ArtifactLayout(tmp_path))
    monkeypatch.setattr(
        review,
        "build_setup_catalog",
        lambda _settings: type("Catalog", (), {"template_order": ("first", "second")})(),
    )
    monkeypatch.setattr(review, "get_settings", lambda: object())
    calls = 0

    def run_preset(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise KeyboardInterrupt
        return {
            "preset_id": "first",
            "state": "passed",
            "completed": True,
            "action_count": 1,
            "invocations": 1,
            "fallbacks": 0,
            "provider_errors": 0,
            "usage_unavailable": 0,
            "latency_ms": 1.0,
            "input_tokens": 1,
            "output_tokens": 1,
            "total_tokens": 2,
            "private_traces": [{"raw": "private"}],
        }

    monkeypatch.setattr(review, "_run_preset", run_preset)

    state, run_dir = review.run_suite("fake", "standard")

    checkpoint = json.loads((run_dir / "checkpoint.json").read_text(encoding="utf-8"))
    run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    metrics = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
    public = json.loads((run_dir / "public" / "scenarios.json").read_text(encoding="utf-8"))
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert state == "error"
    assert run["state"] == "error"
    assert checkpoint["state"] == "error"
    assert checkpoint["completed_presets"] == ["first"]
    assert metrics["completed_count"] == 1
    assert public[0]["preset_id"] == "first"
    assert any(item["path"] == "private/traces.json" for item in manifest["artifacts"])


def test_review_serializer_keeps_numeric_usage_but_redacts_credentials() -> None:
    document = review._safe_value(
        {
            "prompt_tokens": 123,
            "completion_tokens": 45,
            "api_key": "secret",
            "authorization": "Bearer secret",
        }
    )

    assert document["prompt_tokens"] == 123
    assert document["completion_tokens"] == 45
    assert document["api_key"] == "[REDACTED]"
    assert document["authorization"] == "[REDACTED]"


def test_gameplay_metrics_distinguish_explained_public_position_changes() -> None:
    metrics = review._gameplay_metrics(
        [
            {
                "player_id": "p1",
                "day": 1,
                "parsed_decision": {"type": "speech", "message": "p2を疑う"},
                "request_payload": {"focus_id": "p2"},
            },
            {
                "player_id": "p1",
                "day": 1,
                "parsed_decision": {
                    "type": "vote",
                    "target_id": "p3",
                    "reason": "公開情報で判断を更新した",
                },
                "request_payload": {},
            },
        ]
    )

    assert metrics["speech_vote_consistency_rate"] == 0.0
    assert metrics["changed_vote_count"] == 1
    assert metrics["changed_vote_reason_missing_count"] == 0


def test_standard_suite_can_select_explicit_presets(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(review, "_new_run_dir", lambda *_args: tmp_path)

    state, run_dir = review.run_suite(
        "fake",
        "standard",
        selected_presets=("standard_6",),
    )

    run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    scenarios = json.loads((run_dir / "public" / "scenarios.json").read_text(encoding="utf-8"))
    assert state == "passed"
    assert run["presets"] == ["standard_6"]
    assert [item["preset_id"] for item in scenarios] == ["standard_6"]


def test_compare_runs_records_execution_context(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline"
    candidate = tmp_path / "candidate"
    for root, provider, model in (
        (baseline, "fake", "fake-list-chat-model"),
        (candidate, "local", "local-model"),
    ):
        root.mkdir()
        (root / "run.json").write_text(
            json.dumps(
                {
                    "provider": provider,
                    "model": model,
                    "suite": "smoke",
                    "seed": 7,
                    "configuration_checksum": f"{provider}-checksum",
                }
            ),
            encoding="utf-8",
        )
        (root / "metrics.json").write_text(
            json.dumps(
                {
                    "scenarios": [{"preset_id": "standard_6"}],
                    "completed_count": 1,
                }
            ),
            encoding="utf-8",
        )

    comparison = review.compare_runs(baseline, candidate)

    assert comparison["context"]["same_scenarios"] is True
    assert comparison["context"]["baseline"]["provider"] == "fake"
    assert comparison["context"]["candidate"]["model"] == "local-model"

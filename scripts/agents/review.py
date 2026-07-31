"""実際のAgent moduleでゲームを完走し、分析用証拠を保存する。"""

from __future__ import annotations

import hashlib
import json
import os
import random
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx

from scripts._infra.artifacts import LAYOUT
from scripts._infra.operations import prune_review_runs
from scripts._infra.process import redact
from werewolf_agent.adapters.agents.game_driver import langchain_agent_factory
from werewolf_agent.adapters.application_bridge import (
    build_llm_definitions,
    build_setup_catalog,
)
from werewolf_agent.adapters.llm.configuration import LlmProviderConfig
from werewolf_agent.agents.models import (
    AgentAbilityContext,
    AgentGameContext,
    AgentScenario,
    DeliberationLevel,
    PlayerProfile,
)
from werewolf_agent.agents.tracing import LlmInvocationTrace
from werewolf_agent.application.domain_codec import domain_to_data
from werewolf_agent.application.rules import rule_definition_from_values
from werewolf_agent.application.setup_document import GameSetupDocument
from werewolf_agent.domain import EventVisibility, Game, GameSetup, Phase, Player, build_game_rules
from werewolf_agent.settings import get_settings
from werewolf_agent.setup import checksum_payload, generate_players, namespace_seed

ReviewState = Literal["passed", "degraded", "failed", "blocked", "error"]

LOCAL_BASE_URL_DEFAULT = "http://127.0.0.1:1234/v1"
LOCAL_MODEL_DEFAULT = "google/gemma-3-4b"
LOCAL_TIMEOUT_SECONDS = 40.0
LOCAL_MAX_TOKENS = 256
LOCAL_MAX_INVOCATIONS = 3
MAX_PHASES = 64
MAX_INVOCATIONS = 512
SMOKE_PRESETS = ("standard_6",)
SECRET_KEY_PARTS = (
    "api_key",
    "authorization",
    "credential",
    "password",
    "refresh_token",
    "access_token",
    "secret",
)


class InMemoryTraceSink:
    """1 runのLLM traceを順序どおり保持する。"""

    def __init__(self, on_record: Callable[[LlmInvocationTrace], None] | None = None) -> None:
        self.records: list[LlmInvocationTrace] = []
        self._on_record = on_record

    def record_invocation(self, trace: LlmInvocationTrace) -> None:
        """1回の呼び出しを保持する。"""
        self.records.append(trace)
        if self._on_record is not None:
            self._on_record(trace)


class AgentReviewBlockedError(RuntimeError):
    """実行条件不足によりAgent reviewを開始できないことを表す."""


def local_settings() -> tuple[str, str]:
    """明示設定または安全なloopback既定値を返す。"""
    return (
        os.environ.get("WEREWOLF_LOCAL_LLM_BASE_URL", LOCAL_BASE_URL_DEFAULT).rstrip("/"),
        os.environ.get("WEREWOLF_LOCAL_LLM_MODEL", LOCAL_MODEL_DEFAULT).strip(),
    )


def validate_loopback_base_url(base_url: str) -> None:
    """Local reviewから非loopback endpointへの接続を拒否する。"""
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {
        "127.0.0.1",
        "::1",
        "localhost",
    }:
        raise ValueError("Local LLM base URL must use an HTTP loopback address.")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Local LLM base URL must not contain credentials.")


def provider_config(provider: str, *, confirm_paid: bool = False) -> LlmProviderConfig:
    """review専用の決定的なprovider設定を返す。"""
    if provider == "fake":
        return LlmProviderConfig(
            provider="fake",
            model="fake-list-chat-model",
            base_url="",
            api_key="",
            timeout_seconds=12,
            max_retries=0,
            max_tokens=128,
            temperature=0,
        )
    if provider == "local":
        base_url, model = local_settings()
        validate_loopback_base_url(base_url)
        if not model:
            raise ValueError("WEREWOLF_LOCAL_LLM_MODEL is required.")
        return LlmProviderConfig(
            provider="lmstudio",
            model=model,
            base_url=base_url,
            api_key="lm-studio",
            timeout_seconds=LOCAL_TIMEOUT_SECONDS,
            max_retries=0,
            max_tokens=LOCAL_MAX_TOKENS,
            temperature=0,
        )
    if provider == "openai":
        if not confirm_paid:
            raise ValueError("OpenAI review requires --confirm-paid.")
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required for OpenAI review.")
        return LlmProviderConfig(
            provider="openai",
            model=os.environ.get("WEREWOLF_OPENAI_MODEL", "gpt-4.1-mini").strip(),
            base_url="",
            api_key=api_key,
            timeout_seconds=LOCAL_TIMEOUT_SECONDS,
            max_retries=0,
            max_tokens=LOCAL_MAX_TOKENS,
            temperature=0,
        )
    raise ValueError(f"Unsupported review provider: {provider}")


def preflight() -> tuple[ReviewState, dict[str, object]]:
    """Local model一覧と実Agent decisionを検証する。"""
    started = time.perf_counter()
    root = _new_preflight_dir()
    state: ReviewState
    evidence: dict[str, object]
    try:
        config = provider_config("local")
        model_ids = _local_model_ids(config)
        if config.model not in model_ids:
            state = "blocked"
            evidence = {
                "message": "Configured Local LLM model is not loaded.",
                "configured_model": config.model,
                "loaded_models": model_ids,
                "artifacts": str(root),
            }
            _write_preflight_artifacts(root, state, evidence)
            return state, evidence
        scenario = _run_preset(config, "standard_6", seed=7, invocation_limit=1)
        raw_traces = scenario.pop("private_traces")
        traces = raw_traces if isinstance(raw_traces, list) else []
        first_trace = traces[0] if traces else {}
        if not isinstance(first_trace, Mapping):
            first_trace = {}
        fallback_used = bool(first_trace.get("fallback_used"))
        provider_error = str(first_trace.get("provider_error") or "")
        state = (
            "failed"
            if not traces
            else "blocked"
            if provider_error
            else "degraded"
            if fallback_used
            else "passed"
            if first_trace.get("validation_status") == "valid"
            else "failed"
        )
        evidence = {
            "message": "Local LLM reached the production Agent decision pipeline.",
            "configured_model": config.model,
            "loaded_models": model_ids,
            "decision": first_trace.get("parsed_decision"),
            "validation_status": first_trace.get("validation_status"),
            "fallback_used": fallback_used,
            "provider_error": provider_error,
            "usage": {
                "input_tokens": first_trace.get("input_tokens"),
                "output_tokens": first_trace.get("output_tokens"),
                "total_tokens": first_trace.get("total_tokens"),
                "source": first_trace.get("usage_source"),
            },
            "duration_seconds": round(time.perf_counter() - started, 3),
            "artifacts": str(root),
        }
        _write_preflight_artifacts(root, state, evidence, trace=first_trace)
        return state, evidence
    except (httpx.HTTPError, OSError) as exc:
        state = "blocked"
        evidence = {"message": str(exc), "error_type": type(exc).__name__, "artifacts": str(root)}
    except Exception as exc:
        state = "error"
        evidence = {"message": str(exc), "error_type": type(exc).__name__, "artifacts": str(root)}
    _write_preflight_artifacts(root, state, evidence)
    return state, evidence


def _write_preflight_artifacts(
    root: Path,
    state: ReviewState,
    evidence: Mapping[str, object],
    *,
    trace: Mapping[str, object] | None = None,
) -> None:
    public_evidence = dict(evidence)
    if isinstance(public_evidence.get("message"), str):
        public_evidence["message"] = redact(str(public_evidence["message"]))
    usage = evidence.get("usage")
    usage_values = usage if isinstance(usage, Mapping) else {}
    metrics = {
        "invocations": 1 if trace else 0,
        "fallbacks": int(bool(evidence.get("fallback_used"))),
        "provider_errors": int(bool(evidence.get("provider_error"))),
        "input_tokens": usage_values.get("input_tokens"),
        "output_tokens": usage_values.get("output_tokens"),
        "total_tokens": usage_values.get("total_tokens"),
        "usage_source": usage_values.get("source", "unavailable"),
        "duration_seconds": evidence.get("duration_seconds"),
    }
    run_document = {
        "run_id": root.name,
        "provider": "local",
        "model": evidence.get("configured_model", local_settings()[1]),
        "suite": "preflight",
        "state": state,
    }
    _write_json(root / "report.json", run_document)
    _write_json(root / "metrics.json", metrics)
    _write_json(root / "public" / "result.json", {"state": state, **public_evidence})
    if trace is not None:
        _write_json(root / "private" / "trace.json", trace)
    _write_jsonl(
        root / "events.jsonl",
        [{"event": "preflight.completed", "state": state}],
    )
    (root / "summary.md").write_text(
        "# Agent preflight\n\n"
        f"- state: `{state}`\n"
        f"- model: `{run_document['model']}`\n"
        f"- invocations: `{metrics['invocations']}`\n"
        f"- fallbacks/errors: `{metrics['fallbacks']}` / `{metrics['provider_errors']}`\n"
        f"- input/output/total tokens: `{metrics['input_tokens']}` / "
        f"`{metrics['output_tokens']}` / `{metrics['total_tokens']}`\n",
        encoding="utf-8",
    )
    _finalize_review_run(root)


def run_suite(
    provider: str,
    suite: str,
    *,
    confirm_paid: bool = False,
    seed: int = 7,
    deliberation_level: str = "standard",
    selected_presets: Sequence[str] = (),
) -> tuple[ReviewState, Path]:
    """固定suiteを逐次実行し、review成果物を保存する。"""
    run_dir = _new_run_dir(provider, suite)
    started_at = datetime.now(UTC)
    events: list[dict[str, object]] = [
        {"event": "run.started", "started_at": started_at.isoformat()}
    ]
    scenarios: list[dict[str, object]] = []
    private_traces: dict[str, object] = {}
    config: LlmProviderConfig | None = None
    configuration_checksum = ""
    try:
        config = provider_config(provider, confirm_paid=confirm_paid)
        configuration_checksum = _configuration_checksum(config)
        if provider == "local":
            if suite != "smoke" or selected_presets:
                raise ValueError(
                    "Local LLM review supports only the bounded smoke suite; "
                    "use local-ui for an explicitly requested full game."
                )
            model_ids = _local_model_ids(config)
            if config.model not in model_ids:
                raise AgentReviewBlockedError(
                    f"Configured Local LLM model is not loaded: {config.model}"
                )
        setup_catalog = build_setup_catalog(get_settings())
        available_presets = setup_catalog.template_order
        if selected_presets:
            if suite != "standard":
                raise ValueError("--preset is available only for the standard suite.")
            unknown = sorted(set(selected_presets) - set(available_presets))
            if unknown:
                raise ValueError(f"Unknown setup presets: {', '.join(unknown)}")
            presets = tuple(sorted(set(selected_presets)))
        else:
            presets = SMOKE_PRESETS if suite == "smoke" else available_presets
        _write_checkpoint(
            run_dir,
            provider=provider,
            model=config.model,
            suite=suite,
            seed=seed,
            deliberation_level=deliberation_level,
            configuration_checksum=configuration_checksum,
            started_at=started_at,
            scenarios=scenarios,
            private_traces=private_traces,
            events=events,
        )
        for preset_id in presets:
            events.append({"event": "scenario.started", "preset_id": preset_id})
            _write_checkpoint(
                run_dir,
                provider=provider,
                model=config.model,
                suite=suite,
                seed=seed,
                deliberation_level=deliberation_level,
                configuration_checksum=configuration_checksum,
                started_at=started_at,
                scenarios=scenarios,
                private_traces=private_traces,
                events=events,
            )
            scenario_started = time.perf_counter()
            live_traces: list[dict[str, object]] = []

            def persist_invocation(
                trace: LlmInvocationTrace,
                *,
                current_preset: str = preset_id,
                current_traces: list[dict[str, object]] = live_traces,
                current_started: float = scenario_started,
            ) -> None:
                document = _trace_document(trace)
                current_traces.append(document)
                invocation = len(current_traces)
                _append_jsonl(
                    run_dir / "private" / "invocations.jsonl",
                    {
                        "preset_id": current_preset,
                        "invocation": invocation,
                        "trace": document,
                    },
                )
                progress = _invocation_progress(
                    current_preset,
                    current_traces,
                    duration_seconds=time.perf_counter() - current_started,
                )
                _write_json(run_dir / "progress.json", progress)
                events.append(
                    {
                        "event": "invocation.completed",
                        "preset_id": current_preset,
                        "invocation": invocation,
                        "phase": document.get("phase"),
                        "day": document.get("day"),
                        "validation_status": document.get("validation_status"),
                        "fallback_used": document.get("fallback_used"),
                        "latency_ms": document.get("latency_ms"),
                    }
                )
                _write_jsonl(run_dir / "events.jsonl", events)
                _write_manifest(run_dir)

            scenario = _run_preset(
                config,
                preset_id,
                seed=seed,
                deliberation_level=DeliberationLevel(deliberation_level),
                invocation_limit=(
                    LOCAL_MAX_INVOCATIONS if provider == "local" else MAX_INVOCATIONS
                ),
                trace_callback=persist_invocation,
            )
            traces = scenario.pop("private_traces")
            private_traces[preset_id] = traces
            scenario["duration_seconds"] = round(time.perf_counter() - scenario_started, 3)
            scenarios.append(scenario)
            _write_json(
                run_dir / "progress.json",
                {
                    **_invocation_progress(
                        preset_id,
                        live_traces,
                        duration_seconds=scenario["duration_seconds"],
                    ),
                    "state": scenario["state"],
                    "completed": scenario["completed"],
                },
            )
            events.append(
                {
                    "event": "scenario.completed",
                    "preset_id": preset_id,
                    "state": scenario["state"],
                    "duration_seconds": scenario["duration_seconds"],
                }
            )
            _write_checkpoint(
                run_dir,
                provider=provider,
                model=config.model,
                suite=suite,
                seed=seed,
                deliberation_level=deliberation_level,
                configuration_checksum=configuration_checksum,
                started_at=started_at,
                scenarios=scenarios,
                private_traces=private_traces,
                events=events,
            )
        state = _aggregate_state(scenarios)
        run_document = {
            "run_id": run_dir.name,
            "provider": provider,
            "adapter_provider": config.provider,
            "model": config.model,
            "suite": suite,
            "seed": seed,
            "deliberation_level": deliberation_level,
            "state": state,
            "configuration_checksum": configuration_checksum,
            "started_at": started_at.isoformat(),
            "finished_at": datetime.now(UTC).isoformat(),
            "limits": {
                "max_phases": MAX_PHASES,
                "max_invocations": (
                    LOCAL_MAX_INVOCATIONS if provider == "local" else MAX_INVOCATIONS
                ),
            },
            "presets": list(presets),
        }
        events.append(
            {"event": "run.completed", "state": state, "finished_at": run_document["finished_at"]}
        )
        _write_json(run_dir / "report.json", run_document)
        _write_json(run_dir / "metrics.json", _aggregate_metrics(scenarios))
        _write_json(run_dir / "public" / "scenarios.json", scenarios)
        _write_json(run_dir / "private" / "traces.json", private_traces)
        _write_jsonl(run_dir / "events.jsonl", events)
        (run_dir / "summary.md").write_text(
            _summary_markdown(run_document, scenarios), encoding="utf-8"
        )
        _write_checkpoint(
            run_dir,
            provider=provider,
            model=config.model,
            suite=suite,
            seed=seed,
            deliberation_level=deliberation_level,
            configuration_checksum=configuration_checksum,
            started_at=started_at,
            scenarios=scenarios,
            private_traces=private_traces,
            events=events,
            state=state,
            finished_at=str(run_document["finished_at"]),
        )
    except (httpx.HTTPError, AgentReviewBlockedError) as exc:
        state = "blocked"
        _write_failure(
            run_dir,
            provider,
            suite,
            state,
            exc,
            started_at,
            scenarios=scenarios,
            private_traces=private_traces,
            events=events,
            model=config.model if config is not None else "",
            configuration_checksum=configuration_checksum,
            seed=seed,
            deliberation_level=deliberation_level,
        )
    except (Exception, KeyboardInterrupt) as exc:
        state = "error"
        _write_failure(
            run_dir,
            provider,
            suite,
            state,
            exc,
            started_at,
            scenarios=scenarios,
            private_traces=private_traces,
            events=events,
            model=config.model if config is not None else "",
            configuration_checksum=configuration_checksum,
            seed=seed,
            deliberation_level=deliberation_level,
        )
    _finalize_review_run(run_dir)
    return state, run_dir


def _write_checkpoint(
    run_dir: Path,
    *,
    provider: str,
    model: str,
    suite: str,
    seed: int,
    deliberation_level: str,
    configuration_checksum: str,
    started_at: datetime,
    scenarios: Sequence[Mapping[str, object]],
    private_traces: Mapping[str, object],
    events: Sequence[Mapping[str, object]],
    state: str = "running",
    finished_at: str | None = None,
) -> None:
    """完了済みscenarioを中断から回収できるcheckpointとして保存する."""
    _write_json(
        run_dir / "checkpoint.json",
        {
            "provider": provider,
            "model": model,
            "suite": suite,
            "seed": seed,
            "deliberation_level": deliberation_level,
            "state": state,
            "configuration_checksum": configuration_checksum,
            "started_at": started_at.isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
            "finished_at": finished_at,
            "completed_presets": [str(item["preset_id"]) for item in scenarios],
        },
    )
    _write_json(run_dir / "metrics.json", _aggregate_metrics(scenarios))
    _write_json(run_dir / "public" / "scenarios.json", list(scenarios))
    _write_json(run_dir / "private" / "traces.json", private_traces)
    _write_jsonl(run_dir / "events.jsonl", events)
    _write_manifest(run_dir)


def compare_runs(baseline: Path, candidate: Path) -> dict[str, object]:
    """2 runの観測指標を同じfieldで比較する。"""
    baseline_run = _read_json(baseline / "report.json")
    candidate_run = _read_json(candidate / "report.json")
    baseline_metrics = _read_json(baseline / "metrics.json")
    candidate_metrics = _read_json(candidate / "metrics.json")
    keys = (
        "scenario_count",
        "completed_count",
        "degraded_count",
        "failed_count",
        "finished_day_total",
        "invocations",
        "fallbacks",
        "provider_errors",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "latency_ms",
        "duration_seconds",
    )
    comparison = {
        key: {
            "baseline": baseline_metrics.get(key),
            "candidate": candidate_metrics.get(key),
            "delta": _numeric_delta(baseline_metrics.get(key), candidate_metrics.get(key)),
        }
        for key in keys
    }
    return {
        "baseline": baseline.name,
        "candidate": candidate.name,
        "context": {
            "baseline": _comparison_context(baseline_run, baseline_metrics),
            "candidate": _comparison_context(candidate_run, candidate_metrics),
            "same_scenarios": _scenario_ids(baseline_metrics) == _scenario_ids(candidate_metrics),
        },
        "metrics": comparison,
    }


def write_comparison(baseline: Path, candidate: Path) -> tuple[Path, Path]:
    """比較JSONとMarkdownをcandidate runへ保存する。"""
    document = compare_runs(baseline, candidate)
    json_path = candidate / "compare.json"
    markdown_path = candidate / "compare.md"
    _write_json(json_path, document)
    context = document["context"]
    same_scenarios = context.get("same_scenarios") if isinstance(context, Mapping) else None
    lines = [
        "# Agent run comparison",
        "",
        f"- baseline: `{baseline.name}`",
        f"- candidate: `{candidate.name}`",
        f"- same scenarios: `{same_scenarios}`",
        "",
        "## Context",
        "",
    ]
    if isinstance(context, Mapping):
        for side in ("baseline", "candidate"):
            values = context.get(side)
            if isinstance(values, Mapping):
                lines.append(
                    f"- {side}: provider=`{values.get('provider')}`, "
                    f"model=`{values.get('model')}`, "
                    f"suite=`{values.get('suite')}`, seed=`{values.get('seed')}`, "
                    f"configuration=`{values.get('configuration_checksum')}`"
                )
    lines.extend(["", "## Metrics", ""])
    metrics = document["metrics"]
    if not isinstance(metrics, Mapping):
        raise ValueError("comparison metrics must be an object")
    for key, raw_values in metrics.items():
        if not isinstance(raw_values, Mapping):
            continue
        lines.append(
            f"- {key}: `{raw_values.get('baseline')}` → `{raw_values.get('candidate')}` "
            f"(delta: `{raw_values.get('delta')}`)"
        )
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _write_manifest(candidate)
    return json_path, markdown_path


def _comparison_context(
    run: Mapping[str, object], metrics: Mapping[str, object]
) -> dict[str, object]:
    return {
        key: run.get(key)
        for key in (
            "provider",
            "adapter_provider",
            "model",
            "suite",
            "seed",
            "deliberation_level",
            "configuration_checksum",
        )
    } | {"scenario_ids": _scenario_ids(metrics)}


def _scenario_ids(metrics: Mapping[str, object]) -> list[str]:
    scenarios = metrics.get("scenarios")
    if not isinstance(scenarios, list):
        return []
    return [
        str(item.get("preset_id"))
        for item in scenarios
        if isinstance(item, Mapping) and item.get("preset_id")
    ]


def resolve_run(value: str) -> Path:
    """run IDまたはpathを実在するrun directoryへ解決する。"""
    candidate = Path(value)
    if not candidate.is_dir():
        candidate = LAYOUT.reviews / "agents" / "runs" / value
    if not candidate.is_dir():
        raise FileNotFoundError(value)
    return candidate.resolve()


def _run_preset(
    config: LlmProviderConfig,
    preset_id: str,
    *,
    seed: int,
    deliberation_level: DeliberationLevel = DeliberationLevel.STANDARD,
    invocation_limit: int = MAX_INVOCATIONS,
    trace_callback: Callable[[LlmInvocationTrace], None] | None = None,
) -> dict[str, object]:
    settings = get_settings()
    setup_catalog = build_setup_catalog(settings)
    llm_definitions = build_llm_definitions(settings)
    setup = setup_catalog.require_document(preset_id)
    mechanics = setup.mechanics
    rule_definition = rule_definition_from_values(
        player_count=sum(mechanics.role_counts.values()),
        role_counts=mechanics.role_counts,
        rules=mechanics.rules.model_dump(mode="json"),
        roles={key: value.model_dump(mode="json") for key, value in mechanics.roles.items()},
        abilities={
            key: value.model_dump(mode="json") for key, value in mechanics.abilities.items()
        },
    )
    players = generate_players(
        setup.player_generation,
        player_count=sum(mechanics.role_counts.values()),
        seed=seed,
    )
    profiles = {
        player.player_id: PlayerProfile.model_validate(player.profile.to_mapping())
        for player in players
    }
    role_rng = random.Random(namespace_seed(seed, "role_assignment"))
    gameplay_rng = random.Random(namespace_seed(seed, "gameplay"))
    game = Game.create(
        GameSetup(
            players=tuple(Player(id=item.player_id, name=item.profile.name) for item in players)
        ),
        rules=build_game_rules(rule_definition),
        random=role_rng,
    )
    trace_sink = InMemoryTraceSink(trace_callback)
    contexts = _game_contexts(
        setup, game, setup_checksum=checksum_payload(setup.model_dump(mode="json"))
    )
    factory = langchain_agent_factory(
        config,
        definitions=llm_definitions,
        profiles=profiles,
        profile_ids_by_player={player_id: player_id for player_id in profiles},
        scenario=AgentScenario(name=setup.theme.name, premise=setup.theme.premise),
        game_contexts=contexts,
        trace_sink=trace_sink,
        deliberation_level=deliberation_level,
    )
    public_timeline = [
        domain_to_data(event)
        for event in game.creation_events
        if event.visibility is EventVisibility.PUBLIC
    ]
    phase_count = 0
    action_count = 0
    stopped_for_preflight = False
    while game.snapshot().phase is not Phase.FINISHED and phase_count < MAX_PHASES:
        for index, player in enumerate(tuple(game.snapshot().players.values())):
            if player.status.value != "alive":
                continue
            observation = game.view_for(player.id)
            while observation.available_actions:
                if len(trace_sink.records) >= invocation_limit:
                    stopped_for_preflight = invocation_limit < MAX_INVOCATIONS
                    break
                agent = factory.create(
                    player.id,
                    seed=seed + phase_count * 1009 + index * 131 + action_count,
                )
                action = agent.act(observation)
                emitted = game.submit(action)
                action_count += 1
                public_timeline.extend(
                    domain_to_data(event)
                    for event in emitted
                    if event.visibility is EventVisibility.PUBLIC
                )
                observation = game.view_for(player.id)
            if stopped_for_preflight:
                break
        if stopped_for_preflight:
            break
        emitted = game.advance(gameplay_rng)
        public_timeline.extend(
            domain_to_data(event) for event in emitted if event.visibility is EventVisibility.PUBLIC
        )
        phase_count += 1
        contexts = _game_contexts(
            setup,
            game,
            setup_checksum=checksum_payload(setup.model_dump(mode="json")),
        )
        factory = langchain_agent_factory(
            config,
            definitions=llm_definitions,
            profiles=profiles,
            profile_ids_by_player={player_id: player_id for player_id in profiles},
            scenario=AgentScenario(name=setup.theme.name, premise=setup.theme.premise),
            game_contexts=contexts,
            trace_sink=trace_sink,
            deliberation_level=deliberation_level,
        )
    snapshot = game.snapshot()
    traces = [_trace_document(trace) for trace in trace_sink.records]
    fallbacks = sum(bool(trace["fallback_used"]) for trace in traces)
    provider_errors = sum(bool(trace["provider_error"]) for trace in traces)
    input_tokens = _sum_available(trace["input_tokens"] for trace in traces)
    output_tokens = _sum_available(trace["output_tokens"] for trace in traces)
    total_tokens = _sum_available(trace["total_tokens"] for trace in traces)
    latency_ms = round(
        sum(_as_float(trace["latency_ms"]) for trace in traces),
        3,
    )
    prompt_characters = sum(_as_int(trace["prompt_characters"]) for trace in traces)
    response_characters = sum(_as_int(trace["response_characters"]) for trace in traces)
    completed = snapshot.phase is Phase.FINISHED
    state = _classify_scenario_state(
        stopped_for_preflight=stopped_for_preflight,
        has_traces=bool(traces),
        completed=completed,
        fallbacks=fallbacks,
        provider_errors=provider_errors,
        provider=config.provider,
    )
    return {
        "preset_id": preset_id,
        "seed": seed,
        "deliberation_level": deliberation_level.value,
        "state": state,
        "completed": completed,
        "phase_count": phase_count,
        "finished_day": snapshot.day,
        "winner": snapshot.winner_id,
        "action_count": action_count,
        "invocations": len(traces),
        "fallbacks": fallbacks,
        "provider_errors": provider_errors,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "usage_unavailable": sum(trace["usage_source"] == "unavailable" for trace in traces),
        "latency_ms": latency_ms,
        "prompt_characters": prompt_characters,
        "average_prompt_characters": round(prompt_characters / len(traces), 3) if traces else 0,
        "response_characters": response_characters,
        "gameplay_metrics": _gameplay_metrics(traces),
        "setup_checksum": checksum_payload(setup.model_dump(mode="json")),
        "mechanics_checksum": checksum_payload(mechanics.model_dump(mode="json")),
        "public_timeline": public_timeline,
        "private_traces": traces,
    }


def _classify_scenario_state(
    *,
    stopped_for_preflight: bool,
    has_traces: bool,
    completed: bool,
    fallbacks: int,
    provider_errors: int,
    provider: str,
) -> ReviewState:
    """Classify model availability before bounded-preflight completion."""
    if provider_errors and provider == "lmstudio":
        return "blocked"
    if stopped_for_preflight:
        return "passed" if has_traces and not fallbacks else "degraded"
    if not completed:
        return "failed"
    if fallbacks or provider_errors:
        return "degraded"
    return "passed"


def _gameplay_metrics(traces: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """Return descriptive gameplay observations without inventing pass/fail thresholds."""
    speeches: list[str] = []
    speech_focus: dict[tuple[str, int], str] = {}
    vote_pairs: list[tuple[str, int, str]] = []
    targets: list[str] = []
    profile_choices: dict[str, set[str]] = {}
    empty_focus = 0
    invalid_evidence = 0
    changed_votes = 0
    changed_vote_reason_missing = 0
    for trace in traces:
        decision_value = trace.get("parsed_decision")
        decision = decision_value if isinstance(decision_value, Mapping) else {}
        request_value = trace.get("request_payload")
        request = request_value if isinstance(request_value, Mapping) else {}
        error_value = trace.get("error_payload")
        error = error_value if isinstance(error_value, Mapping) else {}
        invalid_evidence += str(error.get("validation_detail") or "") == "evidence is not visible"
        action = str(decision.get("type") or "")
        player_id = str(trace.get("player_id") or "")
        day = _as_int(trace.get("day"))
        target_id = str(decision.get("target_id") or "")
        focus_id = str(request.get("focus_id") or "")
        profile_key = f"{request.get('risk_tolerance', '')}:{request.get('evidence_focus', '')}"
        if action == "speech":
            message = str(decision.get("message") or "").strip()
            if message:
                speeches.append(message)
            if focus_id:
                speech_focus[(player_id, day)] = focus_id
            else:
                empty_focus += 1
        if action == "vote" and target_id:
            vote_pairs.append((player_id, day, target_id))
            previous_focus = speech_focus.get((player_id, day))
            if previous_focus is not None and previous_focus != target_id:
                changed_votes += 1
                changed_vote_reason_missing += not str(decision.get("reason") or "").strip()
        if target_id:
            targets.append(target_id)
            profile_choices.setdefault(profile_key, set()).add(target_id)
    duplicate_count = len(speeches) - len(set(speeches))
    consistent_votes = sum(
        speech_focus.get((player_id, day)) == target_id
        for player_id, day, target_id in vote_pairs
        if (player_id, day) in speech_focus
    )
    comparable_votes = sum(
        (player_id, day) in speech_focus for player_id, day, _target_id in vote_pairs
    )
    fixed_target_rate = (
        max(targets.count(target) for target in set(targets)) / len(targets) if targets else 0.0
    )
    return {
        "speech_count": len(speeches),
        "speech_exact_duplicate_rate": round(duplicate_count / len(speeches), 4)
        if speeches
        else 0.0,
        "speech_empty_focus_count": empty_focus,
        "invalid_evidence_count": invalid_evidence,
        "speech_vote_comparable_count": comparable_votes,
        "speech_vote_consistency_rate": round(consistent_votes / comparable_votes, 4)
        if comparable_votes
        else None,
        "changed_vote_count": changed_votes,
        "changed_vote_reason_missing_count": changed_vote_reason_missing,
        "targeted_decision_count": len(targets),
        "fixed_target_rate": round(fixed_target_rate, 4),
        "profile_target_variety": {
            profile: len(values) for profile, values in sorted(profile_choices.items())
        },
    }


def _game_contexts(
    setup: GameSetupDocument,
    game: Game,
    *,
    setup_checksum: str,
) -> dict[str, AgentGameContext]:
    snapshot = game.snapshot()
    mechanics = setup.mechanics
    mechanics_checksum = checksum_payload(mechanics.model_dump(mode="json"))
    rules = mechanics.rules.model_dump(mode="json")
    contexts: dict[str, AgentGameContext] = {}
    for player in snapshot.players.values():
        if player.role is None:
            continue
        role = mechanics.roles[player.role]
        abilities = []
        for ability_id in role.abilities:
            ability = mechanics.abilities[ability_id]
            used = snapshot.ability_uses.get(player.id, {}).get(ability_id, 0)
            remaining = (
                max(0, ability.max_uses - used) if isinstance(ability.max_uses, int) else None
            )
            abilities.append(
                AgentAbilityContext(
                    id=ability_id,
                    name=setup.theme.ability_names[ability_id],
                    kind=ability.kind,
                    remaining_uses=remaining,
                )
            )
        identity_faction = role.identity_faction
        victory_team = role.victory_team
        contexts[player.id] = AgentGameContext(
            theme_id=setup.theme.id,
            theme_name=setup.theme.name,
            premise=setup.theme.premise,
            role_id=player.role,
            role_name=setup.theme.role_names[player.role],
            identity_faction=identity_faction,
            identity_faction_name=setup.theme.faction_names[identity_faction],
            victory_team=victory_team,
            victory_team_name=setup.theme.faction_names[victory_team],
            objective=setup.theme.role_objectives[player.role],
            abilities=tuple(abilities),
            relevant_rules={
                key: value for key, value in rules.items() if isinstance(value, (str, bool, int))
            },
            action_names=dict(setup.theme.action_names),
            phase_names=dict(setup.theme.phase_names),
            setup_checksum=setup_checksum,
            mechanics_checksum=mechanics_checksum,
        )
    return contexts


def _trace_document(trace: LlmInvocationTrace) -> dict[str, object]:
    document = _safe_value(asdict(trace))
    if not isinstance(document, dict):
        raise TypeError("trace serializer must return an object")
    return {str(key): value for key, value in document.items()}


def _safe_value(value: object, *, key: str = "") -> Any:
    if any(part in key.casefold() for part in SECRET_KEY_PARTS):
        return "[REDACTED]"
    if isinstance(value, Mapping):
        return {
            str(item_key): _safe_value(item, key=str(item_key)) for item_key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_safe_value(item) for item in value]
    return value


def _aggregate_state(scenarios: Sequence[Mapping[str, object]]) -> ReviewState:
    states = {str(scenario["state"]) for scenario in scenarios}
    if "error" in states:
        return "error"
    if "blocked" in states:
        return "blocked"
    if "failed" in states:
        return "failed"
    if "degraded" in states:
        return "degraded"
    return "passed"


def _aggregate_metrics(scenarios: Sequence[Mapping[str, object]]) -> dict[str, object]:
    numeric_keys = (
        "action_count",
        "invocations",
        "fallbacks",
        "provider_errors",
        "usage_unavailable",
        "prompt_characters",
        "response_characters",
    )
    metrics: dict[str, object] = {
        "scenario_count": len(scenarios),
        "completed_count": sum(bool(item["completed"]) for item in scenarios),
        "degraded_count": sum(item.get("state") == "degraded" for item in scenarios),
        "failed_count": sum(item.get("state") in {"failed", "error"} for item in scenarios),
        "finished_day_total": sum(_as_int(item.get("finished_day")) for item in scenarios),
        "scenarios": [
            {
                key: item.get(key)
                for key in (
                    "preset_id",
                    "seed",
                    "deliberation_level",
                    "state",
                    "completed",
                    "finished_day",
                    "winner",
                    "action_count",
                    "invocations",
                    "fallbacks",
                    "provider_errors",
                    "input_tokens",
                    "output_tokens",
                    "total_tokens",
                    "usage_unavailable",
                    "latency_ms",
                    "duration_seconds",
                )
            }
            for item in scenarios
        ],
    }
    for key in numeric_keys:
        metrics[key] = sum(_as_int(item.get(key)) for item in scenarios)
    for key in ("latency_ms", "duration_seconds"):
        metrics[key] = round(sum(_as_float(item.get(key)) for item in scenarios), 3)
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        values = [item[key] for item in scenarios]
        metrics[key] = (
            sum(int(value) for value in values if isinstance(value, int))
            if any(isinstance(value, int) for value in values)
            else None
        )
    return metrics


def _summary_markdown(
    run_document: Mapping[str, object],
    scenarios: Sequence[Mapping[str, object]],
) -> str:
    metrics = _aggregate_metrics(scenarios)
    lines = [
        "# Agent stability review",
        "",
        f"- state: `{run_document['state']}`",
        f"- provider: `{run_document['provider']}`",
        f"- model: `{run_document['model']}`",
        f"- suite: `{run_document['suite']}`",
        f"- scenarios: `{metrics['completed_count']}/{metrics['scenario_count']}` completed",
        f"- invocations: `{metrics['invocations']}`",
        f"- provider errors: `{metrics['provider_errors']}`",
        f"- input/output/total tokens: `{metrics['input_tokens']}` / "
        f"`{metrics['output_tokens']}` / `{metrics['total_tokens']}`",
        f"- LLM latency: `{metrics['latency_ms']}` ms",
        f"- scenario duration: `{metrics['duration_seconds']}` s",
        "",
        "## Scenarios",
        "",
    ]
    for scenario in scenarios:
        lines.append(
            f"- `{scenario.get('preset_id', 'unavailable')}`: "
            f"{scenario.get('state', 'unavailable')}, "
            f"day={scenario.get('finished_day', 'unavailable')}, "
            f"invocations={scenario.get('invocations', 'unavailable')}, "
            f"fallbacks={scenario.get('fallbacks', 'unavailable')}"
        )
    lines.extend(
        [
            "",
            "このreviewは完走性、契約適合、再現性、実行指標だけを記録します。",
            "面白さと発言内容の評価は行いません。",
            "",
        ]
    )
    return "\n".join(lines)


def _model_ids(document: object) -> list[str]:
    if not isinstance(document, Mapping) or not isinstance(document.get("data"), list):
        raise ValueError("Local LLM /models response is invalid.")
    return sorted(
        str(item["id"])
        for item in document["data"]
        if isinstance(item, Mapping) and str(item.get("id") or "").strip()
    )


def _local_model_ids(config: LlmProviderConfig) -> list[str]:
    with httpx.Client(timeout=10, trust_env=False) as client:
        response = client.get(f"{config.base_url}/models")
        response.raise_for_status()
        return _model_ids(response.json())


def _new_run_dir(provider: str, suite: str) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    base = LAYOUT.reviews / "agents" / "runs"
    run_dir = base / f"{stamp}-{provider}-{suite}"
    suffix = 1
    while run_dir.exists():
        run_dir = base / f"{stamp}-{provider}-{suite}-{suffix}"
        suffix += 1
    (run_dir / "public").mkdir(parents=True)
    (run_dir / "private").mkdir()
    (run_dir / ".active").write_text("", encoding="utf-8")
    return run_dir


def _new_preflight_dir() -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    root = LAYOUT.reviews / "agents" / "preflight" / stamp
    suffix = 1
    while root.exists():
        root = LAYOUT.reviews / "agents" / "preflight" / f"{stamp}-{suffix}"
        suffix += 1
    (root / "public").mkdir(parents=True)
    (root / "private").mkdir()
    (root / ".active").write_text("", encoding="utf-8")
    return root


def _write_failure(
    run_dir: Path,
    provider: str,
    suite: str,
    state: ReviewState,
    error: BaseException,
    started_at: datetime,
    *,
    scenarios: Sequence[Mapping[str, object]],
    private_traces: Mapping[str, object],
    events: list[dict[str, object]],
    model: str,
    configuration_checksum: str,
    seed: int,
    deliberation_level: str,
) -> None:
    error_document = {"type": type(error).__name__, "message": redact(str(error))}
    document = {
        "run_id": run_dir.name,
        "provider": provider,
        "model": model,
        "suite": suite,
        "seed": seed,
        "deliberation_level": deliberation_level,
        "state": state,
        "configuration_checksum": configuration_checksum,
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
        "error": error_document,
    }
    events.append({"event": "run.failed", **error_document, "finished_at": document["finished_at"]})
    _write_json(run_dir / "report.json", document)
    _write_json(run_dir / "metrics.json", _aggregate_metrics(scenarios))
    _write_json(run_dir / "public" / "scenarios.json", list(scenarios))
    _write_json(run_dir / "private" / "traces.json", private_traces)
    _write_jsonl(run_dir / "events.jsonl", events)
    summary = _summary_markdown(document, scenarios)
    summary += (
        f"\n## Error\n\n- type: `{type(error).__name__}`\n"
        f"- message: `{error_document['message']}`\n"
    )
    (run_dir / "summary.md").write_text(summary, encoding="utf-8")
    _write_checkpoint(
        run_dir,
        provider=provider,
        model=model,
        suite=suite,
        seed=seed,
        deliberation_level=deliberation_level,
        configuration_checksum=configuration_checksum,
        started_at=started_at,
        scenarios=scenarios,
        private_traces=private_traces,
        events=events,
        state=state,
        finished_at=str(document["finished_at"]),
    )


def _configuration_checksum(config: LlmProviderConfig) -> str:
    """秘密情報を除くprovider設定のchecksumを返す."""
    values = asdict(config)
    values.pop("api_key", None)
    return checksum_payload(values)


def _write_json(path: Path, document: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_safe_value(document), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, records: Sequence[Mapping[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(_safe_value(record), ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )


def _append_jsonl(path: Path, record: Mapping[str, object]) -> None:
    """中断後も回収できるよう1 recordを直ちに永続化する."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(_safe_value(record), ensure_ascii=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _invocation_progress(
    preset_id: str,
    traces: Sequence[Mapping[str, object]],
    *,
    duration_seconds: object,
) -> dict[str, object]:
    """完了済みLLM呼び出しだけから中断耐性のある進捗指標を作る."""
    latest = traces[-1] if traces else {}
    return {
        "preset_id": preset_id,
        "state": "running",
        "completed": False,
        "updated_at": datetime.now(UTC).isoformat(),
        "invocations": len(traces),
        "fallbacks": sum(bool(trace.get("fallback_used")) for trace in traces),
        "provider_errors": sum(bool(trace.get("provider_error")) for trace in traces),
        "input_tokens": _sum_available(trace.get("input_tokens") for trace in traces),
        "output_tokens": _sum_available(trace.get("output_tokens") for trace in traces),
        "total_tokens": _sum_available(trace.get("total_tokens") for trace in traces),
        "latency_ms": round(sum(_as_float(trace.get("latency_ms")) for trace in traces), 3),
        "duration_seconds": round(_as_float(duration_seconds), 3),
        "last_phase": latest.get("phase"),
        "last_day": latest.get("day"),
        "last_player_id": latest.get("player_id"),
        "last_validation_status": latest.get("validation_status"),
    }


def _write_manifest(run_dir: Path) -> None:
    artifacts = []
    for path in sorted(run_dir.rglob("*")):
        if not path.is_file() or path.name in {".active", "manifest.json"}:
            continue
        relative = path.relative_to(run_dir).as_posix()
        content = path.read_bytes()
        artifacts.append(
            {
                "path": relative,
                "producer": "scripts.agents",
                "category": "private" if relative.startswith("private/") else "evidence",
                "mime_type": _mime_type(path),
                "bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
                "retained": True,
            }
        )
    _write_json(
        run_dir / "manifest.json",
        {"run_id": run_dir.name, "artifacts": artifacts},
    )


def _finalize_review_run(run_dir: Path) -> None:
    _write_manifest(run_dir)
    (run_dir / ".active").unlink(missing_ok=True)
    prune_review_runs()


def _read_json(path: Path) -> dict[str, object]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"JSON object required: {path}")
    return document


def _mime_type(path: Path) -> str:
    return {
        ".html": "text/html",
        ".json": "application/json",
        ".jsonl": "application/x-ndjson",
        ".log": "text/plain",
        ".md": "text/markdown",
        ".png": "image/png",
        ".txt": "text/plain",
        ".zip": "application/zip",
    }.get(path.suffix.casefold(), "application/octet-stream")


def _numeric_delta(baseline: object, candidate: object) -> int | float | None:
    if isinstance(baseline, (int, float)) and isinstance(candidate, (int, float)):
        return candidate - baseline
    return None


def _sum_available(values: Iterable[object]) -> int | None:
    available = [value for value in values if isinstance(value, int)]
    return sum(available) if available else None


def _as_int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float, str)):
        return int(value)
    return 0


def _as_float(value: object) -> float:
    if isinstance(value, (int, float, str)):
        return float(value)
    return 0.0


__all__ = [
    "InMemoryTraceSink",
    "compare_runs",
    "local_settings",
    "preflight",
    "provider_config",
    "resolve_run",
    "run_suite",
    "validate_loopback_base_url",
    "write_comparison",
]

"""実際のAgent moduleでゲームを完走し、分析用証拠を保存する。"""

from __future__ import annotations

import hashlib
import json
import os
import random
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx

from scripts._infra.artifacts import LAYOUT
from scripts._infra.operations import prune_review_runs
from scripts._infra.process import redact
from werewolf_agent.adapters.agents.game_context import SetupAgentMetadataProvider
from werewolf_agent.adapters.agents.game_driver import langchain_agent_factory
from werewolf_agent.adapters.application_bridge import (
    build_llm_definitions,
    build_setup_catalog,
)
from werewolf_agent.adapters.llm.configuration import LlmProviderConfig
from werewolf_agent.adapters.llm.langchain.constants import LLM_SPEECH_MESSAGE_MAX_CHARS
from werewolf_agent.adapters.llm.models import (
    DeliberationLevel,
    PlayerProfile,
)
from werewolf_agent.adapters.llm.tracing import LlmInvocationTrace
from werewolf_agent.agents import (
    AgentContext,
    AgentDecisionError,
    AgentFactory,
    AgentIdentity,
    AgentObservation,
    AgentProcedure,
    AgentWorld,
    DecisionOption,
    DecisionRequest,
    ObservedPlayer,
    PublicTimelineEvent,
)
from werewolf_agent.application.domain_codec import domain_to_data
from werewolf_agent.domain import EventVisibility, Game, GameSetup, Player, build_game_rules
from werewolf_agent.settings import get_settings
from werewolf_agent.setup import (
    checksum_payload,
    generate_players,
    namespace_seed,
    rule_definition_from_values,
)
from werewolf_agent.simulation import (
    PlayerController,
    SimulationLimits,
    SimulationRunner,
    SimulationSpec,
    SimulationStepKind,
)

ReviewState = Literal["passed", "degraded", "failed", "blocked", "error"]

LOCAL_BASE_URL_DEFAULT = "http://127.0.0.1:1234/v1"
LOCAL_MODEL_DEFAULT = "google/gemma-3-4b"
LOCAL_TIMEOUT_SECONDS = 240.0
LOCAL_MAX_TOKENS = 1024
LOCAL_MAX_INVOCATIONS = 3
FULL_GAME_MAX_INVOCATIONS = 128
FULL_GAME_MAX_DURATION_SECONDS = 5400.0
REVIEW_RESPONSE_REFERENCE_LIMIT = 2
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
            api_key="lm-studio",  # pragma: allowlist secret
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
    """Local model一覧と構造化議論の本番decision経路を検証する。"""
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
        probes, traces = _run_structured_discussion_probes(config)
        fallback_count = sum(bool(trace.get("fallback_used")) for trace in traces)
        provider_errors = [
            str(trace.get("provider_error")) for trace in traces if trace.get("provider_error")
        ]
        state = (
            "blocked"
            if provider_errors
            else "degraded"
            if fallback_count
            else "passed"
            if len(traces) == len(probes) == 3
            and all(bool(probe.get("passed")) for probe in probes)
            and all(trace.get("validation_status") == "valid" for trace in traces)
            else "failed"
        )
        usage = _probe_usage(traces)
        evidence = {
            "message": "Local LLMで構造化議論の開始、応答、投票を検証しました。",
            "configured_model": config.model,
            "loaded_models": model_ids,
            "probes": probes,
            "validation_status": "valid" if state == "passed" else state,
            "fallback_count": fallback_count,
            "provider_errors": provider_errors,
            "usage": usage,
            "duration_seconds": round(time.perf_counter() - started, 3),
            "artifacts": str(root),
        }
        _write_preflight_artifacts(root, state, evidence, traces=traces)
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
    traces: Sequence[Mapping[str, object]] = (),
) -> None:
    public_evidence = dict(evidence)
    if isinstance(public_evidence.get("message"), str):
        public_evidence["message"] = redact(str(public_evidence["message"]))
    usage = evidence.get("usage")
    usage_values = usage if isinstance(usage, Mapping) else {}
    provider_errors = evidence.get("provider_errors")
    provider_error_count = (
        len(provider_errors)
        if isinstance(provider_errors, Sequence) and not isinstance(provider_errors, str)
        else 0
    )
    metrics = {
        "invocations": len(traces),
        "fallbacks": evidence.get("fallback_count", 0),
        "provider_errors": provider_error_count,
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
    if traces:
        _write_json(root / "private" / "traces.json", list(traces))
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


def _run_structured_discussion_probes(
    config: LlmProviderConfig,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """開始、応答、投票を公開Agent契約から実providerへ一回ずつ送る。"""
    definitions = build_llm_definitions(get_settings())
    trace_sink = InMemoryTraceSink()
    profile = PlayerProfile(
        name="遥",
        age=28,
        gender="unspecified",
        personality="落ち着いて発言の矛盾を確認します。",
        speaking_style="短く明確に話します。",
        reasoning_style="公開情報と発言のつながりを重視します。",
        risk_tolerance="medium",
    )
    factory = langchain_agent_factory(
        config,
        definitions=definitions,
        profile=profile,
        trace_sink=trace_sink,
        deliberation_level=DeliberationLevel.STANDARD,
    )
    context = AgentContext("local-review", "local-review", "p1", 7)
    session = factory.create(context)
    probes: list[dict[str, object]] = []
    try:
        for probe_id, request in _structured_discussion_requests(context):
            try:
                response = session.decide(request)
                response_document = _safe_value(
                    {item.name: getattr(response, item.name) for item in fields(response)}
                )
                passed = _probe_response_is_legal(probe_id, response_document)
                probes.append(
                    {
                        "id": probe_id,
                        "passed": passed,
                        "response": response_document,
                    }
                )
            except AgentDecisionError as exc:
                probes.append(
                    {
                        "id": probe_id,
                        "passed": False,
                        "error": exc.code,
                        "diagnostics": _safe_value(exc.diagnostics),
                    }
                )
    finally:
        session.close()
    return probes, [_trace_document(trace) for trace in trace_sink.records]


def _structured_discussion_requests(
    context: AgentContext,
) -> tuple[tuple[str, DecisionRequest], ...]:
    players = (
        ObservedPlayer("p1", "遥", True),
        ObservedPlayer("p2", "結衣", True),
        ObservedPlayer("p3", "湊", True),
    )
    checksum = "1" * 64
    identity = AgentIdentity(
        role_id="villager",
        role_name="村人",
        identity_faction_id="village",
        identity_faction_name="村人陣営",
        victory_team_id="village",
        victory_team_name="村人陣営",
        objective="公開情報を基に人狼を見つけます。",
    )
    world = AgentWorld(
        theme_id="standard",
        theme_name="古い村",
        premise="村人の中に人狼が潜んでいます。",
        setup_checksum=checksum,
        mechanics_checksum=checksum,
        action_names={"speech": "発言", "vote": "投票"},
        phase_names={"day_discussion": "議論", "voting": "投票"},
    )

    def observation(phase: str, *, procedure_stage: str | None = None) -> AgentObservation:
        return AgentObservation(
            phase=phase,
            day=1,
            me=players[0],
            players=players,
            known_roles={"p1": "villager"},
            known_factions={"p1": "village"},
            identity=identity,
            world=world,
            procedure=AgentProcedure(
                procedure_id="structured_discussion",
                stage_id=procedure_stage or "",
                cycle=1,
                submission_mode="ordered" if procedure_stage == "response" else "sealed",
            )
            if procedure_stage is not None
            else None,
        )

    timeline = (
        PublicTimelineEvent(
            1,
            "speech",
            1,
            "p2",
            {
                "speech_id": "opening:p2",
                "message": "私はまだ判断材料が足りません。",
                "speech_act": "question",
                "subject_id": "p1",
            },
        ),
        PublicTimelineEvent(
            2,
            "speech",
            1,
            "p3",
            {
                "speech_id": "opening:p3",
                "message": "結衣の慎重さが気になります。",
                "speech_act": "challenge",
                "subject_id": "p1",
                "evidence_id": "opening:p2",
            },
        ),
    )
    opening = DecisionRequest(
        "probe-opening",
        context,
        observation("day_discussion", procedure_stage="opening"),
        (),
        (
            DecisionOption(
                "speech",
                legal_subject_ids=("p2", "p3"),
                message_max_chars=LLM_SPEECH_MESSAGE_MAX_CHARS,
            ),
        ),
        11,
    )
    response = DecisionRequest(
        "probe-response",
        context,
        observation("day_discussion", procedure_stage="response"),
        timeline,
        (
            DecisionOption(
                "speech",
                legal_subject_ids=("p2", "p3"),
                legal_evidence_ids=("opening:p2", "opening:p3"),
                legal_reference_ids=("opening:p2", "opening:p3"),
                message_max_chars=LLM_SPEECH_MESSAGE_MAX_CHARS,
            ),
        ),
        13,
    )
    vote = DecisionRequest(
        "probe-vote",
        context,
        observation("voting"),
        timeline,
        (
            DecisionOption(
                "vote",
                legal_target_ids=("p2", "p3"),
                legal_evidence_ids=("opening:p2", "opening:p3"),
            ),
        ),
        17,
    )
    return (("opening", opening), ("response", response), ("vote", vote))


def _probe_response_is_legal(probe_id: str, response: object) -> bool:
    if not isinstance(response, Mapping):
        return False
    if probe_id == "opening":
        return (
            response.get("action_type") == "speech"
            and bool(response.get("message"))
            and response.get("speech_act") == "question"
            and response.get("subject_id") in {"p2", "p3"}
            and response.get("response_to_id") is None
        )
    if probe_id == "response":
        return (
            response.get("action_type") == "speech"
            and bool(response.get("message"))
            and response.get("speech_act") in {"answer", "support", "challenge", "revise"}
            and response.get("subject_id") in {"p2", "p3"}
            and response.get("response_to_id") in {"opening:p2", "opening:p3"}
            and response.get("evidence_id") == response.get("response_to_id")
        )
    return (
        response.get("action_type") == "vote"
        and response.get("target_id") in {"p2", "p3"}
        and bool(response.get("reason"))
        and response.get("evidence_id") in {"opening:p2", "opening:p3"}
    )


def _probe_usage(traces: Sequence[Mapping[str, object]]) -> dict[str, object]:
    sources = {str(trace.get("usage_source")) for trace in traces}
    return {
        "input_tokens": _sum_available(trace.get("input_tokens") for trace in traces),
        "output_tokens": _sum_available(trace.get("output_tokens") for trace in traces),
        "total_tokens": _sum_available(trace.get("total_tokens") for trace in traces),
        "source": sources.pop() if len(sources) == 1 else "mixed",
    }


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
            if suite not in {"smoke", "full-game"} or selected_presets:
                raise ValueError("Local LLM review supports smoke or full-game without --preset.")
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
        elif suite in {"smoke", "full-game"}:
            presets = SMOKE_PRESETS
        else:
            presets = available_presets
        invocation_limit = (
            LOCAL_MAX_INVOCATIONS
            if provider == "local" and suite == "smoke"
            else FULL_GAME_MAX_INVOCATIONS
            if suite == "full-game"
            else MAX_INVOCATIONS
        )
        duration_limit_seconds = FULL_GAME_MAX_DURATION_SECONDS if suite == "full-game" else None
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
                invocation_limit=invocation_limit,
                duration_limit_seconds=duration_limit_seconds,
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
                "max_invocations": invocation_limit,
                "max_duration_seconds": duration_limit_seconds,
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
    duration_limit_seconds: float | None = None,
    trace_callback: Callable[[LlmInvocationTrace], None] | None = None,
) -> dict[str, object]:
    scenario_started = time.perf_counter()
    settings = get_settings()
    setup_catalog = build_setup_catalog(settings)
    llm_definitions = build_llm_definitions(settings)
    setup = setup_catalog.require_document(preset_id)
    mechanics = setup.mechanics
    rule_definition = rule_definition_from_values(
        player_count=sum(mechanics.role_counts.values()),
        role_counts=mechanics.role_counts,
        discussion=mechanics.discussion.to_mapping(),
        voting=mechanics.voting.to_mapping(),
        night=mechanics.night.to_mapping(),
        lifecycle=mechanics.lifecycle.to_mapping(),
        roles={key: value.to_mapping() for key, value in mechanics.roles.items()},
        abilities={key: value.to_mapping() for key, value in mechanics.abilities.items()},
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
    trace_sink = InMemoryTraceSink(trace_callback)
    setup_document = setup.to_mapping()
    setup_checksum = checksum_payload(setup_document)
    mechanics_checksum = checksum_payload(mechanics.to_mapping())
    factories: dict[str, AgentFactory] = {
        player_id: langchain_agent_factory(
            config,
            definitions=llm_definitions,
            profile=profile,
            trace_sink=trace_sink,
            deliberation_level=deliberation_level,
        )
        for player_id, profile in profiles.items()
    }
    player_setup = GameSetup(
        players=tuple(Player(id=item.player_id, name=item.profile.name) for item in players)
    )
    rules = build_game_rules(rule_definition)
    game = Game.create(
        player_setup,
        rules=rules,
        random=random.Random(namespace_seed(seed, "role_assignment")),
    )
    metadata_provider = SetupAgentMetadataProvider(
        setup=setup_document,
        snapshot=game.snapshot,
        setup_checksum=setup_checksum,
        mechanics_checksum=mechanics_checksum,
    )
    session = SimulationRunner().start(
        game,
        SimulationSpec(
            simulation_id=f"review:{seed}",
            game_id=f"review:{seed}",
            seed=seed,
            controllers={
                player_id: PlayerController(
                    player_id,
                    factory,
                    metadata_provider=metadata_provider,
                )
                for player_id, factory in factories.items()
            },
            limits=SimulationLimits(
                max_actions=MAX_INVOCATIONS,
                max_phases=MAX_PHASES,
                decision_timeout_seconds=config.timeout_seconds,
            ),
            speech_message_max_chars=LLM_SPEECH_MESSAGE_MAX_CHARS,
            response_reference_limit=REVIEW_RESPONSE_REFERENCE_LIMIT,
        ),
    )
    public_timeline = [
        domain_to_data(event)
        for event in game.creation_events
        if event.visibility is EventVisibility.PUBLIC
    ]
    phase_count = 0
    action_count = 0
    stopped_for_preflight = False
    stopped_for_duration = False
    try:
        while True:
            if (
                duration_limit_seconds is not None
                and time.perf_counter() - scenario_started >= duration_limit_seconds
            ):
                stopped_for_duration = True
                break
            if len(trace_sink.records) >= invocation_limit:
                stopped_for_preflight = invocation_limit < MAX_INVOCATIONS
                break
            step = session.step()
            public_timeline.extend(
                domain_to_data(event)
                for event in step.events
                if event.visibility is EventVisibility.PUBLIC
            )
            if step.kind is SimulationStepKind.AGENT_ACTION:
                action_count += 1
            elif step.kind is SimulationStepKind.PHASE_ADVANCED:
                phase_count += 1
            if step.stop_reason is not None:
                break
    finally:
        session.close()
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
    completed = snapshot.is_finished
    gameplay_metrics = _gameplay_metrics(traces, public_timeline)
    state = _classify_scenario_state(
        stopped_for_preflight=stopped_for_preflight,
        stopped_for_duration=stopped_for_duration,
        has_traces=bool(traces),
        completed=completed,
        fallbacks=fallbacks,
        provider_errors=provider_errors,
        provider=config.provider,
        integrity_failed=bool(gameplay_metrics["integrity_flags"]),
    )
    return {
        "preset_id": preset_id,
        "seed": seed,
        "deliberation_level": deliberation_level.value,
        "state": state,
        "completed": completed,
        "stopped_for_duration": stopped_for_duration,
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
        "phase_quality": _phase_quality_metrics(traces),
        "gameplay_metrics": gameplay_metrics,
        "setup_checksum": checksum_payload(setup.to_mapping()),
        "mechanics_checksum": checksum_payload(mechanics.to_mapping()),
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
    stopped_for_duration: bool = False,
    integrity_failed: bool = False,
) -> ReviewState:
    """Classify model availability before bounded-preflight completion."""
    if provider_errors and provider == "lmstudio":
        return "blocked"
    if stopped_for_duration:
        return "failed"
    if stopped_for_preflight:
        return "passed" if has_traces and not fallbacks else "degraded"
    if integrity_failed:
        return "failed"
    if not completed:
        return "failed"
    if fallbacks or provider_errors:
        return "degraded"
    return "passed"


def _gameplay_metrics(
    traces: Sequence[Mapping[str, object]],
    public_timeline: Sequence[Mapping[str, object]] = (),
) -> dict[str, object]:
    """一局の会話、根拠、投票、夜、終了整合を決定的に集計する。"""
    speeches: list[str] = []
    speech_subject: dict[tuple[str, int], str] = {}
    vote_pairs: list[tuple[str, int, str]] = []
    targets: list[str] = []
    subjects: list[str] = []
    speech_acts: dict[str, int] = {}
    profile_choices: dict[str, set[str]] = {}
    missing_subject = 0
    invalid_evidence = 0
    grounded_decisions = 0
    ungrounded_assertions = 0
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
        subject_id = str(decision.get("subject_id") or "")
        evidence_id = str(decision.get("evidence_id") or "")
        profile_key = f"{request.get('risk_tolerance', '')}:{request.get('evidence_focus', '')}"
        if action == "speech":
            message = str(decision.get("message") or "").strip()
            speech_act = str(decision.get("speech_act") or "")
            if message:
                speeches.append(message)
            if speech_act:
                speech_acts[speech_act] = speech_acts.get(speech_act, 0) + 1
            if subject_id:
                subjects.append(subject_id)
                speech_subject[(player_id, day)] = subject_id
            else:
                missing_subject += 1
            if evidence_id:
                grounded_decisions += 1
            elif speech_act and speech_act != "question":
                ungrounded_assertions += 1
        if action == "vote" and target_id:
            vote_pairs.append((player_id, day, target_id))
            if evidence_id:
                grounded_decisions += 1
            else:
                ungrounded_assertions += 1
            previous_subject = speech_subject.get((player_id, day))
            if previous_subject is not None and previous_subject != target_id:
                changed_votes += 1
                changed_vote_reason_missing += not str(decision.get("reason") or "").strip()
        if target_id:
            targets.append(target_id)
            profile_choices.setdefault(profile_key, set()).add(target_id)
    duplicate_count = len(speeches) - len(set(speeches))
    consistent_votes = sum(
        speech_subject.get((player_id, day)) == target_id
        for player_id, day, target_id in vote_pairs
        if (player_id, day) in speech_subject
    )
    comparable_votes = sum(
        (player_id, day) in speech_subject for player_id, day, _target_id in vote_pairs
    )
    fixed_target_rate = (
        max(targets.count(target) for target in set(targets)) / len(targets) if targets else 0.0
    )
    timeline_metrics = _timeline_gameplay_metrics(public_timeline)
    return {
        "speech_count": len(speeches),
        "speech_exact_duplicate_rate": round(duplicate_count / len(speeches), 4)
        if speeches
        else 0.0,
        "speech_missing_subject_count": missing_subject,
        "speech_act_counts": dict(sorted(speech_acts.items())),
        "subject_variety": len(set(subjects)),
        "invalid_evidence_count": invalid_evidence,
        "grounded_decision_count": grounded_decisions,
        "ungrounded_assertion_count": ungrounded_assertions,
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
        **timeline_metrics,
    }


def _timeline_gameplay_metrics(
    public_timeline: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """公開timelineだけから一局の参照整合と進行結果を検証する。"""
    speech_ids: set[str] = set()
    integrity_flags: list[str] = []
    response_count = 0
    response_alignment_count = 0
    vote_round_count = 0
    tied_vote_round_count = 0
    revote_count = 0
    elimination_count = 0
    night_round_count = 0
    night_kill_count = 0
    finished_count = 0
    winner = ""
    for event in public_timeline:
        event_type = str(event.get("event_type") or "")
        payload_value = event.get("payload")
        payload = payload_value if isinstance(payload_value, Mapping) else {}
        if event_type == "speech_recorded":
            speech_id = str(payload.get("speech_id") or "")
            evidence_id = str(payload.get("evidence_id") or "")
            response_to_id = str(payload.get("response_to_id") or "")
            if evidence_id and evidence_id not in speech_ids:
                integrity_flags.append(f"unknown_speech_evidence:{evidence_id}")
            if response_to_id:
                response_count += 1
                if evidence_id == response_to_id:
                    response_alignment_count += 1
                else:
                    integrity_flags.append(f"response_evidence_mismatch:{speech_id}")
            if speech_id:
                if speech_id in speech_ids:
                    integrity_flags.append(f"duplicate_speech_id:{speech_id}")
                speech_ids.add(speech_id)
        elif event_type == "vote_resolved":
            vote_round_count += 1
            tied = payload.get("tied_player_ids")
            if isinstance(tied, list) and len(tied) > 1:
                tied_vote_round_count += 1
            if bool(payload.get("requires_revote")):
                revote_count += 1
            if payload.get("eliminated_player_id"):
                elimination_count += 1
            evidence_value = payload.get("evidence_ids")
            evidence_ids = evidence_value if isinstance(evidence_value, Mapping) else {}
            for evidence_id in evidence_ids.values():
                normalized = str(evidence_id or "")
                if normalized and normalized not in speech_ids:
                    integrity_flags.append(f"unknown_vote_evidence:{normalized}")
        elif event_type == "night_resolved":
            night_round_count += 1
            killed = payload.get("killed_player_ids")
            if isinstance(killed, list):
                night_kill_count += len(killed)
            elif payload.get("killed_player_id"):
                night_kill_count += 1
        elif event_type == "game_finished":
            finished_count += 1
            winner = str(payload.get("winner") or "")
    if public_timeline and finished_count != 1:
        integrity_flags.append(f"game_finished_event_count:{finished_count}")
    if finished_count == 1 and winner not in {"village", "werewolf", "fox"}:
        integrity_flags.append(f"invalid_winner:{winner}")
    return {
        "public_speech_count": len(speech_ids),
        "response_count": response_count,
        "response_evidence_alignment_rate": (
            round(response_alignment_count / response_count, 4) if response_count else None
        ),
        "vote_round_count": vote_round_count,
        "tied_vote_round_count": tied_vote_round_count,
        "revote_count": revote_count,
        "elimination_count": elimination_count,
        "night_round_count": night_round_count,
        "night_kill_count": night_kill_count,
        "game_finished_event_count": finished_count,
        "public_winner": winner or None,
        "integrity_flags": sorted(set(integrity_flags)),
    }


def _phase_quality_metrics(
    traces: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """フェーズごとの応答時間、token、fallbackを集計する。"""
    result: dict[str, object] = {}
    phases = sorted({str(trace.get("phase") or "unknown") for trace in traces})
    for phase in phases:
        items = [trace for trace in traces if str(trace.get("phase") or "unknown") == phase]
        latencies = [_as_float(item.get("latency_ms")) for item in items]
        token_values = [
            _as_int(item["total_tokens"])
            for item in items
            if isinstance(item.get("total_tokens"), int)
        ]
        result[phase] = {
            "invocations": len(items),
            "fallbacks": sum(bool(item.get("fallback_used")) for item in items),
            "usage_unavailable": sum(item.get("usage_source") == "unavailable" for item in items),
            "latency_ms": _distribution(latencies),
            "total_tokens": _distribution(token_values),
        }
    return result


def _distribution(values: Sequence[int | float]) -> dict[str, int | float | None]:
    """小標本でも再現可能なnearest-rank分布を返す。"""
    ordered = sorted(values)
    if not ordered:
        return {"count": 0, "total": 0, "average": None, "p50": None, "p95": None, "max": None}

    def percentile(fraction: float) -> int | float:
        index = max(0, min(len(ordered) - 1, int(len(ordered) * fraction + 0.999999) - 1))
        return ordered[index]

    total = sum(ordered)
    return {
        "count": len(ordered),
        "total": round(total, 3),
        "average": round(total / len(ordered), 3),
        "p50": percentile(0.5),
        "p95": percentile(0.95),
        "max": ordered[-1],
    }


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
                    "phase_quality",
                    "gameplay_metrics",
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
        gameplay_value = scenario.get("gameplay_metrics")
        gameplay = gameplay_value if isinstance(gameplay_value, Mapping) else {}
        lines.append(
            f"  - speeches={gameplay.get('speech_count', 'unavailable')}, "
            f"responses={gameplay.get('response_count', 'unavailable')}, "
            f"vote rounds={gameplay.get('vote_round_count', 'unavailable')}, "
            f"night rounds={gameplay.get('night_round_count', 'unavailable')}, "
            f"integrity flags={gameplay.get('integrity_flags', [])}"
        )
    lines.extend(
        [
            "",
            "このreviewは完走性、契約適合、公開根拠の参照整合、会話の重複、",
            "投票・夜・勝敗とフェーズ別のtoken・応答時間を記録します。",
            "発言内容の事実性と面白さの最終判断は、公開timelineの人手レビューで補います。",
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

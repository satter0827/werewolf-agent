"""Agent adapterとSimulationのprepared transition接続を検証する."""

from __future__ import annotations

import random
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from werewolf_agent.adapters.agents.game_context import build_agent_game_contexts
from werewolf_agent.adapters.agents.game_driver import (
    AgentRuntime,
    _lmstudio_model_id,
    _openai_compatible_model,
    drive_prepared_game,
)
from werewolf_agent.adapters.application_bridge import build_setup_catalog
from werewolf_agent.adapters.llm.configuration import LlmProviderConfig
from werewolf_agent.adapters.resources import load_llm_definitions
from werewolf_agent.agents import DecisionTrace, RandomLegalAgentFactory
from werewolf_agent.application import PreparedAdvanceGame
from werewolf_agent.application.errors import GameError
from werewolf_agent.application.handlers import compute_prepared_advance
from werewolf_agent.contracts import LlmProviderError
from werewolf_agent.domain import Game, GameSetup, Player, build_game_rules
from werewolf_agent.setup import (
    checksum_payload,
    generate_players,
    namespace_seed,
    rule_definition_from_values,
)


class _TraceSink:
    def __init__(self) -> None:
        self.records: list[DecisionTrace] = []

    def record_decision(self, trace: DecisionTrace) -> None:
        self.records.append(trace)


def _prepared(seed: int = 7) -> tuple[PreparedAdvanceGame, tuple[str, ...]]:
    catalog = build_setup_catalog()
    setup = catalog.require_document(catalog.recommended_template_id)
    mechanics = setup.mechanics
    player_count = sum(mechanics.role_counts.values())
    generated = generate_players(
        setup.player_generation,
        player_count=player_count,
        seed=seed,
    )
    players = tuple(Player(item.player_id, item.profile.name) for item in generated)
    rules = build_game_rules(
        rule_definition_from_values(
            player_count=player_count,
            role_counts=mechanics.role_counts,
            discussion=mechanics.discussion.to_mapping(),
            voting=mechanics.voting.to_mapping(),
            night=mechanics.night.to_mapping(),
            lifecycle=mechanics.lifecycle.to_mapping(),
            roles={key: value.to_mapping() for key, value in mechanics.roles.items()},
            abilities={key: value.to_mapping() for key, value in mechanics.abilities.items()},
        )
    )
    game = Game.create(
        GameSetup(players),
        rules=rules,
        random=random.Random(namespace_seed(seed, "role_assignment")),
    )
    player_ids = tuple(game.snapshot().players)
    setup_document = setup.to_mapping()
    return (
        PreparedAdvanceGame(
            game_id="game-1",
            version=1,
            seed=seed,
            config={
                "player_agent_types": {player_id: "external" for player_id in player_ids},
                "setup_document": setup_document,
                "setup_checksum": checksum_payload(setup_document),
                "mechanics_checksum": checksum_payload(mechanics.to_mapping()),
            },
            game=game,
            prepared_state=game.snapshot(),
            created_at=datetime(2030, 1, 1, tzinfo=UTC),
            phase_seed=namespace_seed(seed, "prepared-phase"),
        ),
        player_ids,
    )


def _runtime(player_ids: tuple[str, ...], sink: _TraceSink) -> AgentRuntime:
    return AgentRuntime(
        config=LlmProviderConfig(
            provider="fake",
            model="unused",
            base_url="",
            api_key="",
            timeout_seconds=1,
            max_tokens=1,
            temperature=0,
        ),
        definitions=load_llm_definitions(prompt_path=None, fake_responses_path=None),
        agent_factories={player_id: RandomLegalAgentFactory() for player_id in player_ids},
        decision_trace_sink=sink,
    )


def test_prepared_game_uses_simulation_and_advances_exactly_once() -> None:
    prepared, player_ids = _prepared()
    before = prepared.game.snapshot()
    sink = _TraceSink()

    driven = drive_prepared_game(prepared, runtime=_runtime(player_ids, sink))
    after = driven.game.snapshot()

    assert driven.domain_transition_complete
    assert driven.domain_events
    assert after.phase != before.phase or after.day != before.day
    assert sink.records

    computed = compute_prepared_advance(driven)

    assert computed.phase == after.phase.value
    assert computed.day == after.day
    assert computed.private_state["phase"] == after.phase.value


def test_game_context_keeps_only_each_players_current_private_metadata() -> None:
    prepared, _ = _prepared()
    snapshot = prepared.game.snapshot()
    setup = prepared.config["setup_document"]
    assert isinstance(setup, dict)

    contexts = build_agent_game_contexts(
        setup,
        snapshot,
        setup_checksum="1" * 64,
        mechanics_checksum="2" * 64,
    )

    assert set(contexts) == set(snapshot.players)
    assert all(
        context.role_id == snapshot.players[player_id].role
        for player_id, context in contexts.items()
    )
    assert all(context.setup_checksum == "1" * 64 for context in contexts.values())


def test_application_rejects_missing_or_unmarked_prepared_transition() -> None:
    missing, player_ids = _prepared()
    with pytest.raises(GameError, match="transition state"):
        compute_prepared_advance(replace(missing, domain_transition_complete=True))

    driven = drive_prepared_game(missing, runtime=_runtime(player_ids, _TraceSink()))
    with pytest.raises(GameError, match="transition state"):
        compute_prepared_advance(replace(driven, domain_transition_complete=False))


def test_prepared_transition_accepts_discussion_substage_change() -> None:
    prepared, player_ids = _prepared()
    runtime = _runtime(player_ids, _TraceSink())
    first = drive_prepared_game(prepared, runtime=runtime)
    opening = first.game.snapshot()
    assert opening.phase.value == "day_discussion"

    second = replace(
        first,
        version=2,
        prepared_state=opening,
        phase_seed=namespace_seed(7, "prepared-response"),
        domain_transition_complete=False,
        domain_events=(),
    )
    response = drive_prepared_game(second, runtime=runtime)
    after = response.game.snapshot()

    assert after != opening
    assert after.phase == opening.phase
    assert after.day == opening.day
    computed = compute_prepared_advance(response)
    assert computed.phase == after.phase.value
    assert computed.day == after.day


def test_lmstudio_model_catalog_is_rejected_before_exceeding_byte_limit(monkeypatch) -> None:
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def raise_for_status(self) -> None:
            return None

        def iter_bytes(self):
            yield b'{"data":['
            yield b"x" * 32

    monkeypatch.setattr("httpx.stream", lambda *_args, **_kwargs: Response())
    config = LlmProviderConfig(
        provider="lmstudio",
        model="auto",
        base_url="http://127.0.0.1:1234/v1",
        api_key="",
        timeout_seconds=1,
        max_tokens=1,
        temperature=0,
        model_catalog_max_bytes=16,
    )

    with pytest.raises(LlmProviderError):
        _lmstudio_model_id(config)


def test_deadline_bound_decisions_disable_transport_retries(monkeypatch) -> None:
    """Decision全体期限を越えるtransport内retryを構成しない."""
    captured: dict[str, object] = {}

    class ChatOpenAI:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

    module = type("LangChainOpenAI", (), {"ChatOpenAI": ChatOpenAI})
    monkeypatch.setattr(
        "werewolf_agent.adapters.agents.game_driver.import_module",
        lambda _name: module,
    )
    placeholder = "test"
    config = LlmProviderConfig(
        provider="openai",
        model="test-model",
        base_url="https://example.invalid/v1",
        api_key=placeholder,
        timeout_seconds=10,
        max_tokens=128,
        temperature=0,
    )

    _openai_compatible_model(config, model_id="test-model")

    assert captured["max_retries"] == 0

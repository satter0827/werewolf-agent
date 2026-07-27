import ast
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
import typer
from typer.testing import CliRunner

from werewolf_agent.clients.cli import commands as cui_commands
from werewolf_agent.clients.cli.app import app
from werewolf_agent.clients.cli.commands import common as command_common
from werewolf_agent.clients.cli.commands import setup as setup_command
from werewolf_agent.clients.cli.errors import run_app_command
from werewolf_agent.contracts import AppError, ErrorCode
from werewolf_agent.contracts.schemas import (
    AdvanceGameJobResponse,
    AdvanceGameResponse,
    CreateGameRequest,
    GameListResponse,
    GameResponse,
    GameSetupOptionsResponse,
    GameTimelineItem,
    GameTimelineResponse,
    PlayerActionRequest,
    PlayerActionResponse,
    PlayerObservationResponse,
    PublicGameState,
    PublicGameSummary,
    PublicPlayerState,
)
from werewolf_agent.observability import configure_entrypoint_logging
from werewolf_agent.settings import (
    AppSettings,
    get_settings,
)


@pytest.fixture(autouse=True)
def disable_operational_log_file(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("WEREWOLF_LOG_OUTPUT", "none")
    monkeypatch.setenv("WEREWOLF_SUPABASE_URL", "http://127.0.0.1:54321")
    monkeypatch.setenv("WEREWOLF_SUPABASE_PUBLISHABLE_KEY", "publishable-test")


def _state(
    *,
    status: str = "running",
    phase: str = "night",
    winner: str | None = None,
) -> PublicGameState:
    return PublicGameState(
        game_id="game-1",
        status=status,
        phase=phase,
        day=1,
        version=2 if status == "completed" else 1,
        seed=1,
        players=[
            PublicPlayerState(
                id="player-1",
                name="Player 1",
                alive=status != "completed",
                status="dead" if status == "completed" else "alive",
                eliminated_day=1 if status == "completed" else None,
            ),
            PublicPlayerState(id="player-2", name="Player 2", alive=True, status="alive"),
        ],
        alive_player_ids=["player-2"] if status == "completed" else ["player-1", "player-2"],
        eliminated_player_ids=["player-1"] if status == "completed" else [],
        winner=winner,
        summary={"alive_count": 1 if status == "completed" else 2, "speech_count": 0},
    )


def _event(sequence: int, event_type: str, payload: dict[str, object]) -> GameTimelineItem:
    return GameTimelineItem(
        sequence=sequence,
        event_sequence=sequence,
        version=sequence,
        event_type=event_type,
        phase="finished" if event_type == "game_finished" else "night",
        day=1,
        payload=payload,
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _run_summary() -> PublicGameSummary:
    return PublicGameSummary(
        game_id="game-1",
        status="completed",
        phase="finished",
        day=2,
        version=4,
        seed=1,
        player_count=6,
        alive_count=3,
        winner="village",
        step_count=3,
        turn_count=3,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
        completed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


class FakeGameClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.available_sequence = 0
        self.events = [
            _event(1, "game_started", {"player_count": 6}),
            _event(2, "phase_started", {"phase": "day_discussion"}),
            _event(3, "game_finished", {"winner": "village"}),
        ]

    def create_game(self, request: CreateGameRequest) -> GameResponse:
        selection = request.setup
        value = selection.preset_id if selection.mode == "preset" else request.player_count
        self.calls.append(("create", value))
        self.available_sequence = 1
        return GameResponse(game_id="game-1", state=_state())

    def get_game(self, game_id: str) -> GameResponse:
        self.calls.append(("get", game_id))
        return GameResponse(game_id="game-1", state=_state())

    def health(self) -> dict[str, str]:
        self.calls.append(("health", "ok"))
        return {"status": "ok", "service": "supabase"}

    def get_setup_options(self) -> GameSetupOptionsResponse:
        self.calls.append(("setup_options", "default"))
        return GameSetupOptionsResponse(
            player_count={"min": 5, "max": 8},
            roles=[
                {
                    "id": "villager",
                    "name": "Villager",
                    "identity_faction": "village",
                    "victory_team": "village",
                    "objective": "Find the werewolf",
                    "abilities": [],
                },
                {
                    "id": "werewolf",
                    "name": "Werewolf",
                    "identity_faction": "werewolf",
                    "victory_team": "werewolf",
                    "objective": "Reach parity",
                    "abilities": [],
                },
            ],
            default_role_counts={"werewolf": 1, "villager": 4},
            default_rules={
                "day_speech_limit_per_player": 1,
                "allow_self_vote": False,
                "allow_vote_revision": False,
                "allow_night_action_revision": False,
                "enable_first_night_attack": False,
                "vote_tie_resolution": "no_elimination",
                "wolf_attack_tie_resolution": "random_target",
                "seer_result_detail": "faction",
                "medium_result_detail": "faction",
                "starting_phase": "night",
                "allow_knight_self_guard": True,
                "allow_knight_repeat_guard": True,
                "allow_seer_self_inspect": False,
                "allow_werewolf_friendly_fire": False,
                "reveal_role_on_death": False,
            },
        )

    def advance_game(self, game_id: str) -> AdvanceGameResponse:
        self.calls.append(("advance", game_id))
        self.available_sequence += 1
        status = "completed" if self.available_sequence >= 3 else "running"
        phase = "finished" if status == "completed" else "day_discussion"
        winner = "village" if status == "completed" else None
        timeline = [item for item in self.events if item.sequence == self.available_sequence]
        return AdvanceGameResponse(
            game_id=game_id,
            status=status,
            state=_state(status=status, phase=phase, winner=winner),
            timeline=timeline,
        )

    def start_advance_game(self, game_id: str) -> AdvanceGameJobResponse:
        self.calls.append(("start_advance", game_id))
        return AdvanceGameJobResponse(
            job_id="job-1",
            game_id=game_id,
            status="queued",
            state_version=self.available_sequence,
            poll_url="/api/v1/games/game-1/advance-jobs/job-1",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            updated_at=datetime(2026, 1, 1, tzinfo=UTC),
        )

    def get_advance_job(self, game_id: str, job_id: str) -> AdvanceGameJobResponse:
        self.calls.append(("advance_job", job_id))
        result = self.advance_game(game_id)
        return AdvanceGameJobResponse(
            job_id=job_id,
            game_id=game_id,
            status="completed",
            state_version=result.state.version,
            result=result,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            updated_at=datetime(2026, 1, 1, tzinfo=UTC),
        )

    def get_latest_advance_job(self, game_id: str) -> AdvanceGameJobResponse:
        return self.get_advance_job(game_id, "job-1")

    def get_timeline(
        self,
        game_id: str,
        *,
        after: int = 0,
        limit: int = 100,
    ) -> GameTimelineResponse:
        _ = limit
        self.calls.append(("timeline", after))
        items = [
            event for event in self.events if after < event.sequence <= self.available_sequence
        ]
        next_after = items[-1].sequence if items else after
        return GameTimelineResponse(game_id=game_id, items=items, next_after=next_after)

    def list_games(
        self,
        *,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> GameListResponse:
        self.calls.append(("games", (status, limit, offset)))
        return GameListResponse(games=[_run_summary()])

    def get_private_observation(
        self,
        game_id: str,
        player_id: str,
    ) -> PlayerObservationResponse:
        self.calls.append(("observation", (game_id, player_id)))
        return PlayerObservationResponse(
            game_id=game_id,
            player_id=player_id,
            observation={
                "phase": "day_discussion",
                "day": 1,
                "me": {"id": player_id, "name": "Player 1", "role": "villager"},
                "players": [{"id": "player-1"}, {"id": "player-2"}],
                "known_roles": {"player-1": "villager"},
                "available_actions": ["speech"],
            },
        )

    def submit_player_action(
        self,
        game_id: str,
        player_id: str,
        request: PlayerActionRequest,
    ) -> PlayerActionResponse:
        self.calls.append(("action", (game_id, player_id, request.type)))
        return PlayerActionResponse(
            game_id=game_id,
            player_id=player_id,
            state=_state(),
            timeline=[_event(4, "speech_recorded", {"player_id": player_id})],
        )


def test_doctor_command_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = CliRunner()
    fake_client = FakeGameClient()
    monkeypatch.setattr(command_common, "build_game_client", lambda _settings: fake_client)

    result = runner.invoke(app, ["system", "doctor"])

    assert result.exit_code == 0
    assert "Werewolf Agent 診断" in result.output
    assert "fake" in result.output
    assert "fake-list-llm" in result.output


def test_doctor_json_output_is_machine_readable(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_client = FakeGameClient()
    monkeypatch.setattr(command_common, "build_game_client", lambda _settings: fake_client)

    result = CliRunner().invoke(app, ["system", "doctor", "--output", "json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["provider"] == "fake"
    assert payload["model"] == "fake-list-llm"
    assert payload["prompt file"] == "packaged"
    assert payload["data source"] == "api"


def test_doctor_command_redacts_supabase_worker_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_client = FakeGameClient()
    monkeypatch.setattr(command_common, "build_game_client", lambda _settings: fake_client)
    get_settings.cache_clear()
    try:
        result = CliRunner().invoke(
            app,
            ["system", "doctor"],
            env={
                "WEREWOLF_SUPABASE_URL": "http://127.0.0.1:54321",
                "WEREWOLF_SUPABASE_PUBLISHABLE_KEY": "anon-test",
                "WEREWOLF_SUPABASE_DB_DSN": "postgresql://postgres:secret@db.test/postgres",
            },
        )
    finally:
        get_settings.cache_clear()

    assert result.exit_code == 0
    assert "secret" not in result.output
    assert "[REDACTED]" in result.output


def test_run_app_command_handles_app_error_safely(caplog: pytest.LogCaptureFixture) -> None:
    test_app = typer.Typer()

    def fail() -> None:
        raise AppError(
            "The selected action is not allowed.",
            code=ErrorCode.GAME_INVALID_ACTION,
            context={"api_key": "secret"},
        )

    @test_app.command()
    def broken() -> None:
        run_app_command(fail)

    @test_app.command()
    def ok() -> None:
        pass

    with caplog.at_level(logging.INFO, logger="werewolf_agent.clients.cli.errors"):
        result = CliRunner().invoke(test_app, ["broken"])

    assert result.exit_code == 1
    assert "このゲームでは選択した操作を行えません。" in result.output
    assert "context=" not in result.output
    assert "secret" not in result.output
    record = next(
        record
        for record in caplog.records
        if record.event_action == "cli.application_error.handled"
    )
    assert record.levelname == "INFO"
    assert record.error_code == "game.invalid_action"


def test_run_app_command_logs_operational_app_error_as_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    test_app = typer.Typer()

    def fail() -> None:
        raise AppError("The API server could not be reached.", code=ErrorCode.API_UNAVAILABLE)

    @test_app.command()
    def broken() -> None:
        run_app_command(fail)

    @test_app.command()
    def ok() -> None:
        pass

    with caplog.at_level(logging.INFO, logger="werewolf_agent.clients.cli.errors"):
        result = CliRunner().invoke(test_app, ["broken"])

    assert result.exit_code == 1
    record = next(
        record
        for record in caplog.records
        if record.event_action == "cli.application_error.handled"
    )
    assert record.levelname == "WARNING"
    assert record.error_code == "api.unavailable"


def test_doctor_command_reports_invalid_configuration_safely() -> None:
    get_settings.cache_clear()
    try:
        result = CliRunner().invoke(
            app,
            ["system", "doctor"],
            env={"WEREWOLF_LOG_LEVEL": "VERBOSE"},
        )
    finally:
        get_settings.cache_clear()

    assert result.exit_code == 1
    assert "Invalid configuration for WEREWOLF_LOG_LEVEL" in result.output
    assert "log_level must be one of" in result.output


def test_cli_startup_log_writes_trace_settings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    get_settings.cache_clear()
    monkeypatch.setattr(command_common, "build_game_client", lambda _settings: FakeGameClient())
    log_file = tmp_path / "cli.jsonl"
    try:
        result = CliRunner().invoke(
            app,
            ["system", "doctor"],
            env={
                "WEREWOLF_LOG_LEVEL": "DEBUG",
                "WEREWOLF_LOG_OUTPUT": "file",
                "WEREWOLF_LOG_DIR": str(tmp_path),
                "WEREWOLF_LOG_FILE_NAME": log_file.name,
                "WEREWOLF_LOG_THIRD_PARTY_LEVEL": "INFO",
            },
        )
    finally:
        get_settings.cache_clear()

    assert result.exit_code == 0, (result.output, repr(result.exception))
    for handler in logging.getLogger().handlers:
        handler.flush()
    payloads = [
        json.loads(line) for line in log_file.read_text(encoding="utf-8").splitlines() if line
    ]
    startup_payload = next(
        payload for payload in payloads if payload["event.action"] == "cli.application.started"
    )
    assert startup_payload["event.outcome"] == "success"
    assert startup_payload["cli_command"] == "system"
    assert startup_payload["log_level"] == "DEBUG"
    assert startup_payload["log_output"] == "file"
    assert startup_payload["log_file_path"] == str(log_file)
    assert startup_payload["log_third_party_level"] == "INFO"
    assert "seat_credential" not in startup_payload


def test_play_command_uses_public_api_client(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_client = FakeGameClient()
    monkeypatch.setattr(command_common, "build_game_client", lambda _settings: fake_client)
    log_path = tmp_path / "timeline.jsonl"

    result = CliRunner().invoke(
        app,
        [
            "game",
            "play",
            "--preset",
            "standard_6",
            "--seed",
            "1",
            "--max-steps",
            "4",
            "--log-jsonl",
            str(log_path),
            "--no-show-timeline",
        ],
    )

    assert result.exit_code == 0
    assert "ゲームが終了しました" in result.output
    assert fake_client.calls == [
        ("create", "standard_6"),
        ("timeline", 0),
        ("advance", "game-1"),
        ("timeline", 1),
        ("advance", "game-1"),
        ("timeline", 2),
    ]
    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    assert [json_line["sequence"] for json_line in map(json.loads, lines)] == [1, 2, 3]


def test_play_json_output_is_single_machine_readable_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = FakeGameClient()
    monkeypatch.setattr(command_common, "build_game_client", lambda _settings: fake_client)
    get_settings.cache_clear()
    env = {"WEREWOLF_LOG_LEVEL": "CRITICAL"}

    try:
        result = CliRunner().invoke(
            app,
            [
                "game",
                "play",
                "--preset",
                "standard_6",
                "--seed",
                "1",
                "--max-steps",
                "4",
                "--output",
                "json",
            ],
            env=env,
        )
    finally:
        get_settings.cache_clear()

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["game_id"] == "game-1"
    assert payload["winner"] == "village"
    assert [item["sequence"] for item in payload["timeline"]] == [1, 2, 3]


def test_new_command_can_request_one_manual_player(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_client = FakeGameClient()
    monkeypatch.setattr(command_common, "build_game_client", lambda _settings: fake_client)

    result = CliRunner().invoke(
        app,
        [
            "game",
            "create",
            "--manual-player",
            "player-1",
            "--preset",
            "standard_6",
        ],
    )

    assert result.exit_code == 0
    assert "seat credential" not in result.output
    assert fake_client.calls == [("create", "standard_6")]


def test_new_command_forwards_manual_player_for_preset_validation() -> None:
    result = CliRunner().invoke(
        app,
        [
            "game",
            "create",
            "--preset",
            "standard_6",
            "--manual-player",
            "player-9",
        ],
    )

    assert result.exit_code == 1


def test_create_command_accepts_setup_preset(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_client = FakeGameClient()
    monkeypatch.setattr(command_common, "build_game_client", lambda _settings: fake_client)
    result = CliRunner().invoke(
        app,
        [
            "game",
            "create",
            "--preset",
            "standard_6",
        ],
    )

    assert result.exit_code == 0
    assert fake_client.calls == [("create", "standard_6")]


def test_setup_options_show_and_advance_commands_use_public_api_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = FakeGameClient()
    monkeypatch.setattr(command_common, "build_game_client", lambda _settings: fake_client)
    monkeypatch.setattr(
        setup_command,
        "build_public_client",
        lambda _settings: SimpleNamespace(
            get_runtime_config=lambda: SimpleNamespace(setup=fake_client.get_setup_options())
        ),
    )

    setup_options_result = CliRunner().invoke(app, ["setup", "show"])
    show_result = CliRunner().invoke(app, ["game", "show", "game-1"])
    advance_result = CliRunner().invoke(app, ["game", "advance", "game-1"])

    assert setup_options_result.exit_code == 0
    assert show_result.exit_code == 0
    assert advance_result.exit_code == 0
    assert ("setup_options", "default") in fake_client.calls
    assert ("get", "game-1") in fake_client.calls
    assert ("advance", "game-1") in fake_client.calls


def test_setup_options_uses_public_api_without_supabase_client_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = FakeGameClient()
    public_client = SimpleNamespace(
        get_runtime_config=lambda: SimpleNamespace(setup=fake_client.get_setup_options())
    )
    monkeypatch.setattr(setup_command, "build_public_client", lambda _settings: public_client)
    monkeypatch.setenv("WEREWOLF_SUPABASE_URL", "")
    monkeypatch.setenv("WEREWOLF_SUPABASE_PUBLISHABLE_KEY", "")
    get_settings.cache_clear()

    result = CliRunner().invoke(app, ["setup", "show"])

    assert result.exit_code == 0
    assert ("setup_options", "default") in fake_client.calls


def test_play_command_handles_data_source_problem_safely(monkeypatch: pytest.MonkeyPatch) -> None:
    class FailingGameClient(FakeGameClient):
        def create_game(self, request: CreateGameRequest) -> GameResponse:
            _ = request
            raise AppError(
                "game.invalid_action: The selected action is not allowed.",
                code=ErrorCode.GAME_INVALID_ACTION,
                context={"api_key": "secret"},
            )

    monkeypatch.setattr(
        command_common,
        "build_game_client",
        lambda _settings: FailingGameClient(),
    )

    result = CliRunner().invoke(app, ["game", "play"])

    assert result.exit_code == 1
    assert "このゲームでは選択した操作を行えません。" in result.output
    assert "context=" not in result.output
    assert "secret" not in result.output


def test_run_app_command_logs_sanitized_error_message(caplog) -> None:
    def fail() -> None:
        raise AppError(
            "configuration failed: api_key=secret-value",
            code=ErrorCode.CONFIG_INVALID_VALUE,
        )

    with (
        caplog.at_level(logging.INFO, logger="werewolf_agent.clients.cli.errors"),
        pytest.raises(typer.Exit),
    ):
        run_app_command(fail)

    record = next(
        item for item in caplog.records if item.event_action == "cli.application_error.handled"
    )
    assert record.error_message == "configuration failed: api_key=[REDACTED]"
    assert "secret-value" not in record.error_message


def test_run_app_command_writes_sanitized_error_message_to_json_log(tmp_path: Path) -> None:
    log_path = tmp_path / "cli.jsonl"
    configure_entrypoint_logging(
        AppSettings(
            _env_file=None,
            log_dir=tmp_path,
            log_file_name=log_path.name,
            log_output="file",
        )
    )

    def fail() -> None:
        raise AppError(
            "configuration failed: api_key=secret-value",
            code=ErrorCode.CONFIG_INVALID_VALUE,
        )

    with pytest.raises(typer.Exit):
        run_app_command(fail)

    payload = json.loads(log_path.read_text(encoding="utf-8").splitlines()[-1])
    assert payload["error.message"] == "configuration failed: api_key=[REDACTED]"
    assert "secret-value" not in payload["error.message"]


def test_timeline_replay_and_games_use_public_api_client(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_client = FakeGameClient()
    fake_client.available_sequence = 3
    monkeypatch.setattr(command_common, "build_game_client", lambda _settings: fake_client)
    log_path = tmp_path / "timeline-watch.jsonl"
    timeline_path = tmp_path / "timeline.jsonl"
    timeline_path.write_text(_event(1, "game_started", {"player_count": 6}).model_dump_json())

    timeline_result = CliRunner().invoke(
        app,
        ["records", "timeline", "game-1", "--log-jsonl", str(log_path)],
    )
    replay_result = CliRunner().invoke(
        app,
        ["records", "replay", "--timeline", str(timeline_path)],
    )
    games_result = CliRunner().invoke(app, ["game", "list"])

    assert timeline_result.exit_code == 0
    assert replay_result.exit_code == 0
    assert games_result.exit_code == 0
    assert "ゲーム一覧" in games_result.output
    assert "game_started" in timeline_result.output
    assert log_path.exists()


def test_timeline_follow_rejects_json_output(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_client = FakeGameClient()
    monkeypatch.setattr(command_common, "build_game_client", lambda _settings: fake_client)

    result = CliRunner().invoke(
        app,
        [
            "records",
            "timeline",
            "game-1",
            "--follow",
            "--output",
            "json",
        ],
    )

    assert result.exit_code == 1
    assert "継続取得ではjsonl出力を使用してください。" in result.output


def test_cui_does_not_import_internal_game_layers() -> None:
    imported_modules: list[str] = []
    cui_package = Path(cui_commands.__file__).parent
    for source_path in cui_package.rglob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imported_modules.append(node.module)

    forbidden_prefixes = (
        "werewolf_agent.domain",
        "werewolf_agent.application",
    )
    assert not any(module.startswith(forbidden_prefixes) for module in imported_modules)

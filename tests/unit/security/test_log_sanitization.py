from werewolf_agent.observability.sanitization import safe_http_log_path


def test_safe_http_log_path_removes_game_and_player_identifiers() -> None:
    path = "/api/v1/games/game-1/players/player-2/actions"

    assert safe_http_log_path(path) == "/api/v1/games/{game_id}/players/{player_id}/actions"


def test_safe_http_log_path_keeps_collection_routes_readable() -> None:
    path = "games/game-1/timeline"

    assert safe_http_log_path(path) == "games/{game_id}/timeline"

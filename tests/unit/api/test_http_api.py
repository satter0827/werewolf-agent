from fastapi.testclient import TestClient

from werewolf_agent.api.bootstrap import create_app


def test_setup_routes_are_explicit_in_openapi() -> None:
    schema = create_app().openapi()
    operations = {
        operation["operationId"]
        for path in schema["paths"].values()
        for operation in path.values()
        if isinstance(operation, dict) and "operationId" in operation
    }

    assert {
        "setup_catalog_get",
        "setup_template_get",
        "setup_validate",
        "setup_player_preview",
        "setup_list",
        "setup_create",
        "setup_get",
        "setup_revision_list",
        "setup_revision_get",
        "setup_revision_create",
    } <= operations


def test_player_observation_is_a_typed_client_contract() -> None:
    schema = create_app().openapi()
    components = schema["components"]["schemas"]
    response = components["PlayerObservationResponse"]
    observation_name = response["properties"]["observation"]["$ref"].rsplit("/", 1)[-1]
    observation = components[observation_name]
    action_name = observation["properties"]["available_actions"]["items"]["$ref"].rsplit("/", 1)[-1]
    action = components[action_name]

    assert observation["additionalProperties"] is False
    assert {
        "phase",
        "day",
        "me",
        "players",
        "known_roles",
        "known_factions",
        "available_actions",
        "history",
        "win_result",
    } <= observation["properties"].keys()
    assert {
        "key",
        "type",
        "ability_id",
        "legal_target_ids",
        "message_required",
    } == action["properties"].keys()
    assert action["additionalProperties"] is False


def test_public_setup_catalog_and_preview_do_not_require_authentication() -> None:
    """Anonymous editors can load templates and preview generated players."""
    with TestClient(create_app()) as client:
        catalog = client.get("/api/v1/setup-catalog")
        preview = client.post(
            "/api/v1/setups/preview-players",
            json={
                "setup": {"mode": "template", "template_id": "standard_6"},
                "seed": 7,
            },
        )

    assert catalog.status_code == 200
    assert preview.status_code == 200
    payload = preview.json()
    assert len(payload["players"]) == 6
    assert all(
        "role" not in player and "reasoning_style" not in player for player in payload["players"]
    )

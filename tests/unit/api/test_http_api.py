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

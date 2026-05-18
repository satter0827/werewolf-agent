import os

import pytest
from pydantic import BaseModel, ValidationError

from werewolf_agent.errors import GamePhaseError

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "werewolf_agent.interfaces.api.config.settings")
django = pytest.importorskip("django")
django.setup()

override_settings = pytest.importorskip("django.test").override_settings
SimpleTestCase = pytest.importorskip("django.test").SimpleTestCase
APIRequestFactory = pytest.importorskip("rest_framework.test").APIRequestFactory
DRFValidationError = pytest.importorskip("rest_framework.exceptions").ValidationError
ErrorDetail = pytest.importorskip("rest_framework.exceptions").ErrorDetail

from werewolf_agent.interfaces.api.errors import exception_handler  # noqa: E402


def _request(path: str = "/api/games/1/actions/"):
    return APIRequestFactory().post(path, {}, format="json")


def test_app_error_becomes_problem_details() -> None:
    response = exception_handler(
        GamePhaseError("Night actions are closed.", context={"api_key": "secret"}),
        {"request": _request()},
    )

    assert response.status_code == 409
    assert response["Content-Type"] == "application/problem+json"
    assert response.data == {
        "type": "tag:werewolf-agent,2026:problem:game.invalid_phase",
        "title": "Invalid Game Phase",
        "status": 409,
        "detail": "Night actions are closed.",
        "instance": "/api/games/1/actions/",
        "code": "game.invalid_phase",
    }


def test_drf_validation_error_preserves_field_codes_and_json_pointers() -> None:
    response = exception_handler(
        DRFValidationError(
            {
                "name": [ErrorDetail("This field is required.", code="required")],
                "players": [{"id": [ErrorDetail("Invalid id.", code="invalid")]}],
            }
        ),
        {"request": _request("/api/games/")},
    )

    assert response.status_code == 400
    assert response.data["code"] == "request.validation_failed"
    assert response.data["errors"] == [
        {"code": "required", "detail": "This field is required.", "pointer": "/name"},
        {"code": "invalid", "detail": "Invalid id.", "pointer": "/players/0/id"},
    ]


def test_pydantic_validation_error_preserves_pydantic_error_types() -> None:
    class RequestPayload(BaseModel):
        player_count: int

    with pytest.raises(ValidationError) as exc_info:
        RequestPayload(player_count="many")

    response = exception_handler(exc_info.value, {"request": _request("/api/games/")})

    assert response.status_code == 400
    assert response.data["code"] == "request.validation_failed"
    assert response.data["errors"] == [
        {
            "code": "int_parsing",
            "detail": ("Input should be a valid integer, unable to parse string as an integer"),
            "pointer": "/player_count",
        }
    ]


class ApiProblemDetailsTests(SimpleTestCase):
    def test_method_not_allowed_returns_problem_details(self) -> None:
        response = self.client.post("/api/health/")

        assert response.status_code == 405
        assert response["Content-Type"].startswith("application/problem+json")
        assert response.json()["code"] == "method_not_allowed"
        assert response.json()["type"] == ("tag:werewolf-agent,2026:problem:method_not_allowed")

    @override_settings(DEBUG=False)
    def test_missing_api_route_returns_problem_details(self) -> None:
        response = self.client.get("/api/missing/")

        assert response.status_code == 404
        assert response["Content-Type"].startswith("application/problem+json")
        assert response.json()["code"] == "not_found"
        assert response.json()["instance"] == "/api/missing/"

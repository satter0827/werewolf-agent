from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from werewolf_agent.config import API_SERVICE_NAME
from werewolf_agent.interfaces.api.games.schemas import CreateGameRequest, GameEventsQuery
from werewolf_agent.interfaces.api.games.services import (
    create_game_run,
    default_ruleset,
    get_game_run,
    list_public_events,
    step_game_run,
)


@api_view(["GET"])
def health(_request):
    return Response({"status": "ok", "service": API_SERVICE_NAME})


@api_view(["GET"])
def ruleset_default(_request):
    """Return the default MVP ruleset."""
    return Response(default_ruleset().model_dump(mode="json"))


@api_view(["POST"])
def create_game(request):
    """Create a new deterministic MVP game run."""
    payload = CreateGameRequest.model_validate(request.data)
    response = create_game_run(payload)
    return Response(response.model_dump(mode="json"), status=status.HTTP_201_CREATED)


@api_view(["GET"])
def get_game(_request, game_id):
    """Return public game state."""
    response = get_game_run(game_id)
    return Response(response.model_dump(mode="json"))


@api_view(["POST"])
def step_game(_request, game_id):
    """Advance one MVP game by one synchronous step."""
    response = step_game_run(game_id)
    return Response(response.model_dump(mode="json"))


@api_view(["GET"])
def game_events(request, game_id):
    """Return public game events after an optional sequence cursor."""
    query = GameEventsQuery.model_validate({"after": request.query_params.get("after", 0)})
    response = list_public_events(game_id, after=query.after)
    return Response(response.model_dump(mode="json"))

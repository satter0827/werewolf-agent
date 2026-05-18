from django.urls import path

from .views import create_game, game_events, get_game, health, ruleset_default, step_game

urlpatterns = [
    path("health/", health, name="health"),
    path("rulesets/default/", ruleset_default, name="ruleset-default"),
    path("games/", create_game, name="games"),
    path("games/<uuid:game_id>/", get_game, name="game-detail"),
    path("games/<uuid:game_id>/steps/", step_game, name="game-step"),
    path("games/<uuid:game_id>/advance/", step_game, name="game-advance"),
    path("games/<uuid:game_id>/events/", game_events, name="game-events"),
]

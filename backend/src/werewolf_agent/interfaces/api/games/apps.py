from django.apps import AppConfig


class GamesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    label = "games"
    name = "werewolf_agent.interfaces.api.games"

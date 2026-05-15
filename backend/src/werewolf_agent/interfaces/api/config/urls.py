"""URL configuration for the Werewolf Agent API."""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("api/", include("werewolf_agent.interfaces.api.games.urls")),
    path("admin/", admin.site.urls),
]

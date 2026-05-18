"""URL configuration for the Werewolf Agent API."""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("api/", include("werewolf_agent.interfaces.api.games.urls")),
    path("admin/", admin.site.urls),
]

handler400 = "werewolf_agent.interfaces.api.errors.bad_request"
handler403 = "werewolf_agent.interfaces.api.errors.permission_denied"
handler404 = "werewolf_agent.interfaces.api.errors.not_found"
handler500 = "werewolf_agent.interfaces.api.errors.server_error"

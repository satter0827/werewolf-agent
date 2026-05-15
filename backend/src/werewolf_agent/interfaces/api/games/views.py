from rest_framework.decorators import api_view
from rest_framework.response import Response

from werewolf_agent.config import API_SERVICE_NAME


@api_view(["GET"])
def health(_request):
    return Response({"status": "ok", "service": API_SERVICE_NAME})

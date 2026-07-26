"""SchemathesisによるOpenAPI positive/negative contract探索。"""

import schemathesis
from hypothesis import HealthCheck, settings
from schemathesis import GenerationMode

from werewolf_agent.api.bootstrap import create_app
from werewolf_agent.settings import AppSettings

app = create_app(AppSettings(_env_file=None, api_docs_enabled=True))
positive_schema = schemathesis.openapi.from_asgi("/openapi.json", app).include(
    path="/api/v1/games/{game_id}", method="GET"
)
positive_schema.config.generation.update(
    modes=[GenerationMode.POSITIVE],
    max_examples=12,
    deterministic=True,
)

negative_schema = schemathesis.openapi.from_asgi("/openapi.json", app).include(
    path="/api/v1/games", method="GET"
)
negative_schema.config.generation.update(
    modes=[GenerationMode.NEGATIVE],
    max_examples=24,
    deterministic=True,
)


@positive_schema.parametrize()
@settings(suppress_health_check=[HealthCheck.filter_too_much])
def test_authenticated_contract_handles_generated_positive_input(case) -> None:
    case.headers = {"Authorization": "Bearer invalid"}
    case.call_and_validate()


@negative_schema.parametrize()
@settings(suppress_health_check=[HealthCheck.filter_too_much])
def test_authenticated_contract_rejects_generated_negative_input(case) -> None:
    case.headers = {"Authorization": "Bearer invalid"}
    case.call_and_validate()

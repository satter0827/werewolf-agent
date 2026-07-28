"""Schemathesisによる長時間stateful API探索。"""

import pytest
import schemathesis
from hypothesis import HealthCheck, settings
from schemathesis import GenerationMode

from werewolf_agent.api.bootstrap import create_app
from werewolf_agent.settings import AppSettings

schema = schemathesis.openapi.from_asgi(
    "/openapi.json",
    create_app(
        AppSettings(
            _env_file=None,
            api_docs_enabled=True,
            api_rate_limit_requests=10_000,
        )
    ),
)
schema.config.generation.update(
    modes=[GenerationMode.POSITIVE],
    deterministic=True,
)
# JSON Schemaはrequest全体のencode後byte数を表現できない。schema適合bodyでも
# transport上限を超えた場合の413はAPI contractに沿った受理可能な結果とする。
schema.config.checks.positive_data_acceptance.expected_statuses.append("413")
BaseWorkflow = schema.as_state_machine()


class AuthenticatedWorkflow(BaseWorkflow):
    def before_call(self, case) -> None:
        case.headers = {"Authorization": "Bearer invalid"}


TestOpenApiWorkflow = AuthenticatedWorkflow.TestCase
TestOpenApiWorkflow.settings = settings(
    max_examples=20,
    stateful_step_count=40,
    deadline=None,
    suppress_health_check=[HealthCheck.filter_too_much, HealthCheck.too_slow],
)
pytestmark = [pytest.mark.deep]

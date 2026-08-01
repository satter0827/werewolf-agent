from typing import Any

from werewolf_agent.adapters.supabase.diagnostics import SupabaseAdminDiagnostics
from werewolf_agent.contracts.api import AdminLlmTraceResponse


class _Result:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def fetchall(self) -> list[dict[str, Any]]:
        return self._rows


class _Connection:
    def __init__(self) -> None:
        self.query = ""

    def execute(self, query: str, _params: tuple[object, ...]) -> _Result:
        self.query = query
        return _Result([])


def test_trace_diagnostics_do_not_select_private_decision_payload() -> None:
    connection = _Connection()

    assert SupabaseAdminDiagnostics(connection).traces("game-1", limit=10) == []
    assert "parsed_decision" not in connection.query
    assert "parsed_decision" not in AdminLlmTraceResponse.model_fields

from werewolf_agent.interface.application.database import create_database_engine
from werewolf_agent.interface.runtime import AppSettings


def test_database_engine_hides_bound_parameters_in_logs() -> None:
    settings = AppSettings(_env_file=None, database_url="sqlite:///:memory:")
    engine = create_database_engine(settings)

    try:
        assert engine.hide_parameters is True
    finally:
        engine.dispose()

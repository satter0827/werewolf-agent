from werewolf_agent.commons.configuration import AppSettings
from werewolf_agent.interface.application.database import create_database_engine


def test_database_engine_hides_bound_parameters_in_logs() -> None:
    settings = AppSettings(_env_file=None, database_url="sqlite:///:memory:")
    engine = create_database_engine(settings)

    try:
        assert engine.hide_parameters is True
    finally:
        engine.dispose()

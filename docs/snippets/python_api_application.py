from werewolf_agent.application import (
    GameApplicationConfig,
    SetupTemplateCatalog,
    create_embedded_application,
)

config = GameApplicationConfig(
    min_players=4,
    max_players=16,
    game_list_default_limit=20,
    game_list_max_limit=100,
    timeline_default_limit=50,
    timeline_max_limit=200,
)
catalog = SetupTemplateCatalog(
    recommended_template_id="external",
    template_order=(),
    metadata={},
    documents={},
)
embedded = create_embedded_application(
    user_id="user-1",
    config=config,
    setup_catalog=catalog,
)

assert embedded.games.list(embedded.actor).games == []

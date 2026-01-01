"""
人狼エージェントのCLIモジュール
"""

from __future__ import annotations

import os

print(os.getcwd())

from werewolf_agent.common.log.logger import setup_logger
from werewolf_agent.core.agents.game_master import GameMaster

logger = setup_logger(__name__)

if __name__ == "__main__":
    gm = GameMaster()
    gm.start_game()
    gm.end_game()
    gm.end_game()
    gm.end_game()
    gm.end_game()
    gm.end_game()

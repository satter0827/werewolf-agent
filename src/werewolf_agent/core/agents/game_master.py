"""
人狼エージェントのゲームマスターを定義するモジュール。
"""

from __future__ import annotations

from werewolf_agent.common.log.logger import setup_logger

logger = setup_logger(__name__)


class GameMaster:
    """
    人狼ゲームの進行を管理するクラス。
    """

    def __init__(self) -> None:
        """
        初期化メソッド。"
        """
        logger.info("GameMaster initialized.")
        pass

    def start_game(self) -> None:
        pass

    def end_game(self) -> None:
        pass


if __name__ == "__main__":
    gm = GameMaster()
    gm.start_game()
    gm.end_game()
    gm.end_game()
    gm.end_game()

"""
標準的かつ安全な汎用ロガー基盤.

このモジュールは Python 標準の logging モジュールをラップし、
コンソールとファイルへの同時出力、日次ローテーション、
設定ファイルベースの柔軟な設定をサポートします。
"""

from __future__ import annotations

import configparser
import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any


class LoggerManager:
    """ロガーの初期化と管理を行うクラス."""

    def __init__(self) -> None:
        """初期化."""
        self._loggers: dict[str, logging.Logger] = {}
        self._initialized: bool = False
        self._default_config: dict[str, Any] = {
            "level": "INFO",
            "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            "date_format": "%Y-%m-%d %H:%M:%S",
        }

    def setup_logger(
        self,
        name: str,
        log_file_path: str | None = None,
        config_file: str | None = None,
        level: str | None = None,
    ) -> logging.Logger:
        """
        ロガーをセットアップして返す.

        Args:
            name: ロガー名（通常はモジュール名）
            log_file_path: ログファイルの出力パス（Noneの場合はコンソールのみ）
            config_file: 設定ファイルのパス（INI形式）
            level: ログレベル（"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"）

        Returns:
            logging.Logger: 設定済みのロガーインスタンス

        Examples:
            >>> manager = LoggerManager()
            >>> logger = manager.setup_logger("my_module", "/path/to/log.log")
            >>> logger.info("This is an info message")
        """
        # 既に同じ名前のロガーが設定済みの場合は再利用
        if name in self._loggers:
            return self._loggers[name]

        # 設定ファイルから設定を読み込む
        config = (
            self._load_config(config_file)
            if config_file
            else self._default_config.copy()
        )

        # 引数でレベルが指定された場合は上書き
        if level:
            config["level"] = level

        # ロガーの作成
        logger = logging.getLogger(name)
        logger.setLevel(self._get_log_level(config["level"]))
        logger.propagate = False  # 親ロガーへの伝播を防止

        # 既存のハンドラをクリア（重複防止）
        logger.handlers.clear()

        # フォーマッタの作成
        formatter = logging.Formatter(
            fmt=config["format"],
            datefmt=config.get("date_format", "%Y-%m-%d %H:%M:%S"),
        )

        # コンソールハンドラの追加
        console_handler = logging.StreamHandler()
        console_handler.setLevel(self._get_log_level(config["level"]))
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        # ファイルハンドラの追加（パスが指定されている場合）
        if log_file_path:
            self._add_file_handler(logger, log_file_path, formatter, config)

        # ロガーを登録
        self._loggers[name] = logger
        self._initialized = True

        return logger

    def _load_config(self, config_file: str) -> dict[str, Any]:
        """
        設定ファイル（INI形式）から設定を読み込む.

        Args:
            config_file: 設定ファイルのパス

        Returns:
            dict[str, Any]: 読み込んだ設定

        Raises:
            FileNotFoundError: 設定ファイルが見つからない場合
        """
        if not Path(config_file).exists():
            raise FileNotFoundError(f"設定ファイルが見つかりません: {config_file}")

        # RawConfigParser を使用して % 記号のエスケープを不要にする
        parser = configparser.RawConfigParser()
        parser.read(config_file, encoding="utf-8")

        config = self._default_config.copy()

        if parser.has_section("logger"):
            section = parser["logger"]
            config["level"] = section.get("level", config["level"])
            config["format"] = section.get("format", config["format"])
            config["date_format"] = section.get("date_format", config["date_format"])

            # ローテーション設定
            rotation_when = section.get("rotation_when")
            if rotation_when is not None:
                config["rotation_when"] = rotation_when

            rotation_interval = section.get("rotation_interval")
            if rotation_interval is not None:
                config["rotation_interval"] = section.getint("rotation_interval")

            backup_count = section.get("backup_count")
            if backup_count is not None:
                config["backup_count"] = section.getint("backup_count")

        return config

    def _add_file_handler(
        self,
        logger: logging.Logger,
        log_file_path: str,
        formatter: logging.Formatter,
        config: dict[str, Any],
    ) -> None:
        """
        ファイルハンドラをロガーに追加する.

        Args:
            logger: ロガーインスタンス
            log_file_path: ログファイルのパス
            formatter: フォーマッタ
            config: 設定辞書
        """
        # ディレクトリが存在しない場合は作成
        log_dir = Path(log_file_path).parent
        log_dir.mkdir(parents=True, exist_ok=True)

        # 日次ローテーションハンドラの作成
        file_handler = TimedRotatingFileHandler(
            filename=log_file_path,
            when=config.get("rotation_when", "midnight"),  # デフォルトは日次（深夜0時）
            interval=config.get("rotation_interval", 1),  # デフォルトは1日ごと
            backupCount=config.get("backup_count", 0),  # デフォルトは無制限（全日保持）
            encoding="utf-8",
        )
        file_handler.setLevel(self._get_log_level(config["level"]))
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    def _get_log_level(self, level_str: str) -> int:
        """
        文字列のログレベルを logging モジュールの定数に変換する.

        Args:
            level_str: ログレベルの文字列

        Returns:
            int: logging モジュールのログレベル定数
        """
        level_map = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
            "CRITICAL": logging.CRITICAL,
        }
        return level_map.get(level_str.upper(), logging.INFO)

    def get_logger(self, name: str) -> logging.Logger | None:
        """
        既に設定済みのロガーを取得する.

        Args:
            name: ロガー名

        Returns:
            logging.Logger | None: ロガーインスタンス、存在しない場合はNone
        """
        return self._loggers.get(name)

    def shutdown(self) -> None:
        """
        全てのロガーとハンドラをシャットダウンする.
        """
        for logger in self._loggers.values():
            for handler in logger.handlers[:]:
                handler.close()
                logger.removeHandler(handler)
        self._loggers.clear()
        self._initialized = False


# グローバルなロガーマネージャーのインスタンス
_manager = LoggerManager()


def setup_logger(
    name: str,
    log_file_path: str | None = None,
    config_file: str | None = None,
    level: str | None = None,
) -> logging.Logger:
    """
    ロガーをセットアップして返す（モジュールレベルの便利関数）.

    Args:
        name: ロガー名（通常はモジュール名）
        log_file_path: ログファイルの出力パス（Noneの場合はコンソールのみ）
        config_file: 設定ファイルのパス（INI形式）
        level: ログレベル（"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"）

    Returns:
        logging.Logger: 設定済みのロガーインスタンス

    Examples:
        >>> from automl_engine.common.logger import setup_logger
        >>> logger = setup_logger(__name__, "/path/to/app.log")
        >>> logger.info("Application started")
    """
    return _manager.setup_logger(name, log_file_path, config_file, level)


def get_logger(name: str) -> logging.Logger | None:
    """
    既に設定済みのロガーを取得する（モジュールレベルの便利関数）.

    Args:
        name: ロガー名

    Returns:
        logging.Logger | None: ロガーインスタンス、存在しない場合はNone
    """
    return _manager.get_logger(name)


def shutdown_logger() -> None:
    """
    全てのロガーとハンドラをシャットダウンする（モジュールレベルの便利関数）.

    Examples:
        >>> from automl_engine.common.logger import shutdown_logger
        >>> shutdown_logger()  # アプリケーション終了時に呼び出す
    """
    _manager.shutdown()

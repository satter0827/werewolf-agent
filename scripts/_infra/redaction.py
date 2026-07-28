"""永続化する成果物から秘密情報を除去する。"""

from scripts._infra.process import redact, redact_artifacts

__all__ = ["redact", "redact_artifacts"]

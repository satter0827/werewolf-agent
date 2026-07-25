"""設計文書と公開API文書の検査・構築。"""

from scripts.docs.building import build_documentation
from scripts.docs.inspection import inspect_documentation

__all__ = ["build_documentation", "inspect_documentation"]

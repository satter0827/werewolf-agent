"""Security検査を実行する。"""

from __future__ import annotations

import sys
from collections.abc import Sequence

from scripts.security.dependencies import audit_dependencies
from scripts.security.secrets import audit_secrets


def main(argv: Sequence[str] | None = None) -> int:
    """指定したsecurity検査を実行する。"""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments == ["dependencies"]:
        return audit_dependencies()
    if arguments == ["secrets"]:
        return audit_secrets()
    print("usage: python -m scripts.security {dependencies|secrets}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

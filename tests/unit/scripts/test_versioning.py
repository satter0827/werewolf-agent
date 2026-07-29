"""SemVer registryの回帰契約。"""

from __future__ import annotations

from scripts.versioning import __main__ as versioning


def test_registry_exposes_every_independent_semver_boundary() -> None:
    """意味のある公開境界だけをSemVerとして列挙する。"""
    items = versioning.inspect()

    assert {item["name"] for item in items} == {
        "architecture",
        "event",
        "product",
        "quality-evidence",
        "replay",
        "setup",
    }
    assert {item["version"] for item in items} == {"0.1.0"}


def test_check_accepts_the_new_baseline_against_main() -> None:
    """mainにregistryが存在しない初回baselineはversion漏れにしない。"""
    assert versioning.check("origin/main", "HEAD") == []


def test_semver_rejects_leading_zero() -> None:
    """SemVerの数値識別子へ先頭ゼロを許可しない。"""
    boundary = versioning.Boundary("sample", "test", "sample", r'"([^"]+)"', ())

    try:
        versioning._version(boundary, '"01.0.0"')
    except ValueError as error:
        assert "SemVer" in str(error)
    else:
        raise AssertionError("invalid SemVer was accepted")

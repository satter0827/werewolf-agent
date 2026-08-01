"""Version registryの回帰契約。"""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.versioning import __main__ as versioning


def _boundary(
    name: str,
    path: str,
    pattern: str,
    watch: tuple[str, ...],
    *,
    standard: versioning.VersionStandard = "semver",
    change_detection: versioning.ChangeDetection = "path",
) -> versioning.Boundary:
    return versioning.Boundary(name, "test", standard, path, pattern, watch, change_detection)


def test_registry_exposes_every_independent_version_boundary() -> None:
    """意味のある公開境界だけを規格とともに列挙する。"""
    items = versioning.inspect()

    assert {item["name"] for item in items} == {
        "agent",
        "architecture",
        "event",
        "experiment",
        "experiment-evaluator",
        "product",
        "quality-evidence",
        "replay",
        "rule-pack",
        "simulation",
        "setup",
    }
    versions = {str(item["name"]): str(item["version"]) for item in items}
    assert versions == {
        "agent": "0.5.0",
        "architecture": "0.13.2",
        "event": "0.1.0",
        "experiment": "0.5.0",
        "experiment-evaluator": "0.3.0",
        "product": "0.32.0",
        "quality-evidence": "0.2.0",
        "replay": "0.4.0",
        "rule-pack": "0.6.1",
        "simulation": "0.5.0",
        "setup": "0.3.0",
    }
    assert {item["standard"] for item in items if item["name"] == "product"} == {"pep440"}
    assert {item["standard"] for item in items if item["name"] != "product"} == {"semver"}


def test_check_accepts_the_new_baseline_against_main() -> None:
    """mainにregistryが存在しない初回baselineはversion漏れにしない。"""
    assert versioning.check("origin/main", "HEAD") == []


@pytest.mark.parametrize("value", ["01.0.0", "1.0.0-alpha.01"])
def test_semver_rejects_leading_zero(value: str) -> None:
    """SemVerの数値識別子へ先頭ゼロを許可しない。"""
    with pytest.raises(ValueError, match="SemVer"):
        versioning._semantic_version(value)


def test_semver_compares_prerelease_identifiers_by_the_standard() -> None:
    """pre-releaseは数値、文字列、識別子数をSemVerどおり比較する。"""
    parse = versioning._semantic_version

    assert parse("1.0.0-alpha") < parse("1.0.0-alpha.1")
    assert parse("1.0.0-alpha.2") < parse("1.0.0-alpha.10")
    assert parse("1.0.0-alpha.10") < parse("1.0.0-beta")
    assert parse("1.0.0-beta") < parse("1.0.0")
    assert parse("1.0.0+first") == parse("1.0.0+second")


def test_product_version_uses_pep440() -> None:
    """Python distributionのversionはPEP 440で検証する。"""
    boundary = _boundary("product", "version.py", r'"([^"]+)"', (), standard="pep440")

    assert versioning._version(boundary, '"1.0.0rc1"') == "1.0.0rc1"
    with pytest.raises(ValueError, match="PEP 440"):
        versioning._version(boundary, '"not-a-version"')


def test_product_bump_preserves_pep440_epoch() -> None:
    """PEP 440のepochを失ってversionを退行させない。"""
    boundary = _boundary("product", "version.py", r'"([^"]+)"', (), standard="pep440")

    assert versioning._bumped_version(boundary, "1!2.3.4rc1", "minor") == "1!2.4.0"


def test_changed_paths_include_committed_worktree_and_untracked_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """bump前の未commit変更もversion所有範囲として扱う。"""

    def fake_git(*arguments: str, allow_failure: bool = False) -> str | None:
        del allow_failure
        if arguments[:1] == ("merge-base",):
            return "base\n"
        if arguments[:2] == ("diff", "--name-only"):
            return "src/committed.py\nsrc/working.py\n"
        if arguments[:2] == ("ls-files", "--others"):
            return "src/untracked.py\n"
        raise AssertionError(arguments)

    monkeypatch.setattr(versioning, "_git", fake_git)

    assert versioning._changed_paths("origin/main", "HEAD") == (
        "src/committed.py",
        "src/untracked.py",
        "src/working.py",
    )


def test_file_watch_does_not_match_a_longer_filename() -> None:
    """file監視は似たprefixの別fileを対象にしない。"""
    assert versioning._matches_watch("src/events.py", "src/events.py")
    assert not versioning._matches_watch("src/events.py.bak", "src/events.py")
    assert versioning._matches_watch("src/contracts/events.py", "src/contracts/")


def test_semantic_python_ignores_docstrings_comments_and_formatting() -> None:
    """setup schemaは説明と表記だけの変更を契約変更にしない。"""
    before = '''"""old"""

def build(value: int = 1) -> int:
    """old"""
    return value
'''
    after = '''"""新しい説明。"""

# comment
def build(
    value: int = 1,
) -> int:
    """新しい説明。"""
    return value
'''

    assert versioning._semantic_python(before) == versioning._semantic_python(after)


@pytest.mark.parametrize(
    "after",
    [
        "def build(value: str = '1') -> int:\n    return 1\n",
        "def build(value: int = 2) -> int:\n    return value\n",
        "def build(value: int = 1) -> int:\n    return value + 1\n",
        "class Build:\n    pass\n",
    ],
)
def test_semantic_python_detects_contract_and_behavior_changes(after: str) -> None:
    """注釈、既定値、宣言、処理の変更を契約変更として扱う。"""
    before = "def build(value: int = 1) -> int:\n    return value\n"

    assert versioning._semantic_python(before) != versioning._semantic_python(after)


def test_semantic_boundary_uses_ast_only_for_matching_python_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """意味判定は指定境界のPython fileだけへ適用する。"""
    source = tmp_path / "setup.py"
    source.write_text('"""new"""\nVALUE = 1\n', encoding="utf-8")
    boundary = _boundary(
        "setup",
        "version.py",
        r'"([^"]+)"',
        ("setup.py",),
        change_detection="python_ast",
    )
    monkeypatch.setattr(versioning, "ROOT", tmp_path)
    monkeypatch.setattr(
        versioning,
        "_git",
        lambda *args, **_kwargs: '"""old"""\nVALUE = 1\n'
        if args == ("show", "base:setup.py")
        else None,
    )

    assert not versioning._boundary_touched(boundary, ("setup.py",), "base", "HEAD")

    source.write_text("VALUE = 2\n", encoding="utf-8")
    assert versioning._boundary_touched(boundary, ("setup.py",), "base", "HEAD")


def test_repository_path_rejects_an_escape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """version書換対象をrepository外へ出さない。"""
    monkeypatch.setattr(versioning, "ROOT", tmp_path)

    with pytest.raises(ValueError, match="repository外"):
        versioning._repository_path("../outside.py")


def test_check_requires_precedence_to_increase_for_touched_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """build metadataだけの変更をversion更新として認めない。"""
    path = tmp_path / "version.py"
    path.write_text('__version__ = "1.0.0+new"\n', encoding="utf-8")
    boundary = _boundary("event", "version.py", r'"([^"]+)"', ("src/",))
    monkeypatch.setattr(versioning, "ROOT", tmp_path)
    monkeypatch.setattr(versioning, "_boundaries", lambda: (boundary,))
    monkeypatch.setattr(versioning, "_merge_base", lambda *_args: "base")
    monkeypatch.setattr(versioning, "_changed_paths", lambda *_args: ("src/event.py",))
    monkeypatch.setattr(versioning, "_base_version", lambda *_args: "1.0.0+old")

    assert versioning.check("main", "HEAD") == [
        "event: 所有範囲が変更されていますがversionは1.0.0+newのままです。"
    ]


def test_check_reads_an_explicit_head_ref_instead_of_the_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """任意refの検査はcheckout中のfileと混在させない。"""
    path = tmp_path / "version.py"
    path.write_text('VERSION = "9.0.0"\n', encoding="utf-8")
    boundary = _boundary("event", "version.py", r'"([^"]+)"', ("src/",))
    monkeypatch.setattr(versioning, "ROOT", tmp_path)
    monkeypatch.setattr(versioning, "_boundaries", lambda: (boundary,))
    monkeypatch.setattr(versioning, "_merge_base", lambda *_args: "base")
    monkeypatch.setattr(versioning, "_changed_paths", lambda *_args: ("src/event.py",))
    monkeypatch.setattr(versioning, "_base_version", lambda *_args: "1.0.0")
    monkeypatch.setattr(
        versioning,
        "_git",
        lambda *args, **_kwargs: 'VERSION = "1.1.0"\n'
        if args == ("show", "head:version.py")
        else None,
    )

    assert versioning.check("main", "head") == []


def test_invalid_base_version_is_not_treated_as_an_absent_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """壊れたmain側versionは初回導入として黙認しない。"""
    boundary = _boundary("event", "version.py", r'"([^"]+)"', ())
    monkeypatch.setattr(versioning, "_git", lambda *_args, **_kwargs: 'VERSION = "invalid"\n')

    with pytest.raises(ValueError, match="SemVer"):
        versioning._base_version(boundary, "base")


def test_bump_updates_only_touched_boundaries_and_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """変更pathに対応する境界だけを同じ基準から一度だけ更新する。"""
    product_path = tmp_path / "product.py"
    event_path = tmp_path / "event.py"
    replay_path = tmp_path / "replay.py"
    product_path.write_text('__version__ = "1.2.3"\n', encoding="utf-8")
    event_path.write_text('EVENT = "1.2.3"\n', encoding="utf-8")
    replay_path.write_text('REPLAY = "1.2.3"\n', encoding="utf-8")
    boundaries = (
        _boundary(
            "product",
            "product.py",
            r'__version__\s*=\s*"([^"]+)"',
            ("src/",),
            standard="pep440",
        ),
        _boundary("event", "event.py", r'EVENT\s*=\s*"([^"]+)"', ("src/event.py",)),
        _boundary("replay", "replay.py", r'REPLAY\s*=\s*"([^"]+)"', ("src/replay.py",)),
    )
    monkeypatch.setattr(versioning, "ROOT", tmp_path)
    monkeypatch.setattr(versioning, "_boundaries", lambda: boundaries)
    monkeypatch.setattr(versioning, "_merge_base", lambda *_args: "base")
    monkeypatch.setattr(
        versioning, "_changed_paths", lambda *_args: ("src/event.py", "src/service.py")
    )
    monkeypatch.setattr(versioning, "_base_version", lambda *_args: "1.2.3")

    updates = versioning.bump("minor", "main", "HEAD")

    assert [item["name"] for item in updates] == ["product", "event"]
    assert '__version__ = "1.3.0"' in product_path.read_text(encoding="utf-8")
    assert 'EVENT = "1.3.0"' in event_path.read_text(encoding="utf-8")
    assert 'REPLAY = "1.2.3"' in replay_path.read_text(encoding="utf-8")
    assert versioning.bump("minor", "main", "HEAD") == []


def test_bump_dry_run_does_not_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """dry-runは更新内容だけを返してfileを変更しない。"""
    path = tmp_path / "version.py"
    path.write_text('VERSION = "1.2.3"\n', encoding="utf-8")
    boundary = _boundary("event", "version.py", r'"([^"]+)"', ("src/",))
    monkeypatch.setattr(versioning, "ROOT", tmp_path)
    monkeypatch.setattr(versioning, "_boundaries", lambda: (boundary,))
    monkeypatch.setattr(versioning, "_merge_base", lambda *_args: "base")
    monkeypatch.setattr(versioning, "_changed_paths", lambda *_args: ("src/event.py",))
    monkeypatch.setattr(versioning, "_base_version", lambda *_args: "1.2.3")

    updates = versioning.bump("patch", "main", "HEAD", dry_run=True)

    assert updates[0]["after"] == "1.2.4"
    assert path.read_text(encoding="utf-8") == 'VERSION = "1.2.3"\n'


def test_bump_refuses_to_overwrite_a_different_manual_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """選択済みの異なるversionを暗黙に上書きしない。"""
    path = tmp_path / "version.py"
    path.write_text('VERSION = "1.4.0"\n', encoding="utf-8")
    boundary = _boundary("event", "version.py", r'"([^"]+)"', ("src/",))
    monkeypatch.setattr(versioning, "ROOT", tmp_path)
    monkeypatch.setattr(versioning, "_boundaries", lambda: (boundary,))
    monkeypatch.setattr(versioning, "_merge_base", lambda *_args: "base")
    monkeypatch.setattr(versioning, "_changed_paths", lambda *_args: ("src/event.py",))
    monkeypatch.setattr(versioning, "_base_version", lambda *_args: "1.2.3")

    with pytest.raises(ValueError, match=r"更新先1\.3\.0"):
        versioning.bump("minor", "main", "HEAD")


@pytest.mark.parametrize(
    ("messages", "expected"),
    [
        (("fix: repair\n\nBREAKING CHANGE: wire format",), "major"),
        (("feat(api)!: replace response",), "major"),
        (("fix: repair", "feat: add option"), "minor"),
        (("fix: repair", "docs: explain"), "patch"),
        ((), "patch"),
    ],
)
def test_suggest_uses_conventional_commit_intent(
    messages: tuple[str, ...], expected: versioning.VersionLevel
) -> None:
    """提案はbreaking、feat、その他の優先順で決める。"""
    assert versioning._suggest_level(messages)[0] == expected

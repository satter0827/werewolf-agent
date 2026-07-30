"""CIとcontainer構成が品質runnerの公開契約に従うことを検査する。"""

import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_quality_workflow_separates_develop_and_main_boundaries() -> None:
    """日常統合はCheck、main境界はDeepと互換性を要求する。"""
    workflow = _read(".github/workflows/quality.yml")

    assert "pull_request:" in workflow
    assert "      - develop" in workflow
    assert "      - main" in workflow
    assert "push:" not in workflow
    assert 'cron: "17 18 * * *"' in workflow
    assert "workflow_dispatch:" in workflow
    assert "name: Develop / Check" in workflow
    assert "name: Main / Source Branch" in workflow
    assert "name: Main / Readiness" in workflow
    assert "name: Main / Compatibility" in workflow
    assert "python -m scripts.quality check" in workflow
    assert "python -m scripts.quality release" not in workflow
    composite = _read(".github/actions/deep-readiness/action.yml")
    assert "python -m scripts.quality deep" in composite
    assert "--confirm-deep" in composite
    assert "--base-ref origin/develop" in workflow
    assert "base-ref: origin/main" in workflow
    assert workflow.count("--head-ref HEAD") == 2
    assert workflow.count("head-ref: HEAD") >= 2
    assert (
        "github.event.pull_request.head.sha" not in workflow.split("\n  nightly-preflight:", 1)[0]
    )
    assert "fetch-depth: 0" in workflow


def test_manual_check_reuses_the_develop_pr_job() -> None:
    """選択branchをPR前に同じLinux Checkで検証する。"""
    workflow = _read(".github/workflows/quality.yml")
    develop_check = workflow.split("\n  develop-check:\n", 1)[1].split("\n  main-source:\n", 1)[0]
    scheduled_deep = workflow.split("\n  scheduled-deep:\n", 1)[1].split(
        "\n  nightly-notify:\n", 1
    )[0]

    assert "inputs.profile == 'check'" in develop_check
    assert "github.base_ref == 'develop'" in develop_check
    assert "--head-ref HEAD" in develop_check
    assert "needs.nightly-preflight.result == 'success'" in scheduled_deep
    assert "nightly-preflight.outputs.force" in scheduled_deep


def test_nightly_deep_is_change_aware_and_weekly_forced() -> None:
    """毎晩のSHA fingerprint再利用と週次強制実行を両立する。"""
    workflow = _read(".github/workflows/quality.yml")
    preflight = workflow.split("\n  nightly-preflight:\n", 1)[1].split("\n  scheduled-deep:\n", 1)[
        0
    ]
    scheduled_deep = workflow.split("\n  scheduled-deep:\n", 1)[1].split(
        "\n  nightly-notify:\n", 1
    )[0]

    assert 'fingerprint="nightly-deep-v1-${main_sha}-${develop_sha}"' in workflow
    assert '"$(date -u +%u)" = "7"' in workflow
    assert "reason=weekly-force" in workflow
    assert "reason=manual-force" in workflow
    assert 'git diff --quiet "$main_sha..$develop_sha"' in workflow
    assert "uses: actions/cache/restore@" in preflight
    assert "continue-on-error: true" in preflight
    assert "lookup-only: true" in preflight
    assert "key: ${{ steps.revisions.outputs.fingerprint }}" in preflight
    assert "steps.success-cache.outcome || 'skipped'" in preflight
    assert "uses: actions/cache/save@" in scheduled_deep
    assert "id: success-cache-save" in scheduled_deep
    assert "continue-on-error: true" in scheduled_deep
    assert "key: ${{ needs.nightly-preflight.outputs.fingerprint }}" in scheduled_deep
    assert "steps.success-cache-save.outcome" in scheduled_deep
    assert scheduled_deep.index("uses: ./.github/actions/deep-readiness") < scheduled_deep.index(
        "uses: actions/cache/save@"
    )


def test_nightly_failure_issue_has_narrow_write_permission() -> None:
    """失敗通知jobだけにissue更新権限を与える。"""
    workflow = _read(".github/workflows/quality.yml")
    notify = workflow.split("\n  nightly-notify:\n", 1)[1]

    assert "permissions:\n      contents: read\n      issues: write" in notify
    assert 'const title = "[CI] Nightly readiness failure"' in notify
    assert "PREFLIGHT_RESULT: ${{ needs.nightly-preflight.result }}" in notify
    assert 'const stage = preflight === "success" ? "deep" : "preflight"' in notify
    assert 'const validSkip = result === "skipped" && !shouldRun' in notify
    assert 'const recovered = preflight === "success"' in notify
    assert 'state: "closed"' in notify
    assert workflow.split("\njobs:\n", 1)[0].count("issues: write") == 0


def test_quality_workflow_pins_the_runner_os_generation() -> None:
    """hosted runnerのOS世代をjob間で統一する。"""
    workflow = _read(".github/workflows/quality.yml")
    jobs = workflow.split("\njobs:\n", 1)[1]
    job_names = re.findall(r"^  ([a-z][a-z0-9-]+):$", jobs, re.MULTILINE)
    runners = re.findall(r"^\s+runs-on:\s+([^\s]+)$", workflow, re.MULTILINE)

    assert len(runners) == len(job_names)
    assert set(runners) == {"ubuntu-24.04"}


def test_quality_workflow_uses_the_repository_environment_command() -> None:
    """取得を伴う準備をrepository内のenvironment commandへ分離する。"""
    workflow = _read(".github/workflows/quality.yml") + _read(
        ".github/actions/deep-readiness/action.yml"
    )

    for command in (
        "python -m scripts.environment setup python",
        "python -m scripts.environment setup quality",
    ):
        assert command in workflow
    assert "python -m scripts.environment setup focus" not in workflow
    assert "python -m scripts.environment setup check" not in workflow
    assert "python -m scripts.environment setup deep" not in workflow
    assert "python -m scripts.quality focus" in workflow
    assert "--pull=false" not in workflow
    assert "supabase stop --no-backup" not in workflow
    assert ".werewolf-agent/operations" not in workflow
    assert ".werewolf-agent/outputs" not in workflow
    assert "retention-days: 7" in workflow


def test_workflow_actions_are_pinned_and_dependabot_targets_develop() -> None:
    """外部Actionをimmutableなreleaseへ固定し、同じ依存を統一する。"""
    sources = _action_sources()
    references, errors = _validate_external_action_references(sources)

    assert references
    assert errors == []
    updates = _dependabot_update_blocks(_read(".github/dependabot.yml"))
    assert set(updates) == {"github-actions", "uv"}
    for update in updates.values():
        assert "target-branch: develop" in update
        assert "interval: weekly" in update
        assert "open-pull-requests-limit: 5" in update
    github_actions = updates["github-actions"]
    cache_group = re.search(
        r"(?ms)^      actions-cache:\s*$\n"
        r"        patterns:\s*$\n"
        r"(?P<patterns>(?:          - .+$\n?)+)",
        github_actions,
    )
    assert cache_group is not None
    assert re.findall(r"^          -\s+(.+?)\s*$", cache_group.group("patterns"), re.MULTILINE) == [
        '"actions/cache*"'
    ]
    assert "groups:" not in updates["uv"]


def test_repository_exposes_standard_community_templates() -> None:
    """公開リポジトリの参加、報告、レビュー入口を固定する。"""
    contributing = _read("CONTRIBUTING.md")
    security = _read("SECURITY.md")
    pull_request = _read(".github/PULL_REQUEST_TEMPLATE.md")
    issue_config = _read(".github/ISSUE_TEMPLATE/config.yml")

    assert "scripts/README.md" in contributing
    assert "公開Issue" in security
    for heading in ("## 目的", "## 変更内容", "## 影響", "## 検証", "## 最終判断"):
        assert heading in pull_request
    assert "develop向けはAIが最新headへの判断を記録" in pull_request
    assert "main向けの正式承認とmergeは人間" in pull_request
    assert "blank_issues_enabled: false" in issue_config
    for filename in ("bug_report.yml", "feature_request.yml"):
        template = _read(f".github/ISSUE_TEMPLATE/{filename}")
        assert "name:" in template
        assert "description:" in template
        assert "validations:" in template


def test_external_action_contract_rejects_mutable_or_inconsistent_references() -> None:
    """更新時に見逃してはならない参照形式と同一依存の不一致を拒否する。"""
    invalid_sources = {
        "mutable-tag.yml": "steps:\n  - uses: actions/checkout@v7 # v7.0.1\n",
        "short-sha.yml": "steps:\n  - uses: actions/checkout@3d3c42e # v7.0.1\n",
        "missing-release.yml": (
            "steps:\n  - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1\n"
        ),
        "unsupported.yml": "steps:\n  - uses: docker://alpine:3\n",
        "inconsistent.yml": (
            "steps:\n"
            "  - uses: actions/cache/restore@"
            "55cc8345863c7cc4c66a329aec7e433d2d1c52a9 # v6.1.0\n"
            "  - uses: actions/cache/save@"
            "27d5ce7f107fe9357f9df03efb73ab90386fccae # v5.0.5\n"
        ),
        "case-inconsistent.yml": (
            "steps:\n"
            "  - uses: Actions/cache/restore@"
            "55cc8345863c7cc4c66a329aec7e433d2d1c52a9 # v6.1.0\n"
            "  - uses: actions/cache/save@"
            "27d5ce7f107fe9357f9df03efb73ab90386fccae # v5.0.5\n"
        ),
    }

    _, errors = _validate_external_action_references(invalid_sources)

    assert len(errors) == len(invalid_sources)
    assert sum("40桁SHAとrelease番号" in error for error in errors) == 4
    assert sum("同じSHAとrelease番号" in error for error in errors) == 2


def test_main_source_rejects_a_same_named_fork_branch() -> None:
    """main release sourceを同一repositoryのdevelopへ限定する。"""
    workflow = _read(".github/workflows/quality.yml")
    source = workflow.split("\n  main-source:\n", 1)[1].split("\n  main-readiness:\n", 1)[0]

    assert "HEAD_REF: ${{ github.head_ref }}" in source
    assert 'test "$HEAD_REF" = "develop"' in source
    assert 'test "${{ github.head_ref }}"' not in source
    assert "github.event.pull_request.head.repo.full_name" in source
    assert 'test "$HEAD_REPOSITORY" = "${{ github.repository }}"' in source
    assert 'test "$HEAD_LABEL" = "${{ github.repository_owner }}:develop"' in source


def test_deep_readiness_does_not_expand_inputs_in_the_shell_source() -> None:
    """composite actionのref入力をshell本文へ直接展開しない。"""
    action = _read(".github/actions/deep-readiness/action.yml")

    assert "BASE_REF: ${{ inputs.base-ref }}" in action
    assert "HEAD_REF: ${{ inputs.head-ref }}" in action
    assert '--base-ref "$BASE_REF"' in action
    assert '--head-ref "$HEAD_REF"' in action
    assert '--base-ref "${{ inputs.base-ref }}"' not in action
    assert '--head-ref "${{ inputs.head-ref }}"' not in action


def test_main_compatibility_matches_supported_python_versions() -> None:
    """primary Python以外の対応版をmain互換性matrixへ含める。"""
    workflow = _read(".github/workflows/quality.yml")
    with (ROOT / "pyproject.toml").open("rb") as stream:
        project = tomllib.load(stream)["project"]
    supported = {
        classifier.rsplit("::", maxsplit=1)[-1].strip()
        for classifier in project["classifiers"]
        if re.fullmatch(r"Programming Language :: Python :: 3\.\d+", classifier)
    }

    assert supported == {"3.11", "3.12", "3.13", "3.14"}
    for version in supported - {"3.12"}:
        assert f'"{version}"' in workflow


def test_rulesets_require_the_stable_workflow_checks() -> None:
    """version管理したrulesetとworkflowの必須check名を一致させる。"""
    workflow = _read(".github/workflows/quality.yml")
    expected = {
        "develop.json": {"Develop / Check"},
        "main.json": {"Main / Source Branch", "Main / Readiness", "Main / Compatibility"},
    }
    for filename, contexts in expected.items():
        document = json.loads(_read(f".github/rulesets/{filename}"))
        status_rule = next(
            rule for rule in document["rules"] if rule["type"] == "required_status_checks"
        )
        actual = {item["context"] for item in status_rule["parameters"]["required_status_checks"]}
        assert actual == contexts
        assert all(f"name: {context}" in workflow for context in contexts)
        pull_request_rule = next(
            rule for rule in document["rules"] if rule["type"] == "pull_request"
        )
        parameters = pull_request_rule["parameters"]
        assert parameters["allowed_merge_methods"] == ["merge"]
        assert parameters["required_approving_review_count"] == 0
        assert parameters["dismiss_stale_reviews_on_push"] is False
        assert parameters["require_code_owner_review"] is False
        assert parameters["require_last_push_approval"] is False
        assert parameters["required_review_thread_resolution"] is (filename == "main.json")


def test_backend_dev_image_contains_the_test_suite() -> None:
    """container test用stageへ検証対象を含める。"""
    dockerfile = _read("docker/backend.Dockerfile")

    dev = dockerfile.split("FROM dev-dependencies AS dev", 1)[1].split(
        "FROM runtime-dependencies AS runtime", 1
    )[0]
    for copied_path in (".codex", ".github", "docker", "docs", "notebooks", "tests"):
        assert f"COPY {copied_path}" in dev
    assert "contracts/openapi.json" in dev


def test_compose_exposes_isolated_runtime_and_test_services() -> None:
    """品質対象serviceと秘密情報の境界を維持する。"""
    compose = _read("compose.yaml")

    assert "worker:" in compose
    assert 'profiles: ["dev", "e2e", "production"]' in compose
    assert "command: werewolf-agent-worker run" in compose
    assert 'profiles: ["test"]' in compose
    assert "test:" in compose
    assert "command: pytest" in compose
    streamlit_config = _read(".streamlit/config.toml")
    assert "gatherUsageStats = false" in streamlit_config
    assert "--browser.gatherUsageStats" not in compose
    assert "WEREWOLF_LOG_OUTPUT: ${WEREWOLF_LOG_OUTPUT:-stdout}" in compose
    test_service = compose.split("\n  test:\n", 1)[1].split("\n  e2e:\n", 1)[0]
    assert "WEREWOLF_SUPABASE_" not in test_service
    worker = compose.split("  worker:", 1)[1].split("  streamlit:", 1)[0]
    assert "OPENAI_API_KEY:" in worker
    for service in ("api", "streamlit"):
        section = compose.split(f"  {service}:", 1)[1].split("\n  ", 1)[0]
        assert "OPENAI_API_KEY:" not in section


def test_documented_validation_commands_match_repo_tooling() -> None:
    """利用者向け文書から共通runnerへ到達できる。"""
    docs = "\n".join(
        [
            _read("README.md"),
            _read("docs/design/verification.md"),
            _read("scripts/README.md"),
            _read("AGENTS.md"),
        ]
    )
    pyproject = _read("pyproject.toml")

    for command in (
        "python -m scripts.quality auto",
        "python -m scripts.quality focus",
        "python -m scripts.quality check",
        "python -m scripts.quality release",
        "python -m scripts.quality deep --confirm-deep",
        "python -m scripts.quality clean",
    ):
        assert command in docs
    assert "[tool.werewolf-quality]" in pyproject
    assert 'testpaths = ["tests"]' in pyproject


def test_ignore_files_exclude_secrets_and_current_generated_state() -> None:
    """GitとDockerの入力から秘密情報と現行runtime成果物を除外する。"""
    gitignore = _read(".gitignore")
    dockerignore = _read(".dockerignore")

    for pattern in (
        ".env",
        "!.env.example",
        ".streamlit/secrets.toml",
        "signing_keys.json",
        "credentials.json",
        "*.pem",
        "*.key",
        "/.werewolf-agent/",
        "/supabase/.temp/",
        "*.sqlite3-*",
        "*.db-*",
    ):
        assert pattern in gitignore
    for pattern in (
        ".streamlit/secrets.toml",
        "**/signing_keys.json",
        "supabase/**/secrets.*",
        "**/credentials.json",
        "**/*.pem",
        "**/*.key",
        ".werewolf-agent",
        "*.sqlite3-*",
        "*.db-*",
    ):
        assert pattern in dockerignore
    assert "/front-web/" not in gitignore
    assert "/frontend/" not in gitignore
    assert "/.vscode/" not in gitignore


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _action_sources() -> dict[str, str]:
    paths = sorted((ROOT / ".github/workflows").rglob("*.yml"))
    paths.extend(sorted((ROOT / ".github/workflows").rglob("*.yaml")))
    for pattern in ("action.yml", "action.yaml"):
        paths.extend(sorted((ROOT / ".github/actions").rglob(pattern)))
    return {path.relative_to(ROOT).as_posix(): path.read_text(encoding="utf-8") for path in paths}


def _dependabot_update_blocks(source: str) -> dict[str, str]:
    starts = list(
        re.finditer(
            r"^  - package-ecosystem:\s+(?P<ecosystem>[^\s#]+)\s*$",
            source,
            re.MULTILINE,
        )
    )
    blocks: dict[str, str] = {}
    for index, match in enumerate(starts):
        ecosystem = match.group("ecosystem").strip("\"'")
        if ecosystem in blocks:
            raise AssertionError(f"Dependabotの{ecosystem}設定が重複しています")
        end = starts[index + 1].start() if index + 1 < len(starts) else len(source)
        blocks[ecosystem] = source[match.start() : end]
    return blocks


def _validate_external_action_references(
    sources: dict[str, str],
) -> tuple[list[tuple[str, str, str]], list[str]]:
    use_line = re.compile(r"^\s*-?\s*uses:\s*(?P<value>.+?)\s*$")
    pinned = re.compile(
        r"^(?P<owner>[A-Za-z0-9_.-]+)/(?P<repository>[A-Za-z0-9_.-]+)"
        r"(?:/[A-Za-z0-9_.\-/]+)?@(?P<sha>[0-9a-f]{40})"
        r"\s+#\s+(?P<version>v(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*))$"
    )
    references: list[tuple[str, str, str]] = []
    errors: list[str] = []
    identities: dict[str, tuple[str, str]] = {}
    for path, source in sources.items():
        for line_number, line in enumerate(source.splitlines(), start=1):
            use_match = use_line.fullmatch(line)
            if use_match is None:
                continue
            value = use_match.group("value")
            if value.startswith("./"):
                continue
            pin_match = pinned.fullmatch(value)
            if pin_match is None:
                errors.append(f"{path}:{line_number}: 外部Actionは40桁SHAとrelease番号で固定する")
                continue
            identity = f"{pin_match.group('owner')}/{pin_match.group('repository')}".casefold()
            revision = pin_match.group("sha")
            version = pin_match.group("version")
            references.append((identity, revision, version))
            expected = identities.setdefault(identity, (revision, version))
            if expected != (revision, version):
                errors.append(f"{path}:{line_number}: {identity}は同じSHAとrelease番号へ統一する")
    return references, errors

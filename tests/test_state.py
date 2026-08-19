from repo_infra.remote import Facts
from repo_infra.state import classify_files, classify_remote

MANIFEST = {"assets": {}, "ci_blocks": {}, "actions": {}}
ASSET = "name: CI\n# repo-infra: ci v3\n\njobs:\n  # repo-infra: ci-rust v2\n  fmt:\n"


def write(tmp_path, text):
    target = tmp_path / ".github/workflows/ci.yml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return {".github/workflows/ci.yml": ASSET}


def states(items):
    return {item.name: item.state for item in items}


def test_a_file_that_is_not_there_is_missing(tmp_path):
    rendered = {".github/workflows/ci.yml": ASSET}
    assert states(classify_files(tmp_path, rendered, MANIFEST)) == {"ci": "missing", "ci-rust": "missing"}


def test_matching_markers_and_matching_content_are_ok(tmp_path):
    rendered = write(tmp_path, ASSET)
    assert states(classify_files(tmp_path, rendered, MANIFEST)) == {"ci": "ok", "ci-rust": "ok"}


def test_local_edits_at_the_current_version_stay_ok(tmp_path):
    rendered = write(tmp_path, ASSET.replace("fmt:", "fmt:\n    timeout-minutes: 30"))
    items = {item.name: item for item in classify_files(tmp_path, rendered, MANIFEST)}
    assert items["ci"].state == "ok"
    assert "local edits" in items["ci"].detail


def test_an_older_marker_is_outdated_per_block(tmp_path):
    rendered = write(tmp_path, ASSET.replace("ci-rust v2", "ci-rust v1"))
    items = {item.name: item for item in classify_files(tmp_path, rendered, MANIFEST)}
    assert items["ci"].state == "ok"
    assert items["ci-rust"].state == "outdated"
    assert items["ci-rust"].detail == "v1 installed, v2 available"


def test_a_newer_marker_is_a_conflict_because_the_plugin_is_behind(tmp_path):
    rendered = write(tmp_path, ASSET.replace("ci v3", "ci v9"))
    items = {item.name: item for item in classify_files(tmp_path, rendered, MANIFEST)}
    assert items["ci"].state == "conflict"
    assert "newer" in items["ci"].detail


def test_an_installed_file_with_no_marker_is_a_conflict_not_an_overwrite(tmp_path):
    rendered = write(tmp_path, "name: CI\njobs:\n  fmt:\n")
    items = {item.name: item for item in classify_files(tmp_path, rendered, MANIFEST)}
    assert items["ci"].state == "conflict"
    assert "not managed" in items["ci"].detail


def facts(**overrides):
    base = dict(default_branch="main", protected=True,
                required_contexts={"ci-passed", "changelog-updated"},
                labels={"no-changelog"}, workflow_permissions="write", can_approve_pr=True)
    base.update(overrides)
    return Facts(**base)


def test_a_conforming_repository_reports_every_remote_item_ok():
    assert set(states(classify_remote(facts())).values()) == {"ok"}


def test_a_master_branch_is_a_conflict_and_is_reported_first():
    items = classify_remote(facts(default_branch="master"))
    assert items[0].name == "default-branch"
    assert items[0].state == "conflict"
    assert "main" in items[0].detail


def test_a_missing_required_context_is_missing_not_ok():
    items = states(classify_remote(facts(required_contexts={"ci-passed"})))
    assert items["required-checks"] == "missing"


def test_a_missing_label_is_reported_because_dependabot_will_not_create_it():
    assert states(classify_remote(facts(labels=set())))["no-changelog-label"] == "missing"


def test_actions_that_cannot_open_a_pull_request_is_missing():
    assert states(classify_remote(facts(can_approve_pr=False)))["actions-open-pr"] == "missing"


def test_a_skipped_item_keeps_its_reason_and_leaves_the_attention_count(tmp_path):
    from repo_infra.state import classify

    config = tmp_path / ".github/repo-infra.json"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text('{"skip": {"ci": "hand-written CI, deliberately"}}\n', encoding="utf-8")
    rendered = {".github/workflows/ci.yml": ASSET}
    items = {i.name: i for i in classify(tmp_path, rendered, MANIFEST, facts())}
    assert items["ci"].state == "skipped"
    assert items["ci"].detail == "hand-written CI, deliberately"
    assert items["ci-rust"].state == "missing"


# --- Addition 1: a path filter on a target repository's required workflows --

CI_WITH_FILTER = (
    "name: CI\n"
    "# repo-infra: ci v3\n"
    "on:\n"
    "  pull_request:\n"
    "    paths:\n"
    "      - 'src/**'\n"
    "jobs:\n"
    "  # repo-infra: ci-rust v2\n"
    "  fmt:\n"
)

CI_WITH_FILTER_COMMENT_ONLY = (
    "name: CI\n"
    "# repo-infra: ci v3\n"
    "# Never add paths: or paths-ignore: to this workflow (spec D13).\n"
    "jobs:\n"
    "  # repo-infra: ci-rust v2\n"
    "  fmt:\n"
)


def test_a_required_workflow_carrying_a_real_path_filter_is_a_conflict(tmp_path):
    rendered = write(tmp_path, CI_WITH_FILTER)
    items = {item.name: item for item in classify_files(tmp_path, rendered, MANIFEST)}
    assert items["ci"].state == "conflict"
    assert "ci.yml" in items["ci"].detail
    assert "job" in items["ci"].detail


def test_a_required_workflow_mentioning_paths_only_in_a_comment_is_not_a_conflict(tmp_path):
    rendered = write(tmp_path, CI_WITH_FILTER_COMMENT_ONLY)
    items = {item.name: item for item in classify_files(tmp_path, rendered, MANIFEST)}
    assert items["ci"].state == "ok"

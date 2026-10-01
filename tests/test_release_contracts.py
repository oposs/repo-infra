"""check's release contracts: release_files, release-build-local, Gitea config."""

import pathlib

import pytest

from repo_infra.detect import Detection
from repo_infra.state import classify_contracts, refused_release_files

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSETS = ROOT / "skills/repo-infra/assets"


def result(tmp_path):
    return Detection.load(ASSETS / "detection.json").detect(tmp_path)


@pytest.mark.parametrize("entry", [
    "CHANGES.md", "./CHANGES.md", "Formula/../CHANGES.md", "Cargo.toml",
    ".github/repo-infra.json", ".github//workflows/ci.yml", "/etc/passwd", "../x", "",
])
def test_check_refuses_a_release_file_that_reopens_the_channel(entry):
    assert [p for p, _ in refused_release_files([entry], [{"path": "Cargo.toml"}])] == [entry]


def test_check_accepts_the_formula():
    assert refused_release_files(["Formula/mdmost.rb"], [{"path": "Cargo.toml"}]) == []


GITEA_OK = {"url": "https://gitea.example.org", "owner": "acme"}
SEAM_OK = ("on:\n  workflow_call:\n    inputs:\n      ref:\n        type: string\n"
           "jobs:\n  a:\n    runs-on: x\n    steps:\n      - uses: actions/checkout@v7\n"
           "        with:\n          ref: ${{ inputs.ref }}\n")
SEAM_NO_REF = "on: [workflow_call]\njobs:\n  a:\n    runs-on: x\n    steps:\n      - run: true\n"


def write(tmp_path, name, text):
    (tmp_path / ".github/workflows").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".github/workflows" / name).write_text(text)


def test_release_build_local_without_its_file_is_a_conflict(tmp_path):
    items = classify_contracts(tmp_path, result(tmp_path), {"release_build_local": True})
    assert [(i.name, i.state) for i in items] == [("release-build-local", "conflict")]
    assert ".github/workflows/release-build-local.yml" in items[0].detail


def test_the_d26_contract_items_are_gone(tmp_path):
    items = classify_contracts(tmp_path, result(tmp_path), {
        "release_build": True, "publish": ["publish-gitea-packages"],
        "gitea_packages": GITEA_OK})
    assert items == []


@pytest.mark.parametrize("key,name,item", [
    ("ci_local", "ci-local.yml", "ci-local-seam"),
    ("release_build_local", "release-build-local.yml", "release-build-local-seam"),
])
def test_a_seam_without_ref_is_a_conflict_naming_the_file(tmp_path, key, name, item):
    write(tmp_path, name, SEAM_NO_REF)
    items = classify_contracts(tmp_path, result(tmp_path), {key: True})
    assert [(i.name, i.state) for i in items] == [(item, "conflict")]
    assert f".github/workflows/{name}" in items[0].detail
    assert "declares no workflow_call input `ref`" in items[0].detail


def test_the_action_test_seam_is_checked_too(tmp_path):
    (tmp_path / "action.yml").write_text("name: x\n")
    write(tmp_path, "action-test.yml", SEAM_NO_REF)
    items = classify_contracts(tmp_path, result(tmp_path), {})
    assert [(i.name, i.state) for i in items] == [("action-test-seam", "conflict")]


def test_ci_local_may_not_upload_a_release_asset(tmp_path):
    write(tmp_path, "ci-local.yml", SEAM_OK + "      - uses: actions/upload-artifact@v7\n"
          "        with:\n          name: release-files\n          path: x\n")
    (item,) = classify_contracts(tmp_path, result(tmp_path), {"ci_local": True})
    assert item.name == "ci-local-seam" and "release-files" in item.detail
    # Only the name is wrong: the advice is to rename, not to add `ref`.
    assert "inputs: ref" not in item.detail and "another name" in item.detail


def test_a_seam_without_ref_and_with_a_reserved_name_gets_both_advices(tmp_path):
    write(tmp_path, "ci-local.yml", SEAM_NO_REF + "      - uses: actions/upload-artifact@v7\n"
          "        with:\n          name: release-files\n          path: x\n")
    (item,) = classify_contracts(tmp_path, result(tmp_path), {"ci_local": True})
    assert "inputs: ref" in item.detail and "another name" in item.detail


def test_release_build_local_may_upload_release_assets(tmp_path):
    write(tmp_path, "release-build-local.yml", SEAM_OK + "      - uses: actions/upload-artifact@v7\n"
          "        with:\n          name: release-asset-linux\n          path: x\n")
    assert classify_contracts(tmp_path, result(tmp_path), {"release_build_local": True}) == []


def test_a_pending_rename_checks_the_d26_file_under_the_new_name(tmp_path):
    write(tmp_path, "release-build.yml", SEAM_NO_REF)
    items = classify_contracts(tmp_path, result(tmp_path), {"release_build_local": True},
                               pending_rename=True)
    assert [(i.name, i.state) for i in items] == [("release-build-local-seam", "conflict")]


def test_a_refused_release_file_is_a_conflict(tmp_path):
    config = {"release_files": ["./CHANGES.md"], "version_files": []}
    items = classify_contracts(tmp_path, result(tmp_path), config)
    assert [(i.name, i.state) for i in items] == [("release-files", "conflict")]
    assert "./CHANGES.md" in items[0].detail


def gitea_config(tmp_path, **over):
    config = {"publish": ["publish-gitea-packages"], "gitea_packages": GITEA_OK}
    config.update(over)
    return classify_contracts(tmp_path, result(tmp_path), config)


def test_gitea_packages_with_its_config_is_fine(tmp_path):
    assert gitea_config(tmp_path) == []


@pytest.mark.parametrize("packages,absent", [
    (None, "url and owner"),
    ({"owner": "acme"}, "url"),
    ({"url": "https://gitea.example.org"}, "owner"),
])
def test_gitea_packages_without_url_or_owner_is_a_conflict(tmp_path, packages, absent):
    config = {"gitea_packages": packages} if packages is not None else {"gitea_packages": None}
    items = gitea_config(tmp_path, **config)
    assert [(i.name, i.state) for i in items] == [("gitea-packages-config", "conflict")]
    assert absent in items[0].detail

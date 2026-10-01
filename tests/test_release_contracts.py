"""check's release contracts: release_files, release-build-local, Gitea config."""

import json
import pathlib

import pytest

from repo_infra.detect import Detection
from repo_infra.state import classify_contracts, refused_release_files

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSETS = ROOT / "skills/repo-infra/assets"
MANIFEST = json.loads((ASSETS / "manifest.json").read_text(encoding="utf-8"))


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


def test_release_build_without_the_project_build_is_a_conflict(tmp_path):
    items = classify_contracts(tmp_path, result(tmp_path), {"release_build": True})
    assert [(i.name, i.state) for i in items] == [("release-build", "conflict")]


def test_a_refused_release_file_is_a_conflict(tmp_path):
    (tmp_path / ".github/workflows").mkdir(parents=True)
    (tmp_path / ".github/workflows/release-build.yml").write_text("on: [workflow_call]\n")
    config = {"release_build": True, "release_files": ["./CHANGES.md"], "version_files": []}
    items = classify_contracts(tmp_path, result(tmp_path), config)
    assert [(i.name, i.state) for i in items] == [("release-files", "conflict")]
    assert "./CHANGES.md" in items[0].detail


GITEA_OK = {"url": "https://gitea.example.org", "owner": "acme"}


def gitea_config(tmp_path, **over):
    (tmp_path / ".github/workflows").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".github/workflows/release-build.yml").write_text("on: [workflow_call]\n")
    config = {"publish": ["publish-gitea-packages"], "release_build": True,
              "gitea_packages": GITEA_OK}
    config.update(over)
    return classify_contracts(tmp_path, result(tmp_path), config)


def test_gitea_packages_with_release_build_and_config_is_fine(tmp_path):
    assert gitea_config(tmp_path) == []


def test_gitea_packages_without_release_build_is_a_conflict(tmp_path):
    items = gitea_config(tmp_path, release_build=False)
    assert [(i.name, i.state) for i in items] == [("gitea-packages-build", "conflict")]
    assert "release_build" in items[0].detail


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

"""One naming convention for everything a v2 caller writes (D33).

The interface of the pieces freezes at 2.0.0, so a name that slips through
here stays until v3:

- workflow_call inputs and outputs, workflow_dispatch inputs, and keys of
  .github/repo-infra.json: snake_case;
- workflow_call secrets and the repository variables a workflow reads:
  UPPER_SNAKE, and a call passes each secret under the name of the
  repository secret it reads (`GITEA_PACKAGE_TOKEN: ${{ secrets.GITEA_PACKAGE_TOKEN }}`);
- job ids, step ids, artifact names and workflow file names: kebab-case.

Names a third-party action imposes, such as the `node-version` input of
actions/setup-node, are a step's `with:` and are not checked.
"""

import json
import pathlib
import re

import pytest
import yaml

from repo_infra import check
from repo_infra.pieces import ASSETS

ROOT = pathlib.Path(__file__).resolve().parents[1]
SNAKE = re.compile(r"[a-z][a-z0-9]*(_[a-z0-9]+)*")
UPPER = re.compile(r"[A-Z][A-Z0-9]*(_[A-Z0-9]+)*")
KEBAB = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
EXPRESSION = re.compile(r"\$\{\{.*?\}\}")
SECRET_REF = re.compile(r"\$\{\{ secrets\.([A-Za-z0-9_]+) \}\}")
VARS = re.compile(r"\bvars\.([A-Za-z0-9_-]+)")

WORKFLOWS = sorted((ROOT / ".github/workflows").glob("*.yml")) + sorted(
    (ASSETS / "callers").glob("*.yml"))
EXAMPLES = sorted((ASSETS.parent / "references/examples").glob("*/*.yml"))
CONFIGS = [ROOT / ".github/repo-infra.json"] + sorted(
    (ASSETS.parent / "references/examples").glob("*/repo-infra.json"))


def rel(path):
    return str(path.relative_to(ROOT))


def load(path):
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    return doc if isinstance(doc, dict) else {}


def trigger(doc, event):
    on = doc.get("on", doc.get(True))
    found = on.get(event) if isinstance(on, dict) else None
    return found if isinstance(found, dict) else {}


def workflow_call(doc):
    return trigger(doc, "workflow_call")


def jobs(doc):
    found = doc.get("jobs")
    return found if isinstance(found, dict) else {}


def artifact_names(step):
    """The names an artifact step writes or reads, with every expression and
    glob replaced by a stand-in, so `release-asset-${{ matrix.os }}` checks as
    `release-asset-x`. The value of a matrix variable is data: a Rust target
    triple such as x86_64-unknown-linux-musl is spelt the way rustc spells it."""
    uses = str(step.get("uses", ""))
    if not re.match(r"actions/(upload|download)-artifact@", uses):
        return []
    with_ = step.get("with") or {}
    return [EXPRESSION.sub("x", str(with_[key])).replace("*", "x")
            for key in ("name", "pattern") if key in with_]


def problems(path):
    doc = load(path)
    found = []
    if not KEBAB.fullmatch(path.stem):
        found.append(f"file name {path.name}")
    call = workflow_call(doc)
    for kind, rule in (("inputs", SNAKE), ("outputs", SNAKE), ("secrets", UPPER)):
        for name in call.get(kind) or {}:
            if not rule.fullmatch(name):
                found.append(f"workflow_call {kind[:-1]} {name}")
    for name in trigger(doc, "workflow_dispatch").get("inputs") or {}:
        if not SNAKE.fullmatch(name):
            found.append(f"workflow_dispatch input {name}")
    for job_id, job in jobs(doc).items():
        if not KEBAB.fullmatch(job_id):
            found.append(f"job id {job_id}")
        if not isinstance(job, dict):
            continue
        if "uses" in job:
            for name in job.get("with") or {}:
                if not SNAKE.fullmatch(name):
                    found.append(f"job {job_id} passes input {name}")
            secrets = job.get("secrets")
            for name, value in (secrets.items() if isinstance(secrets, dict) else ()):
                ref = SECRET_REF.fullmatch(str(value))
                if not UPPER.fullmatch(name):
                    found.append(f"job {job_id} passes secret {name}")
                elif ref and ref[1] != name:
                    found.append(f"job {job_id} passes secrets.{ref[1]} as {name}")
        for step in job.get("steps") or []:
            if "id" in step and not KEBAB.fullmatch(str(step["id"])):
                found.append(f"job {job_id} step id {step['id']}")
            for name in artifact_names(step):
                if not KEBAB.fullmatch(name):
                    found.append(f"job {job_id} artifact {name}")
    for name in VARS.findall(path.read_text(encoding="utf-8")):
        if not UPPER.fullmatch(name):
            found.append(f"variable {name}")
    return found


@pytest.mark.parametrize("path", WORKFLOWS + EXAMPLES, ids=rel)
def test_every_name_follows_the_convention(path):
    assert problems(path) == []


def test_the_workflow_set_holds_the_pieces_and_the_callers():
    names = {rel(p) for p in WORKFLOWS}
    assert ".github/workflows/ri-publish-tag.yml" in names
    assert ".github/workflows/ri-ci-repo-infra-selftest.yml" in names
    assert "skills/repo-infra/assets/callers/ci-passed.yml" in names


@pytest.mark.parametrize("bad, said", [
    ("on:\n  workflow_call:\n    inputs:\n      release-type: {type: string}\n",
     "workflow_call input release-type"),
    ("on:\n  workflow_call:\n    outputs:\n      Mode: {value: x}\n", "workflow_call output Mode"),
    ("on:\n  workflow_call:\n    secrets:\n      app-client-id: {required: false}\n",
     "workflow_call secret app-client-id"),
    ("on:\n  workflow_dispatch:\n    inputs:\n      release-type: {type: choice}\n",
     "workflow_dispatch input release-type"),
    ("jobs:\n  ci_passed:\n    runs-on: x\n", "job id ci_passed"),
    ("jobs:\n  a:\n    steps:\n      - id: make_plan\n", "job a step id make_plan"),
    ("jobs:\n  a:\n    steps:\n      - uses: actions/upload-artifact@v7\n"
     "        with:\n          name: release_files\n", "job a artifact release_files"),
    ("jobs:\n  a:\n    uses: o/r/.github/workflows/x.yml@v2\n    secrets:\n"
     "      TOKEN: ${{ secrets.GITEA_PACKAGE_TOKEN }}\n",
     "job a passes secrets.GITEA_PACKAGE_TOKEN as TOKEN"),
    ("jobs:\n  a:\n    uses: o/r/.github/workflows/x.yml@v2\n    with:\n      release-type: x\n",
     "job a passes input release-type"),
    ("jobs:\n  a:\n    env:\n      U: ${{ vars.gitea_user }}\n", "variable gitea_user"),
])
def test_the_check_catches_each_kind(tmp_path, bad, said):
    path = tmp_path / "w.yml"
    path.write_text(bad, encoding="utf-8")
    assert said in problems(path)


def test_an_expression_in_an_artifact_name_is_not_judged():
    step = {"uses": "actions/upload-artifact@v7",
            "with": {"name": "release-asset-${{ matrix.target }}"}}
    assert artifact_names(step) == ["release-asset-x"]


def config_keys(value):
    """Every key of a repo-infra.json, except the rule ids under `exceptions`,
    which are kebab-case ids from references/project-shape.md."""
    if isinstance(value, list):
        return [k for item in value for k in config_keys(item)]
    if not isinstance(value, dict):
        return []
    found = []
    for key, child in value.items():
        found.append(key)
        if key != "exceptions":
            found += config_keys(child)
    return found


@pytest.mark.parametrize("path", CONFIGS, ids=rel)
def test_repo_infra_json_keys_are_snake_case(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    assert [k for k in config_keys(data) if not SNAKE.fullmatch(k)] == []


def test_the_keys_check_knows_are_snake_case():
    assert [k for k in check.KEYS if not SNAKE.fullmatch(k)] == []

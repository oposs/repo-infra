# skills/repo-infra/scripts/repo_infra/callers.py
"""Validate the callers against what they call (D30).

A caller is a workflow the repository owns: ci.yml, release-build.yml,
release-publish.yml, ci-local.yml. It calls pieces with
`uses: ./.github/workflows/<file>.yml`, and GitHub checks such a call only
when the run starts, so a misspelt input or a missing secret surfaces as a
red run on main. Everything here is read from the files as they are
installed: the interface of the called file, never a list kept beside it.
"""

import pathlib
import re

from . import workflow
from .pieces import ASSETS
from .report import Item

WORKFLOWS = ".github/workflows"
CORE_CALLERS = {
    "ci.yml": "the ruleset requires its ci-passed check, and Create release PR runs it",
    "release-build.yml": "Create release PR calls it to build the release",
    "release-publish.yml": "it tags and publishes a release once its pull request merges",
}
# The job that closes each file and what it does wrong when it does not wait
# for a job. The needs: list used to be generated; now check verifies it.
CLOSING = {
    "ci.yml": ("ci-passed", "report green while that job fails"),
    "release-publish.yml": ("finalize", "publish the release before that job attached its files"),
}
_REMOTE = re.compile(r"^[\w.-]+/[\w.-]+/\.github/workflows/[^@]+@")
# GitHub reads context names in an expression case-insensitively.
_INPUT_REF = re.compile(r"\$\{\{\s*inputs\.ref\s*\}\}", re.IGNORECASE)
_RESERVED = re.compile(r"^(release-asset-.*|release-files)$", re.IGNORECASE)


def read_workflows(repo_root):
    """{file name: parsed workflow, or its ReadError} for each file GitHub runs."""
    folder = pathlib.Path(repo_root) / WORKFLOWS
    docs = {}
    if not folder.is_dir():
        return docs
    for path in sorted(folder.iterdir()):
        if path.is_file() and path.suffix in (".yml", ".yaml"):
            try:
                docs[path.name] = workflow.load(path.read_text(encoding="utf-8"))
            except workflow.ReadError as error:
                docs[path.name] = error
    return docs


def jobs(doc):
    found = doc.get("jobs") if isinstance(doc, dict) else None
    if not isinstance(found, dict):
        return {}
    return {name: job for name, job in found.items() if isinstance(job, dict)}


def local_target(uses):
    prefix = f"./{WORKFLOWS}/"
    if isinstance(uses, str) and uses.startswith(prefix):
        return uses[len(prefix):]
    return None


def needs(job):
    value = job.get("needs", [])
    if isinstance(value, str):
        return [value] if value else []
    return [v for v in value if isinstance(v, str)] if isinstance(value, list) else []


def calls(docs, target):
    return any(local_target(job.get("uses")) == target
               for doc in docs.values() for job in jobs(doc).values())


def call_problems(job_id, job, docs):
    """What GitHub would refuse about job `job_id` calling a local workflow."""
    called = local_target(job.get("uses"))
    target = docs.get(called)
    where = f"job {job_id} calls {called}"
    if target is None:
        return [f"{where}, which does not exist"]
    if isinstance(target, workflow.ReadError):
        return []
    face = workflow.interface(target)
    if face is None:
        return [f"{where}, which has no `on: workflow_call` trigger"]
    given = job.get("with") if isinstance(job.get("with"), dict) else {}
    found = [f"{where} with the input {key}, which {called} does not declare"
             for key in given if key not in face.inputs]
    found += [f"{where} without its required input {key}"
              for key, spec in face.inputs.items() if spec["required"] and key not in given]
    secrets = job.get("secrets")
    if secrets != "inherit":
        passed = secrets if isinstance(secrets, dict) else {}
        found += [f"{where} with the secret {key}, which {called} does not declare"
                  for key in passed if key not in face.secrets]
        found += [f"{where} without its required secret {key}; pass it, or write "
                  "`secrets: inherit`"
                  for key, spec in face.secrets.items()
                  if spec["required"] and key not in passed]
    return found


def _without_needs(job):
    return {key: value for key, value in job.items() if key != "needs"}


def closing_problems(docs, assets=ASSETS):
    pattern = jobs(workflow.load(
        (pathlib.Path(assets) / "callers/ci-passed.yml").read_text(encoding="utf-8")))
    found = []
    for name, (closer, harm) in CLOSING.items():
        doc = docs.get(name)
        if not isinstance(doc, dict):
            continue
        all_jobs = jobs(doc)
        job = all_jobs.get(closer)
        if job is None:
            found.append((name, f"has no {closer} job"))
            continue
        missing = [other for other in all_jobs if other != closer and other not in needs(job)]
        if missing:
            found.append((name, f"{closer} does not need {', '.join(missing)}; it would {harm}"))
        if closer != "ci-passed":
            continue
        if job.get("if") != "always()":
            found.append((name, "ci-passed lacks `if: always()`: a failed job would skip it, "
                                "and a skipped required check counts as passed"))
        elif _without_needs(job) != _without_needs(pattern["ci-passed"]):
            found.append((name, "ci-passed differs from the pattern (assets/callers/"
                                "ci-passed.yml in the repo-infra skill); copy it word for "
                                "word and keep only your needs: list"))
    return found


def ref_problems(doc, reserved, skip=()):
    """D28: every checkout takes `ref`, and only the release build uploads
    release-asset-* or release-files."""
    found = []
    for job_id, job in jobs(doc).items():
        if job_id in skip:
            continue
        steps = job.get("steps") if isinstance(job.get("steps"), list) else []
        for step in steps:
            if not isinstance(step, dict):
                continue
            uses = str(step.get("uses", "")).lower()
            given = step.get("with") if isinstance(step.get("with"), dict) else {}
            if uses.startswith("actions/checkout@"):
                if not _INPUT_REF.fullmatch(str(given.get("ref", "")).strip()):
                    found.append(f"job {job_id} has an actions/checkout step without "
                                 "`ref: ${{ inputs.ref }}`; it would test main while the "
                                 "release pull request says it tested the release (D28)")
            elif reserved and uses.startswith("actions/upload-artifact@"):
                artifact = str(given.get("name", ""))
                if _RESERVED.match(artifact):
                    found.append(f"job {job_id} uploads an artifact named {artifact}, a "
                                 "name reserved for the release build")
    return found


def ref_contract_problems(docs, piece_files):
    found = []
    for name, reserved, skip in (("ci.yml", True, ("ci-passed",)),
                                 ("release-build.yml", False, ())):
        if isinstance(docs.get(name), dict):
            found += [(name, p) for p in ref_problems(docs[name], reserved, skip)]
    for name, doc in docs.items():
        for job in jobs(doc).values():
            called = local_target(job.get("uses"))
            given = job.get("with") if isinstance(job.get("with"), dict) else {}
            if (called is None or called in piece_files or called in CLOSING
                    or called == "release-build.yml" or "ref" not in given
                    or not isinstance(docs.get(called), dict)):
                continue
            found += [(called, p) for p in
                      ref_problems(docs[called], reserved=name != "release-build.yml")]
    return list(dict.fromkeys(found))


def validate(docs, pieces, assets=ASSETS):
    piece_files = {pathlib.PurePosixPath(p.target).name
                   for p in pieces.values() if p.workflow}
    items = [Item("callers", name, "problem", f"cannot be read: {doc}")
             for name, doc in docs.items() if isinstance(doc, workflow.ReadError)]
    items += [Item("callers", name, "missing", f"not there; {why}")
              for name, why in CORE_CALLERS.items() if name not in docs]
    for name, doc in docs.items():
        for job_id, job in jobs(doc).items():
            uses = job.get("uses")
            if isinstance(uses, str) and _REMOTE.match(uses):
                items.append(Item("callers", name, "problem",
                                  f"job {job_id} calls {uses}, a workflow in another "
                                  "repository; every workflow stays local (D30): copy the "
                                  "piece"))
            elif local_target(uses):
                items += [Item("callers", name, "problem", p)
                          for p in call_problems(job_id, job, docs)]
    found = closing_problems(docs, assets) + ref_contract_problems(docs, piece_files)
    return items + [Item("callers", name, "problem", detail) for name, detail in found]

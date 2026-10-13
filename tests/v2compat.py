"""What v2 consumers notice (D33): the comparison test_v2_compat.py runs
between the pieces of the commit v2 points at and the pieces now."""

import re
import subprocess

from repo_infra import callers, workflow

_NAMES = {0: "none", 1: "read", 2: "write"}
_RELEASE = re.compile(r"v2\.\d+\.\d+")


def _over(have, had):
    return {s: lv for s, lv in have.items() if lv > had.get(s, 0)}


def _text(levels):
    return ", ".join(f"{s}: {_NAMES[lv]}" for s, lv in sorted(levels.items()))


def git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)


def v2_source(repo, required):
    """What the comparison does in a checkout: ("compare", commit) when the tag
    v2 exists, ("fail", why) when a 2.x release exists but v2 was not moved and
    the job requires the comparison, else ("skip", why)."""
    found = git(repo, "rev-parse", "--verify", "--quiet", "refs/tags/v2^{commit}")
    if found.returncode == 0:
        return "compare", found.stdout.strip()
    tags = git(repo, "tag", "--list", "v2.*").stdout.split()
    if required and any(_RELEASE.fullmatch(t) for t in tags):
        return "fail", ("this checkout has a 2.x release tag but no tag v2; "
                        "the release did not move v2, or the job did not fetch tags")
    return "skip", "no tag v2 in this checkout (shallow clone, or before 2.0.0)"


def interface_problems(name, old, new):
    before, after = workflow.interface(old), workflow.interface(new)
    found = []
    for key, spec in before.inputs.items():
        now = after.inputs.get(key)
        if now is None:
            found.append(f"{name}: input {key} removed")
            continue
        if now["type"] != spec["type"]:
            found.append(f"{name}: input {key} changed its type from {spec['type']} to "
                         f"{now['type']}")
        if now["required"] and not spec["required"]:
            found.append(f"{name}: input {key} became required")
    for key, spec in after.inputs.items():
        if key not in before.inputs and (spec["required"] or spec["default"] is None):
            found.append(f"{name}: new input {key} must be optional with a default")
    for key, spec in before.secrets.items():
        now = after.secrets.get(key)
        if now is None:
            found.append(f"{name}: secret {key} removed")
        elif now["required"] and not spec["required"]:
            found.append(f"{name}: secret {key} became required")
    for key, spec in after.secrets.items():
        if key not in before.secrets and spec["required"]:
            found.append(f"{name}: new secret {key} must be optional")
    for key in before.outputs:
        if key not in after.outputs:
            found.append(f"{name}: output {key} removed")
    return found


def permission_problems(name, old, new):
    found = []
    top_old = callers.grant(old.get("permissions")) or {}
    top_new = callers.grant(new.get("permissions")) or {}
    over = _over(top_new, top_old)
    if over:
        found.append(f"{name}: the workflow-level permissions grant {_text(over)}, above "
                     f"{_text(top_old) or 'nothing'}")
    old_jobs, new_jobs = callers.jobs(old), callers.jobs(new)
    union_old = callers.needed(name, {name: old})
    for job_id, job in new_jobs.items():
        mine = callers.grant(job.get("permissions"))
        if mine is None:
            continue
        if job_id in old_jobs:
            had = callers.grant(old_jobs[job_id].get("permissions")) or top_old
            over = _over(mine, had)
            if over:
                found.append(f"{name}: job {job_id} asks for {_text(over)}, above what it "
                             "asked for in v2")
        else:
            over = _over(mine, union_old)
            if over:
                found.append(f"{name}: new job {job_id} asks for {_text(over)}, beyond what "
                             "the piece asked for in v2")
    union_new = callers.needed(name, {name: new})
    grown = _over(union_new, union_old)
    if grown:
        found.append(f"{name}: the piece as a whole asks for {_text(grown)}, above what it "
                     "asked for in v2")
    return found


def problems(old, new):
    found = []
    for name, doc in sorted(old.items()):
        if name not in new:
            found.append(f"{name}: removed within v2")
            continue
        found += interface_problems(name, doc, new[name])
        found += permission_problems(name, doc, new[name])
    return found

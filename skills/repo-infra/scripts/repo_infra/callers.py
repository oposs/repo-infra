# skills/repo-infra/scripts/repo_infra/callers.py
"""Validate the callers against what they call (D30).

A caller is a workflow the repository owns: ci.yml, release-build.yml,
release-publish.yml, ci-local.yml. It calls pieces with
`uses: ./.github/workflows/<file>.yml`, and GitHub checks such a call only
when the run starts, so a misspelt input or a missing secret surfaces as a
red run on main. Everything here is read from the files as they are
installed: the interface of the called file, never a list kept beside it.
"""

import fnmatch
import pathlib
import re

from . import workflow
from .markers import parse_markers
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


# A local call written on a line of its own, found by text in a file the
# reader cannot follow. A commented-out line starts with `#` and does not match.
_LOCAL_CALL = re.compile(r"^[ \t]*(?:-[ \t]+)?uses:[ \t]*['\"]?\./\.github/workflows/"
                         r"([^\s'\"#]+)", re.MULTILINE)


def read_workflows(repo_root):
    """{file name: parsed workflow, or its ReadError} for each file GitHub runs.
    A ReadError carries `marker`, the piece its first marker names, or None,
    and `calls`, the local workflows its text calls. A file that is not UTF-8
    is a ReadError too; it used to crash check."""
    folder = pathlib.Path(repo_root) / WORKFLOWS
    docs = {}
    if not folder.is_dir():
        return docs
    for path in sorted(folder.iterdir()):
        if path.is_file() and path.suffix in (".yml", ".yaml"):
            data = path.read_bytes()
            try:
                text = data.decode("utf-8")
                docs[path.name] = workflow.load(text)
            except UnicodeDecodeError as decoding:
                text = data.decode("utf-8", errors="replace")
                docs[path.name] = workflow.ReadError(
                    f"it is not UTF-8 text (byte 0x{data[decoding.start]:02x} at offset "
                    f"{decoding.start})")
            except workflow.ReadError as error:
                docs[path.name] = error
            error = docs[path.name]
            if isinstance(error, workflow.ReadError):
                markers = parse_markers(text)
                error.marker = markers[0].asset if markers else None
                error.calls = set(_LOCAL_CALL.findall(text))
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


FINALIZE = "ri-publish-finalize"
_EXPRESSION = re.compile(r"^\$\{\{(.*)\}\}$", re.DOTALL)


def _expression(value):
    """An expression as GitHub reads it: `${{ }}` around an `if:` is optional,
    and the spacing inside does not matter."""
    text = str(value).strip()
    match = _EXPRESSION.match(text)
    return " ".join((match[1] if match else text).split())


def _top_level(text):
    """Yield (index, char) of `text` outside quotes and parentheses."""
    depth, quoted = 0, False
    for i, char in enumerate(text):
        if char == "'":
            quoted = not quoted
        elif quoted:
            continue
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif depth == 0:
            yield i, char


def _unwrapped(text):
    """`text` without parentheses around the whole of it, and without the
    spaces outside its strings."""
    text = text.strip()
    while text.startswith("(") and text.endswith(")"):
        inner = text[1:-1]
        depth = 0
        for char in inner:
            depth += {"(": 1, ")": -1}.get(char, 0)
            if depth < 0:
                break
        if depth != 0:
            break
        text = inner.strip()
    kept, quoted = [], False
    for char in text:
        quoted = quoted != (char == "'")
        if quoted or not char.isspace():
            kept.append(char)
    return "".join(kept)


def conjuncts(expression):
    """The terms an expression requires all of: its top-level `&&` operands,
    recursively. A top-level `||` makes the whole expression one term."""
    text = _unwrapped(_expression(expression))
    marks = [i for i, char in _top_level(text) if char in "&|"]
    if any(text[i] == "|" for i in marks):
        return [text]
    cuts = [i for i in marks if text[i:i + 2] == "&&"]
    if not cuts:
        return [text]
    parts, start = [], 0
    for cut in cuts:
        parts.append(text[start:cut])
        start = cut + 2
    parts.append(text[start:])
    return [term for part in parts for term in conjuncts(part)]


def finalize_problems(docs, pieces):
    """finalize's `if:` and `with:` as the piece's Call: header has them.

    The guard used to be generated. Without it finalize runs after every push
    of CHANGES.md, also one that publishes nothing, gets an empty release_id
    and turns the Publish run red after every ordinary merge."""
    piece = pieces.get(FINALIZE)
    job = jobs(docs.get("release-publish.yml")).get("finalize")
    if piece is None or job is None or local_target(job.get("uses")) != f"{FINALIZE}.yml":
        return []
    # The Call: header is the caller's job, keyed by its id.
    snippet = workflow.load(piece.header.get("Call", ""))
    pattern = snippet.get("finalize") if isinstance(snippet, dict) else None
    if not isinstance(pattern, dict):
        return []
    found = []
    # A stricter guard is fine (`&& !cancelled()`); `always()` would also run
    # finalize after a failed publish, and an `||` lets an empty id through.
    terms = conjuncts(job.get("if", ""))
    if "if" in pattern and (_unwrapped(_expression(pattern["if"])) not in terms
                            or any(term.lower() == "always()" for term in terms)):
        found.append(("release-publish.yml",
                      f"finalize lacks `if: {pattern['if']}`; it would run after every push "
                      "of CHANGES.md that publishes nothing, with an empty release_id, "
                      "and fail"))
    given = job.get("with") if isinstance(job.get("with"), dict) else {}
    wanted = pattern.get("with") if isinstance(pattern.get("with"), dict) else {}
    for key, value in wanted.items():
        if key in given and _expression(given[key]) != _expression(value):
            found.append(("release-publish.yml",
                          f"finalize passes {key}: {given[key]}; {FINALIZE}.yml takes "
                          f"{key}: {value} (its Call: header)"))
    return found


def _names(value):
    if isinstance(value, str):
        return [value]
    return [v for v in value if isinstance(v, str)] if isinstance(value, list) else []


def _event(doc, event):
    """(True, its filter dict or {}) when `doc` triggers on `event`."""
    on = doc.get("on")
    if isinstance(on, (str, list)):
        return event in _names(on), {}
    if isinstance(on, dict) and event in on:
        return True, on[event] if isinstance(on[event], dict) else {}
    return False, {}


def _on_main(doc, event):
    """True when `event` starts the workflow for the branch main."""
    present, spec = _event(doc, event)
    if not present:
        return False
    if "branches" in spec and not any(fnmatch.fnmatchcase("main", pattern)
                                      for pattern in _names(spec["branches"])):
        return False
    return not any(fnmatch.fnmatchcase("main", pattern)
                   for pattern in _names(spec.get("branches-ignore")))


RELEASE_PR_CURRENT = "ri-release-pr-current"


def frame_problems(docs, pieces):
    """What the frames of ci.yml and release-publish.yml guaranteed before
    the callers were written by hand: their triggers, the call to
    ri-release-pr-current and the publish concurrency group."""
    found = []
    ci = docs.get("ci.yml")
    if isinstance(ci, dict):
        if not _on_main(ci, "push"):
            found.append(("ci.yml", "ci.yml does not run on push to main; main is not tested "
                                    "after a merge, and an open release pull request is not "
                                    "marked stale when main moves (D28)"))
        if not _on_main(ci, "pull_request"):
            found.append(("ci.yml", "ci.yml does not run on pull_request to main; ci-passed "
                                    "never reports on a pull request, and the ruleset that "
                                    "requires it keeps every pull request waiting"))
        if (RELEASE_PR_CURRENT in pieces
                and not calls({"ci.yml": ci}, f"{RELEASE_PR_CURRENT}.yml")):
            found.append(("ci.yml", f"ci.yml calls no {RELEASE_PR_CURRENT}.yml; an open "
                                    "release pull request is not marked stale when main "
                                    "moves (D28). Add its Call: from the catalogue"))
    publish = docs.get("release-publish.yml")
    if not isinstance(publish, dict):
        return found
    name = "release-publish.yml"
    _, spec = _event(publish, "push")
    paths = _names(spec.get("paths"))
    if not _on_main(publish, "push") or ("paths" in spec and "CHANGES.md" not in paths):
        found.append((name, f"{name} does not run on a push of CHANGES.md to main; a merged "
                            "release pull request would never be published"))
    elif paths != ["CHANGES.md"]:
        found.append((name, f"{name} runs on pushes to main beyond CHANGES.md; filter on "
                            "`paths: [CHANGES.md]` alone, since a release reaches main as a "
                            "change to that file"))
    if _event(publish, "workflow_dispatch")[0]:
        found.append((name, f"{name} has a workflow_dispatch trigger; a release is published "
                            "by merging its pull request, and a dispatch would publish "
                            "whatever CHANGES.md says on the branch it runs on. Remove it"))
    concurrency = publish.get("concurrency")
    group = concurrency.get("group") if isinstance(concurrency, dict) else concurrency
    if group != "release-publish":
        found.append((name, f"{name} lacks `concurrency: group: release-publish`; a second "
                            "merge would start a publish run while the first is still "
                            "attaching files"))
    elif isinstance(concurrency, dict) and str(
            concurrency.get("cancel-in-progress", "false")).lower() != "false":
        found.append((name, f"{name} sets `cancel-in-progress: "
                            f"{concurrency['cancel-in-progress']}`; the next push would "
                            "cancel a publish run half way, with the release partly "
                            "published"))
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
    """D28 on the checkouts: the inline jobs of ci.yml and release-build.yml,
    and every project-owned workflow called with `ref`. A call that omits
    `ref` is ref_passing_problems' to report."""
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


def ref_passing_problems(docs):
    """D28: ci.yml and release-build.yml run on the release commit only when
    each workflow they call that declares `ref` is handed `${{ inputs.ref }}`.
    A call without it tests the commit that triggered the run, so the release
    pull request would report a test of the wrong commit as its own."""
    found = []
    for name in ("ci.yml", "release-build.yml"):
        for job_id, job in jobs(docs.get(name)).items():
            called = local_target(job.get("uses"))
            target = docs.get(called)
            face = workflow.interface(target) if isinstance(target, dict) else None
            if face is None or "ref" not in face.inputs:
                continue
            given = job.get("with") if isinstance(job.get("with"), dict) else {}
            if "ref" not in given and face.inputs["ref"]["required"]:
                continue  # call_problems names the missing required input
            if not _INPUT_REF.fullmatch(str(given.get("ref", "")).strip()):
                found.append((name, f"job {job_id} calls {called}, which takes `ref`, "
                                    "without `with: ref: ${{ inputs.ref }}`; the release "
                                    "pull request would test the triggering commit "
                                    "instead of the release commit (D28). Add it"))
    return found


LEVELS = {"none": 0, "read": 1, "write": 2}
_LEVEL_NAMES = {0: "none", 1: "read", 2: "write"}
SCOPES = ("actions", "attestations", "checks", "contents", "deployments", "discussions",
          "id-token", "issues", "models", "packages", "pages", "pull-requests",
          "repository-projects", "security-events", "statuses")


def grant(value):
    """{scope: level} for a `permissions:` value, or None when there is none."""
    if value is None:
        return None
    if value in ("read-all", "write-all"):
        # GitHub has no read level for id-token.
        return {scope: 1 if value == "read-all" else 2
                for scope in SCOPES if value == "write-all" or scope != "id-token"}
    if isinstance(value, dict):
        return {scope: LEVELS.get(str(level), 0) for scope, level in value.items()}
    return {}


def _own_value(doc, job):
    mine = job.get("permissions")
    return mine if mine is not None else doc.get("permissions")


def _own(doc, job):
    return grant(_own_value(doc, job))


def invalid_grant(value):
    """Why GitHub refuses a `permissions:` value, or None."""
    if isinstance(value, str) and value not in ("read-all", "write-all"):
        return (f"`permissions: {value}`, which GitHub does not accept: write read-all, "
                "write-all or a mapping of scopes")
    if isinstance(value, dict):
        for scope, level in value.items():
            if str(level) not in LEVELS:
                return (f"`{scope}: {level}`, which GitHub does not accept: each scope "
                        "takes read, write or none")
    return None


def needed(name, docs, seen=()):
    """The permissions the jobs of workflow `name` ask for (D30). A job that
    declares none asks for what the workflows it calls ask for."""
    doc = docs.get(name)
    if not isinstance(doc, dict) or name in seen:
        return {}
    total = {}
    for job in jobs(doc).values():
        want = _own(doc, job)
        if want is None:
            called = local_target(job.get("uses"))
            want = needed(called, docs, seen + (name,)) if called else {}
        for scope, level in want.items():
            total[scope] = max(total.get(scope, 0), level)
    return total


def permission_text(levels):
    ordered = sorted(levels.items(), key=lambda item: (-item[1], item[0]))
    return ", ".join(f"{scope}: {_LEVEL_NAMES[level]}" for scope, level in ordered if level)


def _starts_runs(doc):
    """True when the workflow has a trigger besides workflow_call."""
    on = doc.get("on")
    if isinstance(on, str):
        return on != "workflow_call"
    if isinstance(on, (list, dict)):
        return any(trigger != "workflow_call" for trigger in on)
    return False


def permission_problems(docs):
    found = []
    for name, doc in docs.items():
        for job_id, job in jobs(doc).items():
            called = local_target(job.get("uses"))
            if called is None or not isinstance(docs.get(called), dict):
                continue
            want = needed(called, docs)
            value = _own_value(doc, job)
            invalid = invalid_grant(value)
            if invalid:
                found.append((name, f"job {job_id} grants {invalid}"))
                continue
            have = grant(value)
            if have is None:
                # A called file inherits what its caller grants, and the
                # caller is checked against this file's needs. A file with a
                # trigger of its own also starts runs, with nothing above it.
                if want and _starts_runs(doc):
                    found.append((name, f"job {job_id} declares no permissions; {called} "
                                        f"needs {permission_text(want)}. Grant them on the job"))
                continue
            short = {scope: level for scope, level in want.items() if have.get(scope, 0) < level}
            if short:
                said = value if isinstance(value, str) else permission_text(have) or "nothing"
                found.append((name, f"job {job_id} grants {said} "
                                    f"and {called} needs {permission_text(short)}; GitHub "
                                    "refuses to start the run"))
    return found


def unreadable_concerns(docs, pieces):
    """The files that failed to read and that check has a stake in: a core
    caller, a file a readable workflow calls, a file whose marker names a
    piece, and a file one of these calls by the text of its `uses:` lines.
    The reader follows a subset of YAML; a repository's own deploy workflow
    written with a flow mapping or an anchor, which GitHub accepts, would
    otherwise keep check at exit 1 for a file repo-infra never reads."""
    unreadable = {name: doc for name, doc in docs.items()
                  if isinstance(doc, workflow.ReadError)}
    found = {name for name, doc in unreadable.items()
             if name in CORE_CALLERS or getattr(doc, "marker", None) in pieces
             or calls(docs, name)}
    todo = list(found)
    while todo:
        for called in getattr(unreadable[todo.pop()], "calls", ()):
            if called in unreadable and called not in found:
                found.add(called)
                todo.append(called)
    return found


def _callable(pieces, file):
    """True when the workflow piece installed as `file` runs only when called:
    its header carries a Call: snippet. changelog and release-pr start runs
    of their own."""
    return any(p.workflow and pathlib.PurePosixPath(p.target).name == file
               and "Call" in p.header for p in pieces.values())


def validate(docs, pieces, assets=ASSETS):
    piece_files = {pathlib.PurePosixPath(p.target).name
                   for p in pieces.values() if p.workflow}
    concerns = unreadable_concerns(docs, pieces)
    items = [Item("callers", name, "problem", f"cannot be read: {doc}")
             for name, doc in docs.items() if name in concerns]
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
    called_by_text = {target for doc in docs.values()
                      if isinstance(doc, workflow.ReadError)
                      for target in getattr(doc, "calls", ())}
    items += [Item("callers", file, "problem",
                   f"{file} is installed and no workflow calls it, so it never runs. Add "
                   "its Call: from the catalogue to a caller, or remove the file")
              for file in sorted(piece_files)
              if file in docs and _callable(pieces, file)
              and not calls(docs, file) and file not in called_by_text]
    found = (closing_problems(docs, assets) + finalize_problems(docs, pieces)
             + frame_problems(docs, pieces)
             + ref_contract_problems(docs, piece_files)
             + ref_passing_problems(docs)
             + permission_problems(docs))
    return items + [Item("callers", name, "problem", detail) for name, detail in found]

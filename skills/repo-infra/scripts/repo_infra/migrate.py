"""apply's migration from the v1 layout (copied pieces, D30) to remote pieces
(D33): text rewrites that keep every line they do not need to change, so
the pull request shows exactly the migration.

The rewrites read the layout repo-infra writes: jobs two spaces below
`jobs:`, their keys two further. migrate parses each result and refuses a
file whose jobs came out other than intended, rather than commit a broken
workflow.
"""

import pathlib
import re
import shutil

from . import callers, workflow
from .apply import ApplyError
from .markers import parse_markers
from .pieces import ASSETS, HOME_REPO, MAJOR

WORKFLOWS = ".github/workflows"
# The v1 pieces that are callers in v2, written from assets/callers/.
CALLERS = {"changelog.yml": "changelog", "release-pr.yml": "release-pr"}
_LOCAL = re.compile(r"^(?P<lead>[ \t]*(?:-[ \t]+)?uses:[ \t]*)(?P<q>['\"]?)\./\.github/"
                    r"workflows/(?P<file>[^\s'\"#]+)(?P=q)(?P<tail>[ \t]*(?:#.*)?)$")
_JOB = re.compile(r"^  ([A-Za-z_][\w-]*):\s*(?:#.*)?$")
_INHERIT = re.compile(r"^    secrets:[ \t]*inherit[ \t]*(?:#.*)?$")
_USES = re.compile(r"^    uses:[ \t]*['\"]?([^\s'\"#]+)")
_SECRET_REF = re.compile(r"\bsecrets\.([A-Za-z_][A-Za-z0-9_-]*)")

ACTION_TEST = """  action-test:
    {skip}
    uses: ./.github/workflows/action-test.yml
    with:
      ref: ${{{{ inputs.ref }}}}
    secrets: inherit"""


def rewrite_uses(text, remote_files):
    out = []
    for line in text.split("\n"):
        match = _LOCAL.match(line)
        if match and match["file"] in remote_files:
            line = (f"{match['lead']}{HOME_REPO}/{WORKFLOWS}/{match['file']}@{MAJOR}"
                    f"{match['tail']}")
        out.append(line)
    return "\n".join(out)


def _jobs_start(lines):
    return next((i + 1 for i, line in enumerate(lines) if line.rstrip() == "jobs:"), None)


def _job_keys(lines):
    """[(job id, line index)] of every job under `jobs:`."""
    first = _jobs_start(lines)
    if first is None:
        return []
    found = []
    for i in range(first, len(lines)):
        if lines[i] and not lines[i].startswith(" ") and not lines[i].startswith("#"):
            break
        match = _JOB.match(lines[i])
        if match:
            found.append((match[1], i))
    return found


def _block(lines, key):
    """(start, end) of the job whose key is on line `key`."""
    first = _jobs_start(lines)
    start = key
    while start - 1 >= first and lines[start - 1].startswith("  #"):
        start -= 1
    end = key + 1
    while end < len(lines) and not (_JOB.match(lines[end]) or lines[end].startswith("  #")
                                    or (lines[end] and not lines[end].startswith(" "))):
        end += 1
    while end > key + 1 and lines[end - 1].strip() == "":
        end -= 1
    return start, end


def job_block(text, job_id):
    """(start, end) line indices of job `job_id` under `jobs:`, with the
    comment lines directly above it, or None."""
    lines = text.split("\n")
    key = next((i for name, i in _job_keys(lines) if name == job_id), None)
    return None if key is None else _block(lines, key)


def _cut(text, job_id):
    """`text` without the job and the blank lines after it."""
    block = job_block(text, job_id)
    if block is None:
        return text
    lines = text.split("\n")
    start, end = block
    while end < len(lines) and lines[end].strip() == "":
        end += 1
    return "\n".join(lines[:start] + lines[end:])


def _remove_from_needs(text, job_id):
    out, lines, i = [], text.split("\n"), 0
    while i < len(lines):
        line = lines[i]
        flow = re.match(r"^(    needs:[ \t]*)\[([^\]]*)\](.*)$", line)
        scalar = re.match(r"^    needs:[ \t]*['\"]?([\w-]+)['\"]?[ \t]*(?:#.*)?$", line)
        if flow:
            names = [n.strip() for n in flow[2].split(",")
                     if n.strip() and n.strip().strip("'\"") != job_id]
            if names:
                out.append(f"{flow[1]}[{', '.join(names)}]{flow[3]}")
        elif scalar:
            if scalar[1] != job_id:
                out.append(line)
        elif line.rstrip() == "    needs:":
            items = []
            while (i + 1 < len(lines)
                   and re.match(r"^      -[ \t]", lines[i + 1])):
                i += 1
                items.append(lines[i])
            kept = [item for item in items
                    if item.split("-", 1)[1].split("#")[0].strip().strip("'\"") != job_id]
            if kept:
                out += [line] + kept
        else:
            out.append(line)
        i += 1
    return "\n".join(out)


def drop_job(text, job_id):
    """`text` without the job `job_id`, and without it in any `needs:`."""
    if job_block(text, job_id) is None:
        return text
    return _remove_from_needs(_cut(text, job_id), job_id)


def used_secrets(texts):
    """The secret names the workflows in `texts` read, lower case: GitHub
    matches secret names without regard to case."""
    return {name.lower() for text in texts for name in _SECRET_REF.findall(text)}


def passed_secrets(pieces, used):
    """{piece file: [secret]} for replacing `secrets: inherit` on a call:
    the secrets the piece requires, and the optional ones the repository
    used before. inherit passed every secret; naming an optional one the
    repository never had, such as ri-publish-tag's app-client-id, would
    read as a secret it is expected to set."""
    found = {}
    for piece in pieces.values():
        if not piece.remote:
            continue
        secrets = workflow.interface(workflow.load(piece.files[piece.target])).secrets
        found[pathlib.PurePosixPath(piece.target).name] = [
            name for name, spec in secrets.items()
            if spec["required"] or name.lower() in used]
    return found


def name_secrets(text, secrets_of):
    """`secrets: inherit` on a call of a repo-infra piece replaced by the
    secrets of `secrets_of` named one by one, or dropped when there are none
    (D33: check refuses inherit on a remote call)."""
    lines = text.split("\n")
    for _, key in reversed(_job_keys(lines)):
        start, end = _block(lines, key)
        uses = next((m[1] for line in lines[key:end] if (m := _USES.match(line))), None)
        called = callers.home_call(uses)
        if called is None:
            continue
        names = secrets_of.get(called[0], [])
        for i in range(end - 1, key, -1):
            if _INHERIT.match(lines[i]):
                named = (["    secrets:"] + [f"      {n}: ${{{{ secrets.{n} }}}}" for n in names]
                         if names else [])
                lines[i:i + 1] = named
    return "\n".join(lines)


def _ci_passed_pattern(pattern_text):
    """The pattern's release-verdict and ci-passed, with what lies between."""
    lines = pattern_text.split("\n")
    start, _ = job_block(pattern_text, "release-verdict")
    _, end = job_block(pattern_text, "ci-passed")
    return lines[start:end]


def set_ci_passed(text, pattern_text):
    """ci-passed as the pattern has it, needing every other job, with
    release-verdict directly above it. Every other line stays. Idempotent."""
    new = _ci_passed_pattern(pattern_text)
    text = _cut(text, "release-verdict")
    lines = text.split("\n")
    others = [name for name, _ in _job_keys(lines) if name != "ci-passed"]
    new = [line if not line.startswith("    needs:")
           else f"    needs: [{', '.join(others + ['release-verdict'])}]" for line in new]
    block = job_block(text, "ci-passed")
    if block is None:
        return text.rstrip("\n") + "\n" + "\n".join(new) + "\n"
    start, end = block
    return "\n".join(lines[:start] + new + lines[end:])


def add_action_test(text, skip=None):
    """D33: a piece cannot call a workflow of its caller, so ci.yml calls
    action-test.yml itself, directly above ci-passed."""
    if skip is None:
        skip = _skip_line()
    job = ACTION_TEST.format(skip=skip).split("\n")
    block = job_block(text, "ci-passed")
    if block is None:
        return text.rstrip("\n") + "\n" + "\n".join(job) + "\n"
    lines = text.split("\n")
    return "\n".join(lines[:block[0]] + job + lines[block[0]:])


def _skip_line(assets=ASSETS):
    path = pathlib.Path(assets) / "callers/release-pr-skip.yml"
    return next(line for line in path.read_text(encoding="utf-8").split("\n")
                if line.startswith("if: "))


def _ci(text, path, pattern, skip):
    try:
        doc = workflow.load(text)
    except workflow.ReadError as error:
        raise ApplyError(f"{path} cannot be read ({error}); repair it, then run apply "
                         "again") from error
    before = list(callers.jobs(doc))
    lib = [j for j, job in callers.jobs(doc).items()
           if callers.normal_uses(job.get("uses")) == "ri-ci-lib.yml"]
    for job_id in lib:
        text = drop_job(text, job_id)
    targets = {callers.normal_uses(j.get("uses"))
               for j in callers.jobs(workflow.load(text)).values()}
    wanted = {j for j in before if j not in lib} | {"release-verdict", "ci-passed"}
    if "ri-ci-github-action.yml" in targets and "action-test.yml" not in targets:
        text = add_action_test(text, skip)
        wanted.add("action-test")
    text = set_ci_passed(text, pattern)
    try:
        after = set(callers.jobs(workflow.load(text)))
    except workflow.ReadError:
        after = None
    if after != wanted:
        raise ApplyError(f"{path}: migrating its jobs by text gave other jobs than "
                         f"{', '.join(sorted(wanted))}; is it indented two spaces per "
                         "level, as repo-infra writes it? Migrate it by hand")
    return text


def _is_retired(path, piece):
    """True when the file is absent or is the v1 piece `piece`. A v2 caller
    carries no marker and may hold jobs of the repository's own."""
    if not path.is_file():
        return True
    markers = parse_markers(path.read_text(encoding="utf-8", errors="replace"))
    return bool(markers) and markers[0].asset == piece


def migrate(repo_root, pieces, assets):
    """Bring a consumer from the v1 layout to the v2 one. Every new text is
    computed before the first file changes, so a refusal leaves the
    repository as it was. Returns the paths written or removed."""
    root = pathlib.Path(repo_root)
    folder = root / WORKFLOWS
    remote = {pathlib.PurePosixPath(p.target).name for p in pieces.values() if p.remote}
    files = sorted(p for p in folder.iterdir()
                   if p.is_file() and p.suffix in (".yml", ".yaml")) if folder.is_dir() else []
    gone = [p for p in files if p.name in remote | {"ri-ci-lib.yml"}]
    used = used_secrets(p.read_text(encoding="utf-8", errors="replace") for p in files)
    secrets_of = passed_secrets(pieces, used)
    callers_dir = pathlib.Path(assets) / "callers"
    pattern = (callers_dir / "ci-passed.yml").read_text(encoding="utf-8")
    skip = _skip_line(assets)
    writes = {}
    for name, piece in CALLERS.items():
        if _is_retired(folder / name, piece):
            writes[folder / name] = (callers_dir / name).read_text(encoding="utf-8")
    for path in files:
        if path in gone or path in writes:
            continue
        text = path.read_text(encoding="utf-8")
        new = name_secrets(rewrite_uses(text, remote), secrets_of)
        if path.name == "ci.yml":
            new = _ci(new, f"{WORKFLOWS}/{path.name}", pattern, skip)
        writes[path] = new

    touched = []
    for path in gone:
        path.unlink()
        touched.append(f"{WORKFLOWS}/{path.name}")
    lib = folder / "lib"
    if lib.is_dir():
        touched += sorted(p.relative_to(root).as_posix() for p in lib.rglob("*")
                          if p.is_file())
        shutil.rmtree(lib)
    for path, text in writes.items():
        old = path.read_text(encoding="utf-8") if path.is_file() else None
        if text != old:
            path.write_text(text, encoding="utf-8")
            touched.append(f"{WORKFLOWS}/{path.name}")
    return touched

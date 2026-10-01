"""The contract of a project-owned reusable workflow (D20, D25, D28).

ci.yml calls ci-local.yml and action-test.yml, and release-build.yml calls
release-build-local.yml, each with the input `ref`: the commit to test or to
build. A file that does not declare it makes GitHub reject the caller. A file
that declares it and checks out its default commit instead tests main while
the release pull request says it tested the release. Both are read from the
text here, because the scripts use the standard library only; the reader
understands block-style YAML as GitHub workflows write it.
"""

import re

_LINE = re.compile(r"^(?P<indent>\s*)(?P<dash>-\s+)?(?P<key>[A-Za-z_][\w-]*)\s*:\s*(?P<value>.*)$")
_INPUT_REF = re.compile(r"\$\{\{\s*inputs\.ref\s*\}\}")
_RESERVED = re.compile(r"^(release-asset-.*|release-files)$")


def _strip(value):
    return value.strip().strip("'\"")


def _parse(text):
    """One (indent, dash, key, value) per key line. `dash` is the column of a
    list item's `-` or None; `indent` is the column of the key itself."""
    lines = []
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        match = _LINE.match(raw)
        if not match:
            continue
        value = match["value"]
        if " #" in value and not value.lstrip().startswith(("'", '"')):
            value = value.split(" #", 1)[0]
        dash = len(match["indent"]) if match["dash"] else None
        indent = len(match["indent"]) + (len(match["dash"]) if match["dash"] else 0)
        lines.append((indent, dash, match["key"], value.strip()))
    return lines


def _nested(lines, i):
    """The lines nested under line i, by indentation."""
    j = i + 1
    while j < len(lines) and lines[j][0] > lines[i][0]:
        j += 1
    return lines[i + 1:j]


def _declares_ref(lines):
    for i, (_indent, _dash, key, _value) in enumerate(lines):
        if key != "workflow_call":
            continue
        for k, line in enumerate(lines[i + 1:], start=i + 1):
            if line[0] <= lines[i][0]:
                break
            if line[2] == "inputs":
                children = _nested(lines, k)
                if children and any(c[0] == children[0][0] and c[2] == "ref" for c in children):
                    return True
    return False


def _steps(lines):
    """Each list item with everything nested under it."""
    steps = []
    for i, (_indent, dash, _key, _value) in enumerate(lines):
        if dash is None:
            continue
        j = i + 1
        while j < len(lines) and lines[j][0] > dash and not (
                lines[j][1] is not None and lines[j][1] <= dash):
            j += 1
        steps.append(lines[i:j])
    return steps


def seam_problems(text, reserved_artifacts):
    lines = _parse(text)
    problems = []
    if not _declares_ref(lines):
        problems.append("declares no workflow_call input `ref`")
    for step in _steps(lines):
        uses = next((_strip(v) for _i, _d, k, v in step if k == "uses"), "")
        if uses.startswith("actions/checkout@"):
            if not any(k == "ref" and _INPUT_REF.search(v) for _i, _d, k, v in step):
                problems.append("has an actions/checkout step that does not check out "
                                "`ref: ${{ inputs.ref }}`")
        if reserved_artifacts and uses.startswith("actions/upload-artifact@"):
            with_indent = next((i for i, _d, k, _v in step if k == "with"), None)
            for indent, _d, key, value in step:
                if (with_indent is not None and indent > with_indent and key == "name"
                        and _RESERVED.match(_strip(value))):
                    problems.append(f"uploads an artifact named {_strip(value)}, a name "
                                    "reserved for the release build")
    return list(dict.fromkeys(problems))

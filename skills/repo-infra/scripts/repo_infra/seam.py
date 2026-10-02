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

_LINE = re.compile(r"^(?P<indent>\s*)(?P<dash>-\s+(?:&[\w-]+\s+)?)?"
                   r"(?P<key>[A-Za-z_][\w-]*)\s*:\s*(?P<value>.*)$")
# A list item whose content starts on the next line: `-` alone, or with an anchor.
_BARE_DASH = re.compile(r"^(?P<indent>\s*)-(?:\s+&[\w-]+)?\s*$")
# An aliased list item, value or merge key: the text it stands for is elsewhere.
_ALIAS = re.compile(r"^\s*-\s+\*[\w-]+\s*$|:\s+\*[\w-]+\s*$")
# GitHub reads context names in an expression case-insensitively.
_INPUT_REF = re.compile(r"\$\{\{\s*inputs\.ref\s*\}\}", re.IGNORECASE)
# In any case: whether GitHub tells artifact names apart by case is not
# documented, so a name that differs only in case is refused too.
_RESERVED = re.compile(r"^(release-asset-.*|release-files)$", re.IGNORECASE)
_RESERVED_PROBLEM = "uploads an artifact named"
_QUOTED = re.compile(r"""^(?P<q>['"]).*?(?P=q)(?=\s+#|\s*$)""")
# Compared in lower case: GitHub reads owner and repository names case-insensitively.
_CHECKOUT = "actions/checkout@"
_UPLOAD = "actions/upload-artifact@"


def _strip(value):
    """The value without one pair of enclosing YAML quotes. Quotes inside them
    are part of the value: `"'${{ inputs.ref }}'"` names a ref in quotes."""
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value


def _value(value):
    """A key's value without its trailing comment; a quoted value keeps its quotes."""
    value = value.strip()
    if value.startswith("#"):
        return ""
    quoted = _QUOTED.match(value)
    if quoted:
        return quoted.group(0)
    return value.split(" #", 1)[0].strip()


def _code(raw):
    """The line without its comment, or "" for a comment line."""
    if raw.lstrip().startswith("#"):
        return ""
    return raw.split(" #", 1)[0] if " #" in raw else raw


def _parse(text):
    """One (indent, dash, key, value) per key line. `dash` is the column of a
    list item's `-` or None; `indent` is the column of the key itself."""
    lines = []
    pending = None
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        bare = _BARE_DASH.match(raw)
        if bare:
            pending = len(bare["indent"])
            continue
        match = _LINE.match(raw)
        if not match:
            pending = None
            continue
        value = _value(match["value"])
        indent = len(match["indent"]) + (len(match["dash"]) if match["dash"] else 0)
        if match["dash"]:
            dash = len(match["indent"])
        elif pending is not None and indent > pending:
            dash = pending
        else:
            dash = None
        pending = None
        lines.append((indent, dash, match["key"], value.strip()))
    return lines


def _nested(lines, i):
    """The lines nested under line i, by indentation."""
    j = i + 1
    while j < len(lines) and lines[j][0] > lines[i][0]:
        j += 1
    return lines[i + 1:j]


def _children(lines, i):
    """The keys directly under line i."""
    nested = _nested(lines, i)
    return [line for line in nested if line[0] == nested[0][0]] if nested else []


def _declares_ref(lines):
    for i, (_indent, _dash, key, _value) in enumerate(lines):
        if key != "workflow_call":
            continue
        for k, line in enumerate(lines[i + 1:], start=i + 1):
            if line[0] <= lines[i][0]:
                break
            if line[2] == "inputs" and any(c[2] == "ref" for c in _children(lines, k)):
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


def _own(step, key):
    """The index of the step's own `key`, not one nested deeper."""
    return next((i for i, line in enumerate(step) if line[0] == step[0][0] and line[2] == key),
                None)


def _with(step):
    """The `with:` value written on its own line, and the keys directly under it."""
    at = _own(step, "with")
    return ("", []) if at is None else (step[at][3], _children(step, at))


def _unreadable(action):
    return (f"has an {action.rstrip('@')} step this check cannot read; write each step in "
            "block style, `- uses: ...` with its keys on the lines below, without anchors, "
            "aliases or flow mappings")


def seam_problems(text, reserved_artifacts):
    """What keeps this file from the contract. A step written in a form the
    reader does not follow is a problem too: passing it would let a checkout
    of the default commit through, which is the failure this check exists for."""
    lines = _parse(text)
    problems = []
    if not _declares_ref(lines):
        problems.append("declares no workflow_call input `ref`")
    code = [_code(raw) for raw in text.splitlines()]
    if any(_ALIAS.search(line) for line in code):
        problems.append("uses a YAML alias, which this check cannot follow; write the "
                        "steps out in full")
    actions = (_CHECKOUT, _UPLOAD) if reserved_artifacts else (_CHECKOUT,)
    read = {action: 0 for action in actions}
    for step in _steps(lines):
        at = _own(step, "uses")
        uses = _strip(step[at][3]) if at is not None else ""
        action = next((a for a in actions if uses.lower().startswith(a)), None)
        if action is None:
            continue
        read[action] += 1
        value, children = _with(step)
        if value:
            problems.append(_unreadable(action))
        elif action == _CHECKOUT:
            refs = [v for _i, _d, k, v in children if k == "ref"]
            if not refs or not all(_INPUT_REF.fullmatch(_strip(v)) for v in refs):
                problems.append("has an actions/checkout step that does not check out "
                                "`ref: ${{ inputs.ref }}`")
        else:
            for _i, _d, key, value in children:
                if key == "name" and _RESERVED.match(_strip(value)):
                    problems.append(f"{_RESERVED_PROBLEM} {_strip(value)}, a name "
                                    "reserved for the release build")
    for action in actions:
        if sum(line.lower().count(action) for line in code) != read[action]:
            problems.append(_unreadable(action))
    return list(dict.fromkeys(problems))


def seam_advice(problems):
    """What to change for these problems: the ref contract, the artifact name, or both.

    An upload step the reader cannot follow says what to do in its own text."""
    upload = _unreadable(_UPLOAD)
    advice = []
    if any(not p.startswith(_RESERVED_PROBLEM) and p != upload for p in problems):
        advice.append("declare `on: workflow_call: inputs: ref` and give every "
                      "actions/checkout `ref: ${{ inputs.ref }}`")
    if any(p.startswith(_RESERVED_PROBLEM) for p in problems):
        advice.append("give the artifact another name; release-asset-* and release-files "
                      "are the release build's")
    return "; ".join(advice) or "rewrite the upload step as the problem says"

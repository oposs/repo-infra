# Pieces and callers (D30) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** repo-infra stops detecting and assembling. It ships complete reusable workflows (pieces) that a repository copies 1:1 and calls from short callers; `check` reports piece state and validates the callers, `apply` replaces outdated pieces and prints per-piece upgrade notes.

**Architecture:** A standard-library YAML reader (`workflow.py`) lets the tool read pieces and callers as data. `pieces.py` loads the piece store (`assets/pieces/<name>/`, `manifest.json` `pieces`, `generations.json` hashes). `check.py` decides each piece's state by byte comparison with every published version, `callers.py` validates every `uses: ./.github/workflows/...` call, the two closing jobs, the D28 ref contract and the token permissions. `catalogue.py` writes `references/catalogue.md` from the pieces. The old detector, assembler, migration and D29 stamp are deleted once repo-infra's own `.github/` runs on the new model.

**Tech Stack:** Python 3.11 standard library (scripts), pytest + PyYAML (tests only), GitHub Actions reusable workflows, node for the workflow library tests.

**Spec:** `docs/superpowers/specs/2026-10-02-pieces-and-callers-design.md`. Read it before Task 1. This plan covers step 1 of its "Order of work" (repo-infra). mdmost (step 2) and Smalti with `ri-ci-make` and `ri-release-nfpm` (step 3) get their own plans in their own repositories.

## Global Constraints

- Scripts under `skills/repo-infra/scripts/repo_infra/` use the Python standard library only (`requires-python = ">=3.11"`). Tests may use PyYAML (`requirements-dev.txt`).
- "Every workflow piece is a complete reusable workflow (`on: workflow_call`) with typed `inputs` and declared `secrets`. Each input and secret carries a `description:`."
- "The first comment line is the marker `# repo-infra: <piece> vN`." Non-workflow pieces use the comment syntax of their language: `#` for `.yml`/`.mk`, `//` for `.js`, `dnl` for `.m4`, `--` for `.lua`.
- "A piece carries no repository-specific text."
- "No remote references. A repository's infrastructure works standalone; nothing at run time reaches back to repo-infra."
- `.github/repo-infra.json` keeps only `version_files`, `release_assets`, `release_files`, `gitea_packages`, `moving_major_tag`, plus `rust` (see Decision G). The keys `ecosystems`, `ci`, `ci_local`, `publish`, `build`, `release_build`, `release_build_local`, `publish_local` go away; `skip` and `answers` go with detection.
- The required checks stay exactly `ci-passed` and `changelog-updated` (D2).
- GitHub limits: at most ten levels of nested workflows, at most 50 unique reusable workflows per file, a called workflow can only lower the `GITHUB_TOKEN` permissions it receives, workflow-level `env` is not passed to a called workflow.
- Action versions in every piece match the manifest `actions` map exactly.
- `make check` (ruff, pytest, node lib tests) is green at the end of every task. Run pytest serially; never more than 4 cores.
- No em dash in any shipped file (`tests/test_no_em_dash.py`).
- Prose (comments, CHANGES entries, skill text, commit messages) follows the `writing-style` skill. Load it before writing any.
- Every commit ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Work stays on branch `worktree-pieces` in `/scratch/oetiker/claude-worktrees/repo-infra-pieces`. No other repository is touched.

## Decisions this plan takes where the spec is silent or contradicts itself

The executor implements these. They are listed so the human reviewing the plan can veto one before Task 1.

- **A. The publish job, `finalize` and `release-pr-current` become pieces** (`ri-publish-tag`, `ri-publish-finalize`, `ri-release-pr-current`), not caller patterns. The spec table says "caller pattern", but each holds 100 to 250 lines of github-script; in a caller they could not be replaced on update and would contradict "a caller is short and readable".
- **B. `ci-passed` stays an inline job** in `ci.yml`. A job that calls a reusable workflow reports as `ci-passed / <job>`, which the ruleset would not match. Its text ships as `assets/callers/ci-passed.yml`; `check` compares the caller's job with it structurally, ignoring `needs:`, so a change to the pattern reaches every repository through `check`.
- **C. Permissions are validated** (spec gap 3). For every call, the job's grant must cover what the called file's jobs ask for, recursively. Create release PR grants `ci.yml` a fixed union, so this is what stops a caller from breaking the release.
- **D. Header grammar.** After the marker line, one empty comment line, then fields `Purpose:`, `Choose:`, `Supplies:` (required), `Pieces:`, `Produces:`, `Call:` (optional; required for every piece a caller calls, which is every workflow piece except `changelog` and `release-pr`: those start runs of their own). A field continues on lines indented by two more spaces. The first empty comment line or code line ends the header. `Call:` holds the caller job; a test validates it against the piece.
- **E. The D28 ref contract is checked on the YAML structure.** It applies to the inline jobs of `ci.yml` (except `ci-passed`) and `release-build.yml`, and to every project-owned workflow a caller or piece calls with `ref`. `seam.py` and its text parser go.
- **F. The D29 stamp goes.** A piece is identified by its bytes against `generations.json`; the merge procedure stays, keyed on `edited` instead of "no stamp". D11 ("markers, never content hashes") is superseded for pieces.
- **G. `rust` stays in `.github/repo-infra.json`.** `lib/rust-plan.js` reads it, and the spec keeps what the workflow library reads.
- **H. `apply --item <piece>` installs a piece that is not there yet.** Onboarding then copies pieces with the same code that upgrades them. Bare `apply` installs outdated pieces, missing core pieces and missing dependencies. Administration items run only with `--item`, one at a time, each confirmed with the user.
- **I. A remote reusable-workflow reference** (`owner/repo/.github/workflows/x.yml@ref`) is a `problem`.
- **J. Gap 2:** `ri-publish-gitea` keeps reading `gitea_packages` from the config (it is in the kept key list); it gets no owner or URL input.
- **K. Gap 1** (`ri-ci-make` `python` default) belongs to the Smalti plan.
- **L. Carried-over pieces keep their history.** `generations.json` keeps the old hash of `changelog` v4, `release-pr` v5 and the others under the new path, so a repository still on v4 reads `outdated`, not `edited`.
- **M. Obsolete config keys are reported** as `problem`, so a migrated repository is told to remove them.

## Review Focus

1. A repository still on the assembled files (mdmost: `ci.yml` starts with `# repo-infra: ci v2` and carries `ci-rust v3` block markers) must get one `unknown` row per such file pointing at `references/onboarding.md`, and `check` exits 1 without a traceback. Test in Task 5.
2. A caller the reader cannot follow (`with: {ref: x}`, an anchor, a tab) must give one `problem` row naming the file and the line; every other file is still validated. Test in Task 3.
3. `apply` replacing a piece whose new version adds a required input must print the upgrade note and the caller finding; `check` exits 1 until the caller passes the input. Test in Task 12.
4. A call job that grants less than the piece needs (`ri-release-pr-current` under a workflow-level `contents: read`, or a `ci.yml` whose union exceeds what Create release PR grants) must be a `problem` naming the scope. Test in Task 4.
5. A directory piece with a file of the project's own in `.github/workflows/lib/` must ignore that file; a file an older version shipped and the current one does not must be removed by `apply` when unedited. Tests in Tasks 5 and 12.

---

## File structure

New modules in `skills/repo-infra/scripts/repo_infra/`:

| File | Responsibility |
|---|---|
| `workflow.py` | Read block-style YAML; `interface()` of a reusable workflow |
| `pieces.py` | Load the piece store: manifest, header, files, published hashes, upgrade notes |
| `report.py` | `Item`, `SECTIONS`, `ATTENTION`; text and JSON rendering (rewritten) |
| `callers.py` | Validate calls, closing jobs, ref contract, permissions |
| `check.py` | Piece states, config, path filters, administration items; `run()` |
| `catalogue.py` | Render `references/catalogue.md` |
| `apply.py` | Install pieces, merge files, admin items (trimmed) |
| `cli.py` | `check` and `apply` (rewritten) |

Deleted in Task 14: `detect.py`, `assemble.py`, `migrate.py`, `seam.py`, `state.py`, the stamp functions in `markers.py`.

New asset layout under `skills/repo-infra/assets/`:

```
pieces/<name>/CHANGES.md
pieces/<name>/<file name of the target>      file piece
pieces/<name>/<dir name of the target>/...   directory piece (workflow-lib: pieces/workflow-lib/lib/*.js)
callers/ci-passed.yml                        the ci-passed pattern (Decision B)
manifest.json                                {"pieces": {...}, "actions": {...}, "gh": {...}}
generations.json                             {"pieces/<name>/<file>": {"<version>": "<sha256>"}}
gh/ruleset-main.json                         unchanged
```

Manifest entry shape: `"ri-ci-rust": {"target": ".github/workflows/ri-ci-rust.yml", "group": "ci"}`; a directory piece adds `"kind": "dir", "header": "release.js"`; a piece every repository carries adds `"core": true`. Groups: `ci`, `release-build`, `publish`, `release`, `build`. The version lives only in the marker.

New test helpers and tests: `tests/piecekit.py`, `tests/test_workflow.py`, `tests/test_piece_model.py`, `tests/test_pieces.py`, `tests/test_callers.py`, `tests/test_permissions.py`, `tests/test_check.py`, `tests/test_catalogue.py`, `tests/test_apply_pieces.py`, `tests/test_self_check.py`.

---

### Task 1: The workflow reader

**Files:**
- Create: `skills/repo-infra/scripts/repo_infra/workflow.py`
- Test: `tests/test_workflow.py`

**Interfaces:**
- Produces: `workflow.ReadError(Exception)`; `workflow.load(text) -> dict | list | str | None` (every scalar a `str`, empty value `""`, as `yaml.BaseLoader`); `workflow.Interface = namedtuple("Interface", "inputs secrets outputs")` with `inputs: {name: {"required": bool, "default": str|None, "type": str, "description": str}}`, `secrets: {name: {"required": bool, "description": str}}`, `outputs: tuple[str]`; `workflow.interface(doc) -> Interface | None`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_workflow.py
"""The workflow reader against PyYAML's BaseLoader (D30).

BaseLoader returns every scalar as a string, which is what workflow.load
promises. The real workflows of this repository are the main oracle: every
.yml file in the asset store and in .github must read the same both ways."""

import pathlib

import pytest
import yaml

from repo_infra import workflow

ROOT = pathlib.Path(__file__).resolve().parents[1]
FILES = sorted(path for base in (ROOT / "skills/repo-infra/assets", ROOT / ".github")
               for path in base.rglob("*.yml"))


def base(text):
    return yaml.load(text, Loader=yaml.BaseLoader)


@pytest.mark.parametrize("path", FILES, ids=lambda p: str(p.relative_to(ROOT)))
def test_reads_every_workflow_of_this_repository_as_pyyaml_does(path):
    text = path.read_text(encoding="utf-8")
    assert workflow.load(text) == base(text)


SNIPPETS = {
    "nested": "a:\n  b:\n    c: d\n",
    "sequence of scalars": "a:\n  - x\n  - 'y'\n  - \"z\"\n",
    "sequence at the key's indent": "a:\n- x\n- y\nb: c\n",
    "sequence of mappings": "steps:\n  - uses: a@v1\n    with:\n      ref: b\n  - run: c\n",
    "dash alone": "a:\n  -\n    b: c\n",
    "flow sequence": "needs: [a, 'b', \"c\"]\nempty: []\n",
    "comments": "a: b # note\n# whole line\nc: 'd # not a comment'\n",
    "empty value": "a:\nb: c\n",
    "literal": "run: |\n  one\n    two\n\n  three\nnext: x\n",
    "literal strip": "run: |-\n  one\n  two\n",
    "literal keep": "run: |+\n  one\n\n\nnext: x\n",
    "folded": "d: >\n  one\n  two\n\n  three\n    more\n  four\n",
    "folded strip": "d: >-\n  one\n  two\n",
    "plain continued": "if: a &&\n  b\nc: d\n",
    "double quoted escapes": 'a: "x\\ty\\"z"\n',
    "single quoted quote": "a: 'it''s'\n",
    "on is a string key": "on:\n  push:\n    branches: [main]\n",
    "expression": "ref: ${{ inputs.ref }}\n",
    "url value": "u: https://example.com/x\n",
    "document start": "---\na: b\n",
}


@pytest.mark.parametrize("name", sorted(SNIPPETS))
def test_reads_a_snippet_as_pyyaml_does(name):
    assert workflow.load(SNIPPETS[name]) == base(SNIPPETS[name])


REFUSED = {
    "anchor": ("a: &x b\nc: *x\n", "line 1"),
    "alias item": ("a:\n  - *x\n", "line 2"),
    "flow mapping": ("with: {ref: x}\n", "line 1"),
    "tab": ("a:\n\tb: c\n", "line 2"),
    "duplicate key": ("a: b\na: c\n", "line 2"),
    "indentation indicator": ("run: |2\n   x\n", "line 1"),
    "quoted over two lines": ("a: 'b\n  c'\n", "line 1"),
    "flow sequence over two lines": ("a: [b,\n  c]\n", "line 1"),
    "tag": ("a: !!str b\n", "line 1"),
    "not a key": ("a: b\njust text\n", "line 2"),
}


@pytest.mark.parametrize("name", sorted(REFUSED))
def test_refuses_what_it_does_not_follow_and_names_the_line(name):
    text, where = REFUSED[name]
    with pytest.raises(workflow.ReadError, match=where):
        workflow.load(text)


def test_an_empty_text_is_none():
    assert workflow.load("") is None
    assert workflow.load("# only a comment\n") is None


CALLED = """on:
  workflow_call:
    inputs:
      ref:
        description: The commit.
        type: string
        required: false
        default: ''
      target:
        description: The make target.
        type: string
        required: true
    secrets:
      TOKEN:
        description: A token.
        required: true
    outputs:
      tag:
        description: The tag.
        value: ${{ jobs.a.outputs.tag }}
jobs: {}
"""


def test_interface_of_a_reusable_workflow():
    face = workflow.interface(workflow.load(CALLED.replace("jobs: {}\n", "")))
    assert face.inputs["ref"] == {"required": False, "default": "", "type": "string",
                                  "description": "The commit."}
    assert face.inputs["target"]["required"] is True
    assert face.inputs["target"]["default"] is None
    assert face.secrets == {"TOKEN": {"required": True, "description": "A token."}}
    assert face.outputs == ("tag",)


def test_interface_of_a_workflow_without_workflow_call_is_none():
    assert workflow.interface(workflow.load("on:\n  push:\n    branches: [main]\n")) is None
    assert workflow.interface(workflow.load("on: push\n")) is None


def test_interface_of_a_bare_workflow_call():
    assert workflow.interface(workflow.load("on:\n  workflow_call:\n")) == (
        workflow.Interface({}, {}, ()))
    assert workflow.interface(workflow.load("on: [push, workflow_call]\n")) == (
        workflow.Interface({}, {}, ()))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest -q tests/test_workflow.py`
Expected: FAIL with `ImportError: cannot import name 'workflow'`.

- [ ] **Step 3: Write the reader**

```python
# skills/repo-infra/scripts/repo_infra/workflow.py
"""Read the block-style YAML that GitHub workflows are written in (D30).

The scripts use the standard library only, so PyYAML is not available here.
This reader covers what workflows use: block mappings and sequences, plain
and quoted scalars, single-line flow sequences, and literal and folded block
scalars. Every scalar comes back as a string, the way yaml.BaseLoader returns
it, and tests/test_workflow.py holds the two readers to the same result on
every workflow in this repository. Anchors, aliases, tags, flow mappings,
tabs and explicit indentation indicators raise ReadError: check then reports
the file as unreadable instead of guessing what it says.
"""

import re
from collections import namedtuple


class ReadError(Exception):
    """The text uses YAML this reader does not follow; the message says where."""


Interface = namedtuple("Interface", "inputs secrets outputs")

# A key is quoted, or plain up to the first `:` that ends the line or is
# followed by a space. A plain key cannot start with a YAML indicator.
_KEY = re.compile(
    r"""^(?P<key>"(?:[^"\\]|\\.)*"|'(?:[^']|'')*'|[^\s"'#\[\]{},&*!|>%@`-][^#]*?)"""
    r"""\s*:(?:[ ]+(?P<rest>.*))?$""")
_BLOCK = re.compile(r"^([|>])([+-]?)$")
_ESCAPES = {"n": "\n", "t": "\t", "\\": "\\", '"': '"', "/": "/", "0": "\0", " ": " "}


def _item(text):
    return text == "-" or text.startswith("- ")


def _quote_end(text):
    """The index just past the closing quote of `text`, or None."""
    quote, i = text[0], 1
    while i < len(text):
        if quote == '"' and text[i] == "\\":
            i += 2
            continue
        if text[i] == quote:
            if quote == "'" and text[i + 1:i + 2] == "'":
                i += 2
                continue
            return i + 1
        i += 1
    return None


def _unquote(text, line=0):
    if text[:1] == "'":
        return text[1:-1].replace("''", "'")
    if text[:1] != '"':
        return text
    body, out, i = text[1:-1], [], 0
    while i < len(body):
        if body[i] == "\\":
            escape = body[i + 1:i + 2]
            if escape not in _ESCAPES:
                raise ReadError(f"line {line}: the escape \\{escape}, which this reader "
                                "does not follow")
            out.append(_ESCAPES[escape])
            i += 2
        else:
            out.append(body[i])
            i += 1
    return "".join(out)


def _value(rest, line):
    """The value text after `key:` or `-`, without its trailing comment."""
    text = rest.strip()
    if not text or text.startswith("#"):
        return ""
    if text[0] in "'\"":
        end = _quote_end(text)
        if end is None:
            raise ReadError(f"line {line}: a quoted value that continues on the next line")
        tail = text[end:].strip()
        if tail and not tail.startswith("#"):
            raise ReadError(f"line {line}: text after a quoted value")
        return text[:end]
    cut = text.find(" #")
    return (text[:cut] if cut >= 0 else text).rstrip()


def _refuse(text, line):
    if text[0] in "&*":
        raise ReadError(f"line {line}: an anchor or alias; write the value out in full")
    if text[0] == "!":
        raise ReadError(f"line {line}: a tag; write the value without it")
    if text[0] == "{":
        raise ReadError(f"line {line}: a flow mapping; write it in block style")
    if text[0] in "|>" and not _BLOCK.match(text):
        raise ReadError(f"line {line}: a block scalar header this reader does not follow")


def _flow(text, line):
    """A flow sequence of scalars on one line: `[a, 'b']`."""
    if not text.endswith("]"):
        raise ReadError(f"line {line}: a flow sequence that does not end on its line")
    items, current, quote = [], "", None
    for char in text[1:-1]:
        if quote:
            current += char
            if char == quote:
                quote = None
            continue
        if char in "'\"":
            quote = char
            current += char
        elif char in "[]{}":
            raise ReadError(f"line {line}: a nested flow collection; write it in block style")
        elif char == ",":
            items.append(current.strip())
            current = ""
        else:
            current += char
    items.append(current.strip())
    return [_unquote(item, line) for item in items if item != ""]


def _fold(lines):
    """Folded style (YAML 1.2, 8.1.3): a break between two plain lines becomes
    a space; blank lines and more-indented lines keep their breaks."""
    out, last, blanks = "", None, 0
    for line in lines:
        if line == "":
            blanks += 1
            continue
        if last is None:
            out = "\n" * blanks + line
        elif blanks:
            spaced = line.startswith(" ") or last.startswith(" ")
            out += "\n" * (blanks + (1 if spaced else 0)) + line
        elif line.startswith(" ") or last.startswith(" "):
            out += "\n" + line
        else:
            out += " " + line
        last, blanks = line, 0
    return out


class _Reader:
    def __init__(self, text):
        self.lines = text.split("\n")
        self.i = 0

    def peek(self):
        """(indent, text) of the next line with content, or None at the end."""
        while self.i < len(self.lines):
            raw = self.lines[self.i]
            text = raw.strip()
            if text and not text.startswith("#") and text not in ("---", "..."):
                lead = raw[:len(raw) - len(raw.lstrip())]
                if "\t" in lead:
                    raise ReadError(f"line {self.i + 1}: a tab in the indentation")
                return len(lead), text
            self.i += 1
        return None

    def node(self, indent):
        _, text = self.peek()
        return self.sequence(indent) if _item(text) else self.mapping(indent)

    def mapping(self, indent):
        result = {}
        while True:
            peeked = self.peek()
            if peeked is None or peeked[0] < indent:
                return result
            at, text = peeked
            line = self.i + 1
            if at > indent:
                raise ReadError(f"line {line}: indented deeper than the key above it")
            if _item(text):
                return result
            match = _KEY.match(text)
            if match is None:
                raise ReadError(f"line {line}: expected `key: value`")
            key = _unquote(match["key"], line)
            if key in result:
                raise ReadError(f"line {line}: the key {key} appears twice")
            self.i += 1
            result[key] = self.value(match["rest"] or "", indent, line, in_mapping=True)

    def sequence(self, indent):
        result = []
        while True:
            peeked = self.peek()
            if peeked is None or peeked[0] != indent or not _item(peeked[1]):
                return result
            line = self.i + 1
            rest = peeked[1][1:]
            inner = indent + 1 + len(rest) - len(rest.lstrip(" "))
            rest = rest.strip()
            if rest and not rest.startswith("#") and (_item(rest) or _KEY.match(rest)):
                # The item's content starts on the dash line: read the line
                # again with the dash turned into indentation.
                self.lines[self.i] = " " * inner + rest
                result.append(self.node(inner))
            else:
                self.i += 1
                result.append(self.value(rest, indent, line, in_mapping=False))

    def value(self, rest, indent, line, in_mapping):
        text = _value(rest, line)
        if text == "":
            peeked = self.peek()
            if peeked is not None and peeked[0] > indent:
                return self.node(peeked[0])
            if (in_mapping and peeked is not None and peeked[0] == indent
                    and _item(peeked[1])):
                return self.sequence(indent)
            return ""
        _refuse(text, line)
        if text[0] == "[":
            return _flow(text, line)
        block = _BLOCK.match(text)
        if block:
            return self.block(indent, block[1], block[2])
        if text[0] in "'\"":
            return _unquote(text, line)
        parts = [text]
        while True:
            peeked = self.peek()
            if peeked is None or peeked[0] <= indent:
                return " ".join(parts)
            parts.append(_value(peeked[1], self.i + 1))
            self.i += 1

    def block(self, indent, style, chomp):
        lines, width = [], None
        while self.i < len(self.lines):
            raw = self.lines[self.i]
            if raw.strip() == "":
                lines.append("")
                self.i += 1
                continue
            lead = len(raw) - len(raw.lstrip(" "))
            if width is None:
                if lead <= indent:
                    break
                width = lead
            if lead < width:
                break
            lines.append(raw[width:])
            self.i += 1
        trailing = 0
        while lines and lines[-1] == "":
            lines.pop()
            trailing += 1
        if not lines:
            return ""
        body = "\n".join(lines) if style == "|" else _fold(lines)
        if chomp == "-":
            return body
        if chomp == "+":
            return body + "\n" * (1 + trailing)
        return body + "\n"


def load(text):
    """The document in `text`: dicts, lists and strings; None when it is empty."""
    reader = _Reader(text)
    peeked = reader.peek()
    if peeked is None:
        return None
    return reader.node(peeked[0])


def _table(call, key):
    entries = call.get(key) if isinstance(call, dict) else None
    if not isinstance(entries, dict):
        return {}
    return {name: spec if isinstance(spec, dict) else {} for name, spec in entries.items()}


def interface(doc):
    """What a reusable workflow takes and gives, or None if it is not one."""
    on = doc.get("on") if isinstance(doc, dict) else None
    if on == "workflow_call" or (isinstance(on, list) and "workflow_call" in on):
        return Interface({}, {}, ())
    if not isinstance(on, dict) or "workflow_call" not in on:
        return None
    call = on["workflow_call"]
    inputs = {name: {"required": str(spec.get("required", "")).lower() == "true",
                     "default": spec.get("default"),
                     "type": spec.get("type", ""),
                     "description": spec.get("description", "")}
              for name, spec in _table(call, "inputs").items()}
    secrets = {name: {"required": str(spec.get("required", "")).lower() == "true",
                      "description": spec.get("description", "")}
               for name, spec in _table(call, "secrets").items()}
    return Interface(inputs, secrets, tuple(_table(call, "outputs")))
```

- [ ] **Step 4: Run the tests**

Run: `python3 -m pytest -q tests/test_workflow.py`
Expected: PASS. If a real workflow file differs from BaseLoader, the reader is wrong, not the file: print both values (`pytest -q tests/test_workflow.py -k <file> -vv`), fix the reader, and add the smallest snippet that shows the case to `SNIPPETS`. Folding and chomping edge cases are the likely ones.

- [ ] **Step 5: Run the whole gate and commit**

Run: `make check`
Expected: PASS.

```bash
git add skills/repo-infra/scripts/repo_infra/workflow.py tests/test_workflow.py
git commit -m "Read workflows as YAML with the standard library (D30)

check must read pieces and callers as data to validate a call, and the
scripts cannot import PyYAML. The reader covers block YAML as workflows
write it and refuses anchors, flow mappings and tabs with the line, so an
unreadable caller is reported instead of misread. Its test holds it to
yaml.BaseLoader on every workflow in this repository.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: The piece model

**Files:**
- Create: `skills/repo-infra/scripts/repo_infra/pieces.py`
- Create: `tests/piecekit.py`
- Create: `tests/test_piece_model.py`
- Create: `tests/test_pieces.py`
- Modify: `skills/repo-infra/assets/manifest.json` (add `"pieces": {}`)
- Modify: `tests/test_manifest.py` (the expected top-level key set gains `pieces`)

**Interfaces:**
- Consumes: `workflow.load`, `workflow.interface`, `markers.parse_markers`.
- Produces:
  - `pieces.ASSETS: pathlib.Path` (the asset store), `pieces.PieceError(Exception)`.
  - `pieces.Piece` dataclass: `name: str`, `version: int`, `target: str`, `kind: str` (`"file"`/`"dir"`), `group: str`, `core: bool`, `files: dict[str, str]` (repository path to text of the current version), `header: dict[str, str]`; properties `workflow -> bool` (a file piece under `.github/workflows/`), `needs -> list[str]` (the `Pieces:` field split on commas).
  - `pieces.parse_header(text, comment) -> dict[str, str]`.
  - `pieces.load_pieces(assets=ASSETS) -> dict[str, Piece]`.
  - `pieces.load_published(assets=ASSETS) -> dict[str, dict[str, dict[int, str]]]` (piece to repository path to version to sha256).
  - `pieces.changes_sections(text) -> dict[int, str]`; `pieces.upgrade_notes(name, old, new, assets=ASSETS) -> list[tuple[int, str]]`.
  - `piecekit.workflow_piece(name, version, inputs="", body="v1", header="") -> str`, `piecekit.lib_file(name, version, body) -> str`, `piecekit.make_assets(root, current, history=(), core=()) -> pathlib.Path`, `piecekit.install(root, path, text)`, `piecekit.CI_PASSED: str`.

- [ ] **Step 1: Write the test kit**

```python
# tests/piecekit.py
"""A small piece store and repository for tests (D30)."""

import hashlib
import json
import pathlib

from repo_infra.markers import parse_markers

CI_PASSED = """jobs:
  ci-passed:
    if: always()
    needs: []
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - if: contains(needs.*.result, 'failure') || contains(needs.*.result, 'cancelled')
        run: exit 1
"""


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def workflow_piece(name, version, inputs="", body="v1", header=""):
    """A workflow piece called with `ref`; `inputs` adds input entries."""
    job = name.removeprefix("ri-")
    return (
        f"# repo-infra: {name} v{version}\n"
        "#\n"
        f"# Purpose: Test piece {name}.\n"
        "# Choose: In tests.\n"
        "# Supplies: Nothing.\n"
        f"{header}"
        "# Call:\n"
        f"#   {job}:\n"
        f"#     uses: ./.github/workflows/{name}.yml\n"
        "#     with:\n"
        "#       ref: ${{ inputs.ref }}\n"
        f"name: {name}\n"
        "on:\n"
        "  workflow_call:\n"
        "    inputs:\n"
        "      ref:\n"
        "        description: The commit to test.\n"
        "        type: string\n"
        "        required: false\n"
        "        default: ''\n"
        f"{inputs}"
        "permissions:\n"
        "  contents: read\n"
        "jobs:\n"
        f"  {job}:\n"
        "    runs-on: ubuntu-latest\n"
        "    timeout-minutes: 5\n"
        "    steps:\n"
        "      - uses: actions/checkout@v7\n"
        "        with:\n"
        "          ref: ${{ inputs.ref }}\n"
        f"      - run: echo {body}\n")


def lib_file(name, version, body):
    return (f"// repo-infra: {name} v{version}\n//\n// Purpose: Test library.\n"
            "// Choose: In tests.\n// Supplies: Nothing.\n'use strict';\n" + body + "\n")


def _version(text):
    return parse_markers(text)[0].version


def make_assets(root, current, history=(), core=()):
    """A piece store under `root`.

    `current` maps a piece name to its text (a file piece, installed at
    .github/workflows/<name>.yml) or to {file name: text} (a directory piece,
    installed at .github/workflows/<name>/). `history` lists
    (name, file name or None, text) published before the current ones."""
    root = pathlib.Path(root)
    manifest = {"pieces": {}, "actions": {"actions/checkout": "v7"}, "gh": {}}
    record = {}
    versions = {}
    for name, text in current.items():
        folder = root / "pieces" / name
        if isinstance(text, dict):
            spec = {"target": f".github/workflows/{name}", "kind": "dir",
                    "header": sorted(text)[0], "group": "release"}
            (folder / name).mkdir(parents=True)
            for file, body in text.items():
                (folder / name / file).write_text(body, encoding="utf-8")
                record.setdefault(f"pieces/{name}/{name}/{file}", {})[
                    str(_version(body))] = digest(body)
            versions.setdefault(name, set()).add(_version(next(iter(text.values()))))
        else:
            spec = {"target": f".github/workflows/{name}.yml", "group": "ci"}
            folder.mkdir(parents=True)
            (folder / f"{name}.yml").write_text(text, encoding="utf-8")
            record.setdefault(f"pieces/{name}/{name}.yml", {})[str(_version(text))] = (
                digest(text))
            versions.setdefault(name, set()).add(_version(text))
        if name in core:
            spec["core"] = True
        manifest["pieces"][name] = spec
    for name, file, text in history:
        key = f"pieces/{name}/{name}/{file}" if file else f"pieces/{name}/{name}.yml"
        record.setdefault(key, {})[str(_version(text))] = digest(text)
        versions.setdefault(name, set()).add(_version(text))
    for name, found in versions.items():
        sections = "".join(f"## v{v}\n\nNotes for {name} v{v}.\n\n"
                           for v in sorted(found, reverse=True))
        (root / "pieces" / name / "CHANGES.md").write_text(f"# {name}\n\n{sections}",
                                                            encoding="utf-8")
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (root / "generations.json").write_text(json.dumps(record), encoding="utf-8")
    (root / "callers").mkdir()
    (root / "callers/ci-passed.yml").write_text(CI_PASSED, encoding="utf-8")
    return root


def install(root, path, text):
    target = pathlib.Path(root) / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target
```

- [ ] **Step 2: Write the failing model tests**

```python
# tests/test_piece_model.py
import pytest
from piecekit import lib_file, make_assets, workflow_piece

from repo_infra import pieces


def test_loads_a_file_piece_with_its_header(tmp_path):
    assets = make_assets(tmp_path, {"ri-x": workflow_piece("ri-x", 2)})
    piece = pieces.load_pieces(assets)["ri-x"]
    assert piece.version == 2
    assert piece.target == ".github/workflows/ri-x.yml"
    assert piece.workflow
    assert piece.header["Purpose"] == "Test piece ri-x."
    assert piece.header["Call"].splitlines()[0] == "x:"
    assert piece.header["Call"].splitlines()[1] == "  uses: ./.github/workflows/ri-x.yml"


def test_loads_a_directory_piece(tmp_path):
    assets = make_assets(tmp_path, {"lib-x": {"a.js": lib_file("lib-x", 3, "a"),
                                              "b.js": lib_file("lib-x", 3, "b")}})
    piece = pieces.load_pieces(assets)["lib-x"]
    assert piece.kind == "dir"
    assert sorted(piece.files) == [".github/workflows/lib-x/a.js",
                                   ".github/workflows/lib-x/b.js"]
    assert not piece.workflow
    assert piece.version == 3


def test_files_of_a_directory_piece_must_agree_on_the_version(tmp_path):
    assets = make_assets(tmp_path, {"lib-x": {"a.js": lib_file("lib-x", 3, "a"),
                                              "b.js": lib_file("lib-x", 2, "b")}})
    with pytest.raises(pieces.PieceError, match="b.js"):
        pieces.load_pieces(assets)


def test_the_marker_must_name_the_piece(tmp_path):
    assets = make_assets(tmp_path, {"ri-x": workflow_piece("ri-y", 1)})
    with pytest.raises(pieces.PieceError, match="repo-infra: ri-x vN"):
        pieces.load_pieces(assets)


@pytest.mark.parametrize("text, problem", [
    ("# repo-infra: p v1\n#\n# Choose: x\n# Supplies: y\nname: p\n", "Purpose"),
    ("# repo-infra: p v1\n#\n# Purpose: x\n# Colour: y\n", "Colour"),
    ("# repo-infra: p v1\n#\n# Purpose: x\n# Purpose: y\n", "twice"),
    ("name: p\n# repo-infra: p v1\n# Purpose: x\n", "Choose"),
    ("# other comment\n# repo-infra: p v1\n", "first comment line"),
])
def test_header_problems_are_named(text, problem):
    with pytest.raises(pieces.PieceError, match=problem):
        pieces.parse_header(text, "#")


def test_a_field_continues_on_indented_lines_and_ends_at_an_empty_comment():
    text = ("dnl repo-infra: p v1\ndnl\ndnl Purpose: one\ndnl   two\ndnl Choose: c\n"
            "dnl Supplies: s\ndnl\ndnl Prose that is not a field.\n")
    assert pieces.parse_header(text, "dnl") == {"Purpose": "one\ntwo", "Choose": "c",
                                                 "Supplies": "s"}


def test_published_maps_every_recorded_version_to_its_repository_path(tmp_path):
    old = workflow_piece("ri-x", 1, body="old")
    assets = make_assets(tmp_path, {"ri-x": workflow_piece("ri-x", 2)},
                         history=[("ri-x", None, old)])
    published = pieces.load_published(assets)["ri-x"][".github/workflows/ri-x.yml"]
    assert sorted(published) == [1, 2]


def test_upgrade_notes_cover_every_version_crossed(tmp_path):
    assets = make_assets(tmp_path, {"ri-x": workflow_piece("ri-x", 3)},
                         history=[("ri-x", None, workflow_piece("ri-x", 2, body="b")),
                                  ("ri-x", None, workflow_piece("ri-x", 1, body="a"))])
    assert pieces.upgrade_notes("ri-x", 1, 3, assets) == [
        (2, "Notes for ri-x v2."), (3, "Notes for ri-x v3.")]


def test_a_missing_section_says_so(tmp_path):
    assets = make_assets(tmp_path, {"ri-x": workflow_piece("ri-x", 2)})
    assert pieces.upgrade_notes("ri-x", 0, 2, assets)[0] == (
        1, "(no upgrade notes for this version)")
```

- [ ] **Step 3: Run them to verify they fail**

Run: `python3 -m pytest -q tests/test_piece_model.py`
Expected: FAIL with `ImportError: cannot import name 'pieces'`.

- [ ] **Step 4: Write `pieces.py`**

```python
# skills/repo-infra/scripts/repo_infra/pieces.py
"""The pieces repo-infra ships (D30), read from the asset store.

A piece is a file, or a directory of files, that a repository copies 1:1:
a reusable workflow, the workflow library, a make fragment. The manifest
names each piece and where it is installed; the marker on the first comment
line carries its version, and the header block below the marker says what
it is for, which the catalogue is generated from. generations.json holds
the hash of every version ever published, which is how check tells a copy
that is merely old from one that was edited.
"""

import json
import pathlib
import re
from dataclasses import dataclass

from .markers import parse_markers

ASSETS = pathlib.Path(__file__).resolve().parents[2] / "assets"

COMMENT = {".yml": "#", ".yaml": "#", ".mk": "#", ".js": "//", ".m4": "dnl", ".lua": "--"}
FIELDS = ("Purpose", "Choose", "Supplies", "Pieces", "Produces", "Call")
REQUIRED = ("Purpose", "Choose", "Supplies")
_FIELD = re.compile(r"^([A-Z][a-z]+):(?: (.*))?$")
_SECTION = re.compile(r"^## v(\d+)\s*$", re.MULTILINE)


class PieceError(Exception):
    """The asset store is inconsistent. A plugin defect, never a repository's."""


@dataclass
class Piece:
    name: str
    version: int
    target: str
    kind: str
    group: str
    core: bool
    files: dict
    header: dict

    @property
    def workflow(self):
        return self.kind == "file" and self.target.startswith(".github/workflows/")

    @property
    def needs(self):
        return [p.strip() for p in self.header.get("Pieces", "").split(",") if p.strip()]


def comment_of(path):
    return COMMENT[pathlib.PurePosixPath(path).suffix]


def parse_header(text, comment):
    """The header fields after the marker (D30), as {field: text}."""
    lines = text.split("\n")
    first = next((i for i, line in enumerate(lines) if line.strip().startswith(comment)),
                 None)
    if first is None or not parse_markers(lines[first]):
        raise PieceError("the marker must be the first comment line")
    fields, current, started = {}, None, False
    for line in lines[first + 1:]:
        stripped = line.strip()
        if not stripped.startswith(comment):
            break
        body = stripped[len(comment):]
        if body.strip() == "":
            if started:
                break
            continue
        body = body[1:] if body.startswith(" ") else body
        match = _FIELD.match(body)
        if match:
            key = match[1]
            if key not in FIELDS:
                raise PieceError(f"the header field {key} is not one of {', '.join(FIELDS)}")
            if key in fields:
                raise PieceError(f"the header field {key} appears twice")
            fields[key], current, started = (match[2] or "").rstrip(), key, True
        elif current is not None and body.startswith("  "):
            fields[current] += "\n" + body[2:].rstrip()
        else:
            break
    missing = [key for key in REQUIRED if key not in fields]
    if missing:
        raise PieceError(f"the header lacks {', '.join(missing)}")
    return {key: value.strip("\n") for key, value in fields.items()}


def _manifest(assets):
    return json.loads((pathlib.Path(assets) / "manifest.json").read_text(encoding="utf-8"))


def _source(name, spec):
    return f"pieces/{name}/{pathlib.PurePosixPath(spec['target']).name}"


def load_pieces(assets=ASSETS):
    assets = pathlib.Path(assets)
    found = {}
    for name, spec in _manifest(assets).get("pieces", {}).items():
        source = assets / _source(name, spec)
        kind = spec.get("kind", "file")
        if kind == "dir":
            files = {f"{spec['target']}/{child.name}": child.read_text(encoding="utf-8")
                     for child in sorted(source.iterdir()) if child.is_file()}
            lead = f"{spec['target']}/{spec['header']}"
        else:
            files = {spec["target"]: source.read_text(encoding="utf-8")}
            lead = spec["target"]
        version = None
        for path, text in files.items():
            markers = parse_markers(text)
            if not markers or markers[0].asset != name:
                raise PieceError(f"{path}: the first marker must be `repo-infra: {name} vN`")
            if version is None:
                version = markers[0].version
            elif markers[0].version != version:
                raise PieceError(f"{path}: v{markers[0].version}, but the piece {name} "
                                 f"is v{version}")
        try:
            header = parse_header(files[lead], comment_of(lead))
        except PieceError as error:
            raise PieceError(f"{lead}: {error}") from error
        found[name] = Piece(name, version, spec["target"], kind, spec.get("group", ""),
                            bool(spec.get("core")), files, header)
    return found


def load_published(assets=ASSETS):
    """{piece: {repository path: {version: sha256}}} from generations.json."""
    assets = pathlib.Path(assets)
    record = json.loads((assets / "generations.json").read_text(encoding="utf-8"))
    published = {}
    for name, spec in _manifest(assets).get("pieces", {}).items():
        source = _source(name, spec)
        entry = published.setdefault(name, {})
        for path, versions in record.items():
            if spec.get("kind") == "dir" and path.startswith(source + "/"):
                target = spec["target"] + path[len(source):]
            elif path == source:
                target = spec["target"]
            else:
                continue
            entry[target] = {int(v): digest for v, digest in versions.items()}
    return published


def changes_sections(text):
    marks = list(_SECTION.finditer(text))
    return {int(mark[1]): text[mark.end():(marks[i + 1].start() if i + 1 < len(marks)
                                            else len(text))].strip()
            for i, mark in enumerate(marks)}


def upgrade_notes(name, old, new, assets=ASSETS):
    """[(version, notes)] for every version after `old` up to `new`."""
    path = pathlib.Path(assets) / "pieces" / name / "CHANGES.md"
    sections = changes_sections(path.read_text(encoding="utf-8")) if path.is_file() else {}
    return [(v, sections.get(v) or "(no upgrade notes for this version)")
            for v in range(old + 1, new + 1)]
```

- [ ] **Step 5: Run the model tests**

Run: `python3 -m pytest -q tests/test_piece_model.py`
Expected: PASS.

- [ ] **Step 6: Add the manifest section and the invariant test over the real store**

Add `"pieces": {},` as the first key of `skills/repo-infra/assets/manifest.json`. In `tests/test_manifest.py`, add `"pieces"` to the expected set of top-level keys.

```python
# tests/test_pieces.py
"""Invariants every shipped piece holds (D30). Parametrized over the real
store, so a piece added later is checked the day it lands."""

import json
import pathlib
import re

import pytest

from repo_infra import workflow
from repo_infra.pieces import ASSETS, load_pieces

PIECES = load_pieces()
WORKFLOW_PIECES = sorted((p for p in PIECES.values() if p.workflow), key=lambda p: p.name)
# changelog and release-pr start runs of their own; every other workflow piece is called.
CALLED = [p for p in WORKFLOW_PIECES if p.group != "release"]
ALL = sorted(PIECES.values(), key=lambda p: p.name)
ACTIONS = json.loads((ASSETS / "manifest.json").read_text(encoding="utf-8"))["actions"]
GROUPS = {"ci", "release-build", "publish", "release", "build"}
_PINNED = re.compile(r"^([\w.-]+/[\w.-]+)@(v\d+)$")


def ids(piece):
    return piece.name


def doc_of(piece):
    return workflow.load(piece.files[piece.target])


@pytest.mark.parametrize("piece", ALL, ids=ids)
def test_a_piece_names_a_known_group_and_existing_pieces(piece):
    assert piece.group in GROUPS
    assert [n for n in piece.needs if n not in PIECES] == []


@pytest.mark.parametrize("piece", ALL, ids=ids)
def test_changes_has_a_section_for_the_current_version(piece):
    text = (ASSETS / "pieces" / piece.name / "CHANGES.md").read_text(encoding="utf-8")
    versions = [int(v) for v in re.findall(r"^## v(\d+)\s*$", text, re.MULTILINE)]
    assert piece.version in versions
    assert max(versions) == piece.version


@pytest.mark.parametrize("piece", CALLED, ids=ids)
def test_a_workflow_piece_is_a_described_reusable_workflow(piece):
    doc = doc_of(piece)
    face = workflow.interface(doc)
    assert face is not None, "no on: workflow_call"
    undescribed = [n for n, s in {**face.inputs, **face.secrets}.items()
                   if not s["description"].strip()]
    assert undescribed == []
    assert "permissions" in doc, "declare the workflow-level permissions"
    assert set(doc["on"]) == {"workflow_call"}, "a piece is only ever called"


@pytest.mark.parametrize("piece", WORKFLOW_PIECES, ids=ids)
def test_every_inline_job_has_a_timeout(piece):
    jobs = doc_of(piece)["jobs"]
    assert [j for j, job in jobs.items() if "uses" not in job
            and "timeout-minutes" not in job] == []


@pytest.mark.parametrize("piece", WORKFLOW_PIECES, ids=ids)
def test_actions_are_pinned_to_the_manifest(piece):
    wrong = []
    for job in doc_of(piece)["jobs"].values():
        for step in job.get("steps", []):
            match = _PINNED.match(step.get("uses", ""))
            if match and ACTIONS.get(match[1]) != match[2]:
                wrong.append(step["uses"])
    assert wrong == []
```

Two more invariants (the `Call:` snippet and the ref contract) need `callers.py` and are added in Task 3, Step 6.

- [ ] **Step 7: Run the gate and commit**

Run: `make check`
Expected: PASS; `test_pieces.py` reports its parametrized tests as skipped with an empty parameter set.

```bash
git add skills/repo-infra/scripts/repo_infra/pieces.py skills/repo-infra/assets/manifest.json \
  tests/piecekit.py tests/test_piece_model.py tests/test_pieces.py tests/test_manifest.py
git commit -m "Load pieces, their header and their published versions (D30)

A piece is named in the manifest, versioned by its marker and described by
the header block below the marker. generations.json already records each
version's hash; load_published maps them to repository paths, which is
what check compares installed bytes against.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Caller validation

**Files:**
- Modify: `skills/repo-infra/scripts/repo_infra/report.py` (add `Item`, `SECTIONS`, `ATTENTION` at the top; the render functions stay until Task 12)
- Create: `skills/repo-infra/scripts/repo_infra/callers.py`
- Test: `tests/test_callers.py`
- Modify: `tests/test_pieces.py` (two invariants)

**Interfaces:**
- Consumes: `workflow.load/interface/ReadError`, `pieces.ASSETS`, `Piece.workflow/target/header/group`.
- Produces:
  - `report.Item = namedtuple("Item", "section name state detail")`; `report.SECTIONS = ("pieces", "callers", "config", "administration")`; `report.ATTENTION = ("missing", "outdated", "edited", "unknown", "problem", "conflict")`.
  - `callers.read_workflows(repo_root) -> dict[str, dict | workflow.ReadError]` keyed by file name.
  - `callers.jobs(doc) -> dict[str, dict]`, `callers.local_target(uses) -> str | None`, `callers.needs(job) -> list[str]`, `callers.calls(docs, target) -> bool`.
  - `callers.call_problems(job_id, job, docs) -> list[str]`.
  - `callers.closing_problems(docs, assets=ASSETS) -> list[tuple[str, str]]`.
  - `callers.ref_problems(doc, reserved, skip=()) -> list[str]`; `callers.ref_contract_problems(docs, piece_files) -> list[tuple[str, str]]`.
  - `callers.validate(docs, pieces, assets=ASSETS) -> list[Item]` (section `callers`). Task 4 adds permissions to it.

- [ ] **Step 1: Add the item type to `report.py`**

Insert after the imports of `report.py`:

```python
from collections import namedtuple

# D30. One row of the report: which part of the repository it is about, the
# piece, file or setting, its state and what to do about it.
Item = namedtuple("Item", "section name state detail")
SECTIONS = ("pieces", "callers", "config", "administration")
# check's exit code and the report's count both read this, so they cannot
# disagree about what needs attention.
ATTENTION = ("missing", "outdated", "edited", "unknown", "problem", "conflict")
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_callers.py
import pytest
from piecekit import CI_PASSED, install, make_assets, workflow_piece

from repo_infra import callers, workflow
from repo_infra.pieces import load_pieces

PIECE_INPUTS = ("      target:\n        description: The make target.\n"
                "        type: string\n        required: true\n")


@pytest.fixture
def store(tmp_path):
    return make_assets(tmp_path / "assets", {
        "ri-a": workflow_piece("ri-a", 1),
        "ri-b": workflow_piece("ri-b", 1, inputs=PIECE_INPUTS)})


def repo(tmp_path, store, files):
    root = tmp_path / "repo"
    for name, piece in load_pieces(store).items():
        install(root, piece.target, piece.files[piece.target])
    for name, text in files.items():
        install(root, f".github/workflows/{name}", text)
    return root


CI = """name: CI
on:
  push:
    branches: [main]
  workflow_call:
    inputs:
      ref:
        description: The commit.
        type: string
        required: false
        default: ''
permissions:
  contents: read
jobs:
  a:
    uses: ./.github/workflows/ri-a.yml
    with:
      ref: ${{ inputs.ref }}
""" + CI_PASSED.replace("jobs:\n", "").replace("needs: []", "needs: [a]")

BUILD = """name: Release build
on:
  workflow_call:
    inputs:
      version:
        description: v
        type: string
        required: true
      ref:
        description: r
        type: string
        required: true
permissions:
  contents: read
jobs:
  noop:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - run: echo ok
"""

PUBLISH = """name: Publish
on:
  push:
    branches: [main]
permissions:
  contents: read
jobs:
  publish:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - run: echo publish
  finalize:
    needs: [publish]
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - run: echo finalize
"""


def problems(tmp_path, store, **files):
    base = {"ci.yml": CI, "release-build.yml": BUILD, "release-publish.yml": PUBLISH}
    base.update({k.replace("_", "-") + ".yml": v for k, v in files.items()})
    docs = callers.read_workflows(repo(tmp_path, store, base))
    return [(i.name, i.state, i.detail) for i in
            callers.validate(docs, load_pieces(store), store)]


def test_a_conforming_set_of_callers_has_no_problem(tmp_path, store):
    assert problems(tmp_path, store) == []


def test_a_missing_core_caller_is_named(tmp_path, store):
    root = repo(tmp_path, store, {"ci.yml": CI, "release-build.yml": BUILD})
    found = callers.validate(callers.read_workflows(root), load_pieces(store), store)
    assert [(i.name, i.state) for i in found] == [("release-publish.yml", "missing")]


def test_calling_a_file_that_does_not_exist(tmp_path, store):
    found = problems(tmp_path, store, ci=CI.replace("ri-a.yml", "ri-zz.yml"))
    assert ("ci.yml", "problem", "job a calls ri-zz.yml, which does not exist") in found


def test_an_input_the_piece_does_not_declare(tmp_path, store):
    found = problems(tmp_path, store,
                     ci=CI.replace("      ref: ${{ inputs.ref }}\n",
                                   "      ref: ${{ inputs.ref }}\n      colour: red\n", 1))
    assert ("ci.yml", "problem",
            "job a calls ri-a.yml with the input colour, which ri-a.yml does not declare"
            ) in found


def test_a_required_input_not_passed(tmp_path, store):
    found = problems(tmp_path, store, ci=CI.replace("ri-a.yml", "ri-b.yml"))
    assert ("ci.yml", "problem",
            "job a calls ri-b.yml without its required input target") in found


def test_a_required_secret_needs_passing_or_inherit(tmp_path, store):
    secret = ("    secrets:\n      TOKEN:\n        description: t\n"
              "        required: true\n")
    called = workflow_piece("ri-a", 1).replace("permissions:\n", secret + "permissions:\n", 1)
    own = called.replace("repo-infra: ri-a v1", "own").replace("# Purpose", "# P")
    found = problems(tmp_path, store, ci=CI.replace("ri-a.yml", "own.yml"), own=own)
    assert any("without its required secret TOKEN" in d for _, _, d in found)
    inherited = CI.replace("ri-a.yml", "own.yml").replace(
        "      ref: ${{ inputs.ref }}\n", "      ref: ${{ inputs.ref }}\n    secrets: inherit\n", 1)
    assert not any("TOKEN" in d for _, _, d in problems(tmp_path / "2", store,
                                                        ci=inherited, own=own))


def test_a_remote_reusable_workflow_is_a_problem(tmp_path, store):
    found = problems(tmp_path, store, ci=CI.replace(
        "./.github/workflows/ri-a.yml", "oposs/repo-infra/.github/workflows/ri-a.yml@v1"))
    assert any("another repository" in d for _, _, d in found)


def test_an_unreadable_caller_is_one_problem_and_the_rest_is_still_validated(tmp_path, store):
    found = problems(tmp_path, store, ci_local="jobs:\n  x:\n    with: {ref: y}\n",
                     ci=CI.replace("ri-a.yml", "ri-zz.yml"))
    assert ("ci-local.yml", "problem",
            "cannot be read: line 3: a flow mapping; write it in block style") in found
    assert any(d.endswith("ri-zz.yml, which does not exist") for _, _, d in found)


def test_ci_passed_must_need_every_other_job(tmp_path, store):
    found = problems(tmp_path, store, ci=CI.replace("needs: [a]", "needs: []"))
    assert ("ci.yml", "problem",
            "ci-passed does not need a; it would report green while that job fails") in found


def test_ci_passed_must_run_always(tmp_path, store):
    found = problems(tmp_path, store, ci=CI.replace("if: always()", "if: success()"))
    assert any("lacks `if: always()`" in d for _, _, d in found)


def test_ci_passed_must_follow_the_pattern(tmp_path, store):
    found = problems(tmp_path, store, ci=CI.replace("timeout-minutes: 5\n    steps:\n      - if",
                                                    "timeout-minutes: 9\n    steps:\n      - if"))
    assert any("differs from the pattern" in d for _, _, d in found)


def test_finalize_must_need_every_other_job(tmp_path, store):
    extra = PUBLISH + ("  crates:\n    needs: [publish]\n    runs-on: ubuntu-latest\n"
                       "    timeout-minutes: 5\n    steps:\n      - run: echo\n")
    found = problems(tmp_path, store, release_publish=extra)
    assert ("release-publish.yml", "problem",
            "finalize does not need crates; it would publish the release before that job "
            "attached its files") in found


def test_an_inline_job_of_ci_yml_must_check_out_ref(tmp_path, store):
    job = ("  own:\n    runs-on: ubuntu-latest\n    timeout-minutes: 5\n    steps:\n"
           "      - uses: actions/checkout@v7\n")
    found = problems(tmp_path, store, ci=CI.replace("jobs:\n", "jobs:\n" + job, 1)
                     .replace("needs: [a]", "needs: [own, a]"))
    assert any(d.startswith("job own has an actions/checkout step without") for _, _, d in found)


def test_a_project_workflow_called_with_ref_is_held_to_the_contract(tmp_path, store):
    local = """on:
  workflow_call:
    inputs:
      ref:
        description: r
        type: string
        required: false
        default: ''
jobs:
  t:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@v7
        with:
          ref: ${{ inputs.ref }}
      - uses: actions/upload-artifact@v7
        with:
          name: release-asset-x
"""
    ci = CI.replace("ri-a.yml", "ci-local.yml")
    found = problems(tmp_path, store, ci=ci, ci_local=local)
    assert ("ci-local.yml", "problem",
            "job t uploads an artifact named release-asset-x, a name reserved for the "
            "release build") in found
    clean = local.replace("release-asset-x", "coverage")
    assert problems(tmp_path / "2", store, ci=ci, ci_local=clean) == []


def test_ci_passed_may_check_out_the_base_commit():
    pattern = workflow.load(CI_PASSED)
    assert callers.ref_problems(pattern, True, skip=("ci-passed",)) == []
```

- [ ] **Step 3: Run them to verify they fail**

Run: `python3 -m pytest -q tests/test_callers.py`
Expected: FAIL with `ImportError: cannot import name 'callers'`.

- [ ] **Step 4: Write `callers.py`**

```python
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
```

- [ ] **Step 5: Run the caller tests**

Run: `python3 -m pytest -q tests/test_callers.py`
Expected: PASS.

- [ ] **Step 6: Add the two piece invariants that need `callers.py`**

Append to `tests/test_pieces.py`:

```python
from repo_infra import callers  # noqa: E402


@pytest.mark.parametrize("piece", CALLED, ids=ids)
def test_the_call_snippet_calls_this_piece_correctly(piece):
    snippet = workflow.load(piece.header["Call"])
    assert len(snippet) == 1, "Call: holds exactly one job"
    (job_id, job), = snippet.items()
    file = pathlib.PurePosixPath(piece.target).name
    assert job["uses"] == f"./.github/workflows/{file}"
    assert callers.call_problems(job_id, job, {file: doc_of(piece)}) == []


@pytest.mark.parametrize("piece", [p for p in CALLED
                                   if p.group in ("ci", "release-build")], ids=ids)
def test_a_ci_or_build_piece_keeps_the_ref_contract(piece):
    assert callers.ref_problems(doc_of(piece), reserved=piece.group == "ci") == []
```

Move the `from repo_infra import callers` line up into the import block when ruff asks.

- [ ] **Step 7: Run the gate and commit**

Run: `make check`
Expected: PASS.

```bash
git add skills/repo-infra/scripts/repo_infra/report.py skills/repo-infra/scripts/repo_infra/callers.py \
  tests/test_callers.py tests/test_pieces.py
git commit -m "Validate callers against the workflows they call (D30)

GitHub checks a call to a reusable workflow only when the run starts. check
now reads each call and reports an input the called file does not declare,
a required input or secret not passed, a missing file, a remote reference,
the needs: list of ci-passed and finalize, and the D28 ref contract on the
YAML structure instead of the text.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Token permissions across calls

**Files:**
- Modify: `skills/repo-infra/scripts/repo_infra/callers.py`
- Test: `tests/test_permissions.py`

**Interfaces:**
- Consumes: `callers.jobs`, `callers.local_target`, `workflow.interface`.
- Produces: `callers.SCOPES: tuple[str]`; `callers.grant(value) -> dict[str, int] | None` (0 none, 1 read, 2 write); `callers.needed(name, docs) -> dict[str, int]`; `callers.permission_problems(docs) -> list[tuple[str, str]]`; `callers.permission_text(levels) -> str`. `validate()` includes permission problems.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_permissions.py
"""D30: a called workflow can only lower the permissions it receives, and
GitHub checks every job of the called file, skipped or not."""

from repo_infra import callers, workflow

PIECE = """on:
  workflow_call:
permissions:
  contents: read
jobs:
  mark:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    permissions:
      contents: read
      checks: write
    steps:
      - run: echo
"""


def caller(job_permissions="", top="permissions:\n  contents: read\n"):
    return workflow.load(
        "on:\n  push:\n" + top + "jobs:\n  mark:\n    uses: ./.github/workflows/p.yml\n"
        + job_permissions)


def found(ci):
    return callers.permission_problems({"ci.yml": ci, "p.yml": workflow.load(PIECE)})


def test_needed_takes_job_level_permissions_over_the_workflow_level():
    assert callers.needed("p.yml", {"p.yml": workflow.load(PIECE)}) == {"contents": 1,
                                                                       "checks": 2}


def test_a_workflow_level_grant_below_the_need_is_a_problem():
    assert found(caller()) == [(
        "ci.yml", "job mark grants contents: read and p.yml needs checks: write; GitHub "
        "refuses to start the run")]


def test_a_job_level_grant_covers_the_need():
    grant = "    permissions:\n      contents: read\n      checks: write\n"
    assert found(caller(grant)) == []


def test_no_permissions_anywhere_is_a_problem_at_the_top():
    assert found(caller(top="")) == [(
        "ci.yml", "job mark declares no permissions; p.yml needs checks: write, "
        "contents: read. Grant them on the job")]


def test_write_all_covers_everything():
    assert found(caller(top="permissions: write-all\n")) == []


def test_the_need_reaches_through_an_inheriting_call():
    middle = workflow.load("on:\n  workflow_call:\njobs:\n  inner:\n"
                           "    uses: ./.github/workflows/p.yml\n")
    top = workflow.load("on:\n  workflow_dispatch:\njobs:\n  test:\n"
                        "    uses: ./.github/workflows/ci.yml\n"
                        "    permissions:\n      contents: read\n")
    docs = {"release-pr.yml": top, "ci.yml": middle, "p.yml": workflow.load(PIECE)}
    assert callers.permission_problems(docs) == [(
        "release-pr.yml", "job test grants contents: read and ci.yml needs checks: write; "
        "GitHub refuses to start the run")]


def test_a_cycle_does_not_recurse_forever():
    loop = workflow.load("on:\n  workflow_call:\njobs:\n  again:\n"
                         "    uses: ./.github/workflows/loop.yml\n")
    assert callers.needed("loop.yml", {"loop.yml": loop}) == {}
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest -q tests/test_permissions.py`
Expected: FAIL with `AttributeError: module 'repo_infra.callers' has no attribute 'needed'`.

- [ ] **Step 3: Add the permission code to `callers.py`**

```python
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
        return dict.fromkeys(SCOPES, 1 if value == "read-all" else 2)
    if isinstance(value, dict):
        return {scope: LEVELS.get(str(level), 0) for scope, level in value.items()}
    return {}


def _own(doc, job):
    mine = grant(job.get("permissions"))
    return mine if mine is not None else grant(doc.get("permissions"))


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


def permission_problems(docs):
    found = []
    for name, doc in docs.items():
        for job_id, job in jobs(doc).items():
            called = local_target(job.get("uses"))
            if called is None or not isinstance(docs.get(called), dict):
                continue
            want = needed(called, docs)
            have = _own(doc, job)
            if have is None:
                # A called file inherits what its caller grants, and the
                # caller is checked against this file's needs. A file that
                # starts a run has nothing above it.
                if want and workflow.interface(doc) is None:
                    found.append((name, f"job {job_id} declares no permissions; {called} "
                                        f"needs {permission_text(want)}. Grant them on the job"))
                continue
            short = {scope: level for scope, level in want.items() if have.get(scope, 0) < level}
            if short:
                found.append((name, f"job {job_id} grants {permission_text(have) or 'nothing'} "
                                    f"and {called} needs {permission_text(short)}; GitHub "
                                    "refuses to start the run"))
    return found
```

In `validate()`, change the line that builds `found` to:

```python
    found = (closing_problems(docs, assets) + ref_contract_problems(docs, piece_files)
             + permission_problems(docs))
```

- [ ] **Step 4: Run the tests**

Run: `python3 -m pytest -q tests/test_permissions.py tests/test_callers.py`
Expected: PASS. The `CI` fixture of `test_callers.py` calls `ri-a`, which asks only for `contents: read`, so it stays clean.

- [ ] **Step 5: Run the gate and commit**

Run: `make check`
Expected: PASS.

```bash
git add skills/repo-infra/scripts/repo_infra/callers.py tests/test_permissions.py
git commit -m "Check that every call grants what the called workflow needs (D30)

A called workflow can only lower the token permissions it receives, and
GitHub checks every job of the called file before the run starts. Create
release PR grants ci.yml a fixed set, so a caller that asks for more would
break every release. check now compares each call's grant with what the
called file's jobs ask for, through nested calls.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Piece states, config and the check engine

**Files:**
- Create: `skills/repo-infra/scripts/repo_infra/check.py`
- Test: `tests/test_check.py`

**Interfaces:**
- Consumes: `pieces.load_pieces/load_published/ASSETS`, `callers.read_workflows/validate/calls`, `markers.parse_markers`, `report.Item`, `remote.Facts`.
- Produces:
  - `check.PieceState = namedtuple("PieceState", "state installed edited")`; `state` is `absent`, `current`, `outdated` or `edited`; `installed` is the lowest installed version (`outdated`), the marker's claim (`edited`) or None; `edited` lists the edited paths.
  - `check.piece_state(repo_root, piece, history) -> PieceState`.
  - `check.missing_dependencies(pieces, states) -> list[tuple[str, str]]` (piece, the piece that needs it).
  - `check.piece_items(repo_root, pieces, published) -> list[Item]`, `check.unknown_items(repo_root, pieces) -> list[Item]`.
  - `check.refused_release_files(entries, version_files) -> list[tuple]` (moved verbatim from `state.py`).
  - `check.config_items(repo_root, docs) -> list[Item]`, `check.path_filter_items(docs) -> list[Item]`, `check.classify_remote(facts) -> list[Item]`.
  - `check.run(repo_root, facts, assets=ASSETS) -> list[Item]`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_check.py
import json

import pytest
from piecekit import install, lib_file, make_assets, workflow_piece

from repo_infra import callers, check
from repo_infra.pieces import load_pieces, load_published
from repo_infra.remote import Facts

OLD = workflow_piece("ri-x", 1, body="old")
NEW = workflow_piece("ri-x", 2, body="new")
LIB1 = {"a.js": lib_file("lib-x", 1, "a1"), "b.js": lib_file("lib-x", 1, "b1")}
LIB2 = {"a.js": lib_file("lib-x", 2, "a2"), "b.js": lib_file("lib-x", 2, "b2")}


@pytest.fixture
def store(tmp_path):
    history = [("ri-x", None, OLD)] + [("lib-x", f, t) for f, t in LIB1.items()]
    return make_assets(tmp_path / "assets", {"ri-x": NEW, "lib-x": LIB2}, history,
                       core=("lib-x",))


def rows(root, store):
    items = check.piece_items(root, load_pieces(store), load_published(store))
    return [(i.name, i.state, i.detail) for i in items]


def test_a_copy_of_the_latest_version_is_current(tmp_path, store):
    root = tmp_path / "repo"
    install(root, ".github/workflows/ri-x.yml", NEW)
    for f, t in LIB2.items():
        install(root, f".github/workflows/lib-x/{f}", t)
    assert rows(root, store) == [("lib-x", "current", "v2"), ("ri-x", "current", "v2")]


def test_a_copy_of_an_older_version_is_outdated(tmp_path, store):
    root = tmp_path / "repo"
    install(root, ".github/workflows/ri-x.yml", OLD)
    assert ("ri-x", "outdated", "v1 installed, v2 available; apply replaces it") in rows(
        root, store)


def test_a_copy_that_matches_no_version_is_edited(tmp_path, store):
    root = tmp_path / "repo"
    install(root, ".github/workflows/ri-x.yml", NEW + "# mine\n")
    (name, state, detail), = [r for r in rows(root, store) if r[0] == "ri-x"]
    assert state == "edited"
    assert detail.startswith(".github/workflows/ri-x.yml matches no published version")


def test_a_marker_newer_than_the_plugin_says_update_the_plugin(tmp_path, store):
    root = tmp_path / "repo"
    install(root, ".github/workflows/ri-x.yml", workflow_piece("ri-x", 9))
    assert ("ri-x", "edited", ".github/workflows/ri-x.yml says v9, newer than this "
            "plugin's v2; update the plugin") in rows(root, store)


def test_a_core_piece_that_is_absent_is_missing_and_another_is_not_reported(tmp_path, store):
    assert rows(tmp_path / "repo", store) == [
        ("lib-x", "missing", "not installed; every repository carries it")]


def test_a_half_upgraded_directory_is_outdated(tmp_path, store):
    root = tmp_path / "repo"
    install(root, ".github/workflows/lib-x/a.js", LIB2["a.js"])
    install(root, ".github/workflows/lib-x/b.js", LIB1["b.js"])
    assert ("lib-x", "outdated", "v1 installed, v2 available; apply replaces it") in rows(
        root, store)


def test_a_project_file_in_a_piece_directory_is_ignored(tmp_path, store):
    root = tmp_path / "repo"
    for f, t in LIB2.items():
        install(root, f".github/workflows/lib-x/{f}", t)
    install(root, ".github/workflows/lib-x/own.js", "module.exports = {};\n")
    assert ("lib-x", "current", "v2") in rows(root, store)


def test_a_dependency_that_is_absent_is_missing(tmp_path):
    needy = workflow_piece("ri-y", 1, header="# Pieces: ri-x\n")
    store = make_assets(tmp_path / "assets", {"ri-x": NEW, "ri-y": needy})
    root = tmp_path / "repo"
    install(root, ".github/workflows/ri-y.yml", needy)
    assert ("ri-x", "missing", "ri-y needs it") in rows(root, store)


def test_an_assembled_file_is_unknown_and_points_at_onboarding(tmp_path, store):
    root = tmp_path / "repo"
    install(root, ".github/workflows/ci.yml", "name: CI\n# repo-infra: ci v2\n"
            "jobs:\n  # repo-infra: ci-rust v3\n  rust-plan:\n    runs-on: x\n")
    (row,) = [r for r in rows(root, store) if r[1] == "unknown"]
    assert row[0] == "ci"
    assert row[2].startswith(".github/workflows/ci.yml carries `repo-infra: ci v2`")
    assert "references/onboarding.md" in row[2]


def config(tmp_path, data, docs=None):
    root = tmp_path / "repo"
    if data is not None:
        install(root, ".github/repo-infra.json",
                data if isinstance(data, str) else json.dumps(data))
    return [(i.name, i.state, i.detail) for i in check.config_items(root, docs or {})]


VERSIONS = [{"path": "pyproject.toml", "pattern": "x", "replacement": "y", "verify": "z"}]


def test_a_missing_config_is_missing(tmp_path):
    assert config(tmp_path, None)[0][1] == "missing"


def test_a_config_that_is_not_json(tmp_path):
    assert config(tmp_path, "{")[0][1] == "problem"


def test_obsolete_and_unknown_keys_are_problems(tmp_path):
    found = config(tmp_path, {"version_files": VERSIONS, "ci": ["ci-man"],
                              "ecosystems": [], "colour": 1, "_comment": "fine"})
    assert ("repo-infra.json", "problem", "ci, ecosystems: no longer read; the callers "
            "state this now (D30). Remove them") in found
    assert ("repo-infra.json", "problem", "colour: not a key repo-infra reads") in found


def test_empty_version_files_is_a_problem(tmp_path):
    assert config(tmp_path, {})[0][2].startswith("version_files is empty")


def test_refused_release_files_are_reported(tmp_path):
    found = config(tmp_path, {"version_files": VERSIONS,
                              "release_files": ["CHANGES.md", ".github/x", "dist/a"]})
    assert ("release_files", "problem",
            "CHANGES.md is CHANGES.md, which the release pull request rolls; .github/x is "
            "under .github/") in found


def test_gitea_config_is_needed_only_when_the_gitea_piece_is_called(tmp_path):
    docs = {"release-publish.yml": {"jobs": {"gitea": {
        "uses": "./.github/workflows/ri-publish-gitea.yml"}}}}
    base = {"version_files": VERSIONS}
    assert config(tmp_path, base) == []
    found = config(tmp_path, base, docs)
    assert found[0][0] == "gitea_packages" and "url and owner" in found[0][2]


def test_a_required_workflow_with_a_paths_filter_is_a_conflict():
    docs = {"ci.yml": {"on": {"pull_request": {"paths": ["src/**"]}}}}
    assert [(i.name, i.state) for i in check.path_filter_items(docs)] == [("ci.yml", "conflict")]


CONFORMING = Facts(default_branch="main", protected=True,
                   required_contexts={"ci-passed", "changelog-updated"},
                   labels={"no-changelog"}, workflow_permissions="write",
                   can_approve_pr=True, strict=True)


def test_administration_items_are_their_own_section():
    assert {(i.section, i.state) for i in check.classify_remote(CONFORMING)} == {
        ("administration", "ok")}


def test_run_puts_the_sections_together(tmp_path, store):
    root = tmp_path / "repo"
    install(root, ".github/workflows/ri-x.yml", OLD)
    items = check.run(root, CONFORMING, store)
    assert {i.section for i in items} == {"pieces", "callers", "config", "administration"}
    assert callers.read_workflows(root)
```

Then move the remote-item tests from `tests/test_state.py` (every test that calls `classify_remote`) into `tests/test_check.py`, calling `check.classify_remote` and comparing `(name, state, detail)` of each item, so `section` does not change the assertions.

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest -q tests/test_check.py`
Expected: FAIL with `ImportError: cannot import name 'check'`.

- [ ] **Step 3: Write `check.py`**

```python
# skills/repo-infra/scripts/repo_infra/check.py
"""check (D30): the state of every piece, the callers, the config and the
administration items.

It reports and never writes, and it never refuses a repository because
nothing matched it: choosing pieces is the AI's judgement. A piece is
identified by its bytes against every published version, never by its
marker: the marker says which version a file claims to be, the bytes say
whether it is one.
"""

import hashlib
import json
import pathlib
import posixpath
from collections import namedtuple

from . import callers
from .markers import parse_markers
from .pieces import ASSETS, load_pieces, load_published
from .report import Item

PieceState = namedtuple("PieceState", "state installed edited")

CONFIG = ".github/repo-infra.json"
# What the borrowed release machinery reads (release-pr.yml, lib/*.js).
KEYS = ("version_files", "release_assets", "release_files", "gitea_packages",
        "moving_major_tag", "rust")
OBSOLETE = ("ecosystems", "ci", "ci_local", "publish", "build", "publish_local",
            "release_build", "release_build_local", "skip", "answers")
SCANNED = (".github", "build", "m4")
REQUIRED_WORKFLOWS = ("ci.yml", "changelog.yml")


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def piece_state(repo_root, piece, history):
    root = pathlib.Path(repo_root)
    paths = sorted(set(history) | set(piece.files))
    installed = {p: (root / p).read_bytes() for p in paths if (root / p).is_file()}
    if not installed:
        return PieceState("absent", None, [])
    versions, edited = {}, []
    for path, data in installed.items():
        matches = [v for v, d in history.get(path, {}).items() if d == _digest(data)]
        if matches:
            versions[path] = max(matches)
        else:
            edited.append(path)
    if edited:
        markers = parse_markers(installed[edited[0]].decode("utf-8", errors="replace"))
        claimed = next((m.version for m in markers if m.asset == piece.name), None)
        return PieceState("edited", claimed, edited)
    current = (set(installed) == set(piece.files)
               and all(versions[p] == piece.version for p in piece.files))
    return PieceState("current" if current else "outdated", min(versions.values()), [])


def missing_dependencies(pieces, states):
    found = {}
    for name, state in sorted(states.items()):
        if state.state == "absent":
            continue
        for dep in pieces[name].needs:
            if dep in states and states[dep].state == "absent":
                found.setdefault(dep, name)
    return sorted(found.items())


def _edited(piece, state):
    files = ", ".join(state.edited)
    if state.installed and state.installed > piece.version:
        return (f"{files} says v{state.installed}, newer than this plugin's "
                f"v{piece.version}; update the plugin")
    return (f"{files} matches no published version of {piece.name}. Pieces are used as "
            "published: move the change into a caller. apply stops here with the files "
            "for a hand merge")


def unknown_items(repo_root, pieces):
    root = pathlib.Path(repo_root)
    items = []
    for top in SCANNED:
        base = root / top
        if not base.is_dir():
            continue
        for path in sorted(p for p in base.rglob("*") if p.is_file()):
            try:
                markers = parse_markers(path.read_text(encoding="utf-8"))
            except (UnicodeDecodeError, OSError):
                continue
            if markers and markers[0].asset not in pieces:
                first = markers[0]
                items.append(Item(
                    "pieces", first.asset, "unknown",
                    f"{path.relative_to(root).as_posix()} carries `repo-infra: {first.asset} "
                    f"v{first.version}` and repo-infra ships no such piece. A file of the "
                    "assembled standard (ci, release-build, release-publish) is a caller "
                    "now: rewrite it from references/onboarding.md"))
    return items


def piece_items(repo_root, pieces, published):
    states = {name: piece_state(repo_root, piece, published.get(name, {}))
              for name, piece in pieces.items()}
    items = []
    for name, state in sorted(states.items()):
        piece = pieces[name]
        if state.state == "absent":
            if piece.core:
                items.append(Item("pieces", name, "missing",
                                  "not installed; every repository carries it"))
        elif state.state == "current":
            items.append(Item("pieces", name, "current", f"v{piece.version}"))
        elif state.state == "outdated":
            items.append(Item("pieces", name, "outdated",
                              f"v{state.installed} installed, v{piece.version} available; "
                              "apply replaces it"))
        else:
            items.append(Item("pieces", name, "edited", _edited(piece, state)))
    reported = {i.name for i in items if i.state == "missing"}
    items += [Item("pieces", dep, "missing", f"{user} needs it")
              for dep, user in missing_dependencies(pieces, states) if dep not in reported]
    return items + unknown_items(repo_root, pieces)
```

Then move `refused_release_files` from `state.py` into `check.py` verbatim, with its comment line `# The JS refusedReleaseFiles in workflows/lib/release.js enforces the same rule; change both.` above it. Leave the copy in `state.py` until Task 14.

```python
def config_items(repo_root, docs):
    path = pathlib.Path(repo_root) / CONFIG
    if not path.is_file():
        return [Item("config", "repo-infra.json", "missing",
                     f"{CONFIG} does not exist; Create release PR reads version_files "
                     "from it")]
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        return [Item("config", "repo-infra.json", "problem", f"{CONFIG} is not JSON: {error}")]
    if not isinstance(config, dict):
        return [Item("config", "repo-infra.json", "problem", f"{CONFIG} is not a JSON object")]
    items = []
    old = [key for key in config if key in OBSOLETE]
    if old:
        items.append(Item("config", "repo-infra.json", "problem",
                          f"{', '.join(old)}: no longer read; the callers state this now "
                          "(D30). Remove them"))
    strange = [key for key in config
               if key not in KEYS and key not in OBSOLETE and not key.startswith("_")]
    if strange:
        items.append(Item("config", "repo-infra.json", "problem",
                          f"{', '.join(strange)}: not a key repo-infra reads"))
    if not config.get("version_files"):
        items.append(Item("config", "version_files", "problem",
                          "version_files is empty; Create release PR would bump no file"))
    refused = refused_release_files(config.get("release_files", []),
                                    config.get("version_files", []))
    if refused:
        items.append(Item("config", "release_files", "problem",
                          "; ".join(f"{entry} {reason}" for entry, reason in refused)))
    if callers.calls(docs, "ri-publish-gitea.yml"):
        gitea = config.get("gitea_packages")
        gitea = gitea if isinstance(gitea, dict) else {}
        absent = [key for key in ("url", "owner") if not gitea.get(key)]
        if absent:
            items.append(Item("config", "gitea_packages", "problem",
                              "ri-publish-gitea reads \"gitea_packages\" in "
                              f"{CONFIG} and it lacks {' and '.join(absent)}; set \"url\" "
                              "(the Gitea base URL) and \"owner\""))
    return items


def path_filter_items(docs):
    items = []
    for name in REQUIRED_WORKFLOWS:
        doc = docs.get(name)
        on = doc.get("on") if isinstance(doc, dict) else None
        if not isinstance(on, dict):
            continue
        if any(isinstance(spec, dict) and {"paths", "paths-ignore"} & set(spec)
               for spec in on.values()):
            items.append(Item("callers", name, "conflict",
                              f"{name} filters on paths; a required check would leave every "
                              "unmatched pull request pending forever. Move the condition "
                              "into the job (D13)"))
    return items
```

The detail test for `test_refused_release_files_are_reported` expects the entries in input order and the reasons `refused_release_files` already writes; `dist/a` is accepted.

Then move `classify_remote` from `state.py` into `check.py` verbatim, changing each `Item(name, state, detail)` it builds to `Item("administration", name, state, detail)`.

```python
def run(repo_root, facts, assets=ASSETS):
    pieces = load_pieces(assets)
    docs = callers.read_workflows(repo_root)
    return (piece_items(repo_root, pieces, load_published(assets))
            + callers.validate(docs, pieces, assets)
            + config_items(repo_root, docs)
            + path_filter_items(docs)
            + classify_remote(facts))
```

`posixpath` is used by `refused_release_files`.

- [ ] **Step 4: Run the tests**

Run: `python3 -m pytest -q tests/test_check.py`
Expected: PASS.

- [ ] **Step 5: Run the gate and commit**

Run: `make check`
Expected: PASS.

```bash
git add skills/repo-infra/scripts/repo_infra/check.py tests/test_check.py
git commit -m "Report each piece as current, outdated, edited or unknown (D30)

A copy is compared byte for byte with every published version of its piece:
a match on the latest is current, a match on an older one is outdated and
apply may replace it, no match is edited. A marker that names no piece, as
the assembled ci.yml carries, is unknown and points at onboarding. The
config check reports the keys D30 dropped.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: The catalogue generator

**Files:**
- Create: `skills/repo-infra/scripts/repo_infra/catalogue.py`
- Create: `skills/repo-infra/references/catalogue.md` (generated)
- Modify: `Makefile` (target `catalogue`)
- Test: `tests/test_catalogue.py`

**Interfaces:**
- Consumes: `pieces.load_pieces`, `workflow.load/interface`, `callers.needed/permission_text`.
- Produces: `catalogue.GROUPS`, `catalogue.entry(piece) -> str`, `catalogue.render(pieces) -> str`, `catalogue.main(argv) -> int` (writes the file named in `argv[0]`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_catalogue.py
import pathlib

from piecekit import make_assets, workflow_piece

from repo_infra import catalogue
from repo_infra.pieces import load_pieces

ROOT = pathlib.Path(__file__).resolve().parents[1]
CATALOGUE = ROOT / "skills/repo-infra/references/catalogue.md"


def test_the_committed_catalogue_is_what_the_pieces_say():
    assert CATALOGUE.read_text(encoding="utf-8") == catalogue.render(load_pieces()), (
        "run make catalogue")


def test_an_entry_shows_header_inputs_permissions_and_the_call(tmp_path):
    extra = ("      target:\n        description: The make target.\n"
             "        type: string\n        required: true\n")
    store = make_assets(tmp_path, {"ri-x": workflow_piece("ri-x", 2, inputs=extra)})
    text = catalogue.entry(load_pieces(store)["ri-x"])
    assert text.startswith("### ri-x v2\n\nInstalled at `.github/workflows/ri-x.yml`.")
    assert "**Purpose:** Test piece ri-x." in text
    assert "| `ref` | string | no | `''` | The commit to test. |" in text
    assert "| `target` | string | yes |  | The make target. |" in text
    assert "**Permissions it needs:** contents: read" in text
    assert "```yaml\nx:\n  uses: ./.github/workflows/ri-x.yml\n" in text
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest -q tests/test_catalogue.py`
Expected: FAIL with `ImportError: cannot import name 'catalogue'`.

- [ ] **Step 3: Write `catalogue.py`**

```python
# skills/repo-infra/scripts/repo_infra/catalogue.py
"""Write references/catalogue.md from the pieces themselves (D30).

`make catalogue` runs this. tests/test_catalogue.py fails when the committed
file differs, so the catalogue cannot fall behind the pieces it describes.
"""

import pathlib
import sys

from . import callers, workflow
from .pieces import load_pieces

GROUPS = (("ci", "CI: called from ci.yml"),
          ("release-build", "Release build: called from release-build.yml"),
          ("publish", "Publish: called from release-publish.yml"),
          ("release", "Release flow: installed, never called by hand"),
          ("build", "Build files"))
LABELS = (("Purpose", "Purpose"), ("Choose", "Choose it when"),
          ("Supplies", "The repository supplies"), ("Pieces", "Needs the pieces"),
          ("Produces", "Produces"))
INTRO = """# Catalogue

Generated by `make catalogue` from the header block, the inputs and the
secrets of every piece. Do not edit it by hand.

`apply --item <piece>` installs a piece 1:1 and commits it. A workflow piece
then needs a job in a caller; the snippet under each one is that job.
"""


def _cell(text):
    return " ".join(str(text).split()).replace("|", "\\|")


def _default(value):
    if value is None:
        return ""
    return f"`{value}`" if value != "" else "`''`"


def entry(piece):
    lines = [f"### {piece.name} v{piece.version}", "", f"Installed at `{piece.target}`.", ""]
    for field, label in LABELS:
        if field in piece.header:
            lines += [f"**{label}:** {' '.join(piece.header[field].split())}", ""]
    if not piece.workflow:
        return "\n".join(lines)
    doc = workflow.load(piece.files[piece.target])
    face = workflow.interface(doc) or workflow.Interface({}, {}, ())
    if face.inputs:
        lines += ["| Input | Type | Required | Default | Description |",
                  "|---|---|---|---|---|"]
        lines += [f"| `{name}` | {spec['type']} | {'yes' if spec['required'] else 'no'} | "
                  f"{_default(spec['default'])} | {_cell(spec['description'])} |"
                  for name, spec in face.inputs.items()]
        lines.append("")
    if face.secrets:
        lines += ["| Secret | Required | Description |", "|---|---|---|"]
        lines += [f"| `{name}` | {'yes' if spec['required'] else 'no'} | "
                  f"{_cell(spec['description'])} |" for name, spec in face.secrets.items()]
        lines.append("")
    if face.outputs:
        lines += ["**Outputs:** " + ", ".join(f"`{name}`" for name in face.outputs), ""]
    file = pathlib.PurePosixPath(piece.target).name
    lines += [f"**Permissions it needs:** "
              f"{callers.permission_text(callers.needed(file, {file: doc})) or 'none'}", ""]
    if "Call" in piece.header:
        lines += ["```yaml", piece.header["Call"], "```", ""]
    return "\n".join(lines)


def render(pieces):
    parts = [INTRO]
    for group, title in GROUPS:
        members = sorted((p for p in pieces.values() if p.group == group),
                         key=lambda p: p.name)
        if members:
            parts.append(f"## {title}\n")
            parts += [entry(piece) for piece in members]
    return "\n".join(parts).rstrip("\n") + "\n"


def main(argv):
    target = pathlib.Path(argv[0])
    target.write_text(render(load_pieces()), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 4: Add the make target and generate the file**

Add `catalogue` to `.PHONY` in `Makefile` and:

```make
# D30: the catalogue in the skill is generated from the pieces. Run after
# adding or changing a piece; tests/test_catalogue.py fails when it is stale.
catalogue:
	PYTHONPATH=skills/repo-infra/scripts python3 -m repo_infra.catalogue \
	  skills/repo-infra/references/catalogue.md
```

Run: `make catalogue && python3 -m pytest -q tests/test_catalogue.py`
Expected: PASS. The file holds only the intro while the store is empty.

- [ ] **Step 5: Run the gate and commit**

Run: `make check`
Expected: PASS.

```bash
git add Makefile skills/repo-infra/scripts/repo_infra/catalogue.py \
  skills/repo-infra/references/catalogue.md tests/test_catalogue.py
git commit -m "Generate the piece catalogue from the pieces (D30)

The catalogue lists each piece's purpose, when to choose it, what the
repository supplies, its inputs, secrets and permissions, and the caller
job. It is generated from the header block and the workflow_call interface,
and a test fails when the committed file is stale.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Conversion rules used by Tasks 7 to 11

Every task below creates pieces from existing assets. The old asset stays where it is until Task 14, so the old code and its tests keep passing; the tests that run workflow text switch to the piece in the same task.

**R1. Layout.** `skills/repo-infra/assets/pieces/<name>/<file>` plus `pieces/<name>/CHANGES.md`; a manifest entry under `pieces` (`target`, `group`, and `core`, `kind`, `header` where stated).

**R2. Header.** The marker on the first comment line, then:

```
# repo-infra: <name> v<N>
#
# Purpose: <one sentence from the table>
# Choose: <from the table>
# Supplies: <from the table>
# Pieces: <from the table, omitted when empty>
# Produces: <only for release-build pieces>
# Call:
#   <job id>:
#     uses: ./.github/workflows/<name>.yml
#     <with:, secrets:, permissions:, needs:, if: as the table says>
#
# <the asset's own explanatory comments, moved here unchanged>
```

A field continues on lines indented by two spaces after `# `. In a YAML piece whose first line is `name:`, keep `name:` as the first line and the marker as the first comment line, as today.

**R3. A CI block becomes a workflow.** After the header:

```yaml
name: <Workflow name from the table>

on:
  workflow_call:
    inputs:
      ref:
        description: The commit to check out; empty takes the commit that triggered the run (D28).
        type: string
        required: false
        default: ''

permissions:
  contents: read

jobs:
<the block's job lines, unchanged; they are already indented by two spaces>
```

A job with `permissions:` of its own keeps them. The workflow-level `permissions:` is `contents: read` unless the table says otherwise.

**R4. A publish job becomes a workflow.** Replace every `needs.publish.outputs.<x>` with `inputs.<x>` and declare each `<x>` as a `required: true`, `type: string` input with a description. Delete the job-level `needs:` and `if: needs.publish.outputs.release_id != ''`; the caller carries both, and the `Call:` snippet shows them.

**R5. Version and history.** A new piece starts at v1. A carried-over piece takes the next version, because the header changes its bytes. In `generations.json`, copy the old entry of a carried-over file under its new key before running `make generations`, so the new key holds the old version and the new one (Decision L). Example: `"pieces/changelog/changelog.yml": {"4": "<the hash recorded under workflows/changelog.yml>"}`.

**R6. CHANGES.md.**

```markdown
# <name>

Upgrade notes, newest first. Each section says what a caller or
.github/repo-infra.json must change to take that version.

## v<N>

<text from the table>
```

**R7. After creating the files:** `make generations`, `make catalogue`, `make check`.

---

### Task 7: Carry over the release-flow and build pieces

**Files:**
- Create: `skills/repo-infra/assets/pieces/{changelog,release-pr,dependabot,workflow-lib,container,container-m4,man,man-lua}/...`
- Modify: `skills/repo-infra/assets/manifest.json`, `skills/repo-infra/assets/generations.json`, `skills/repo-infra/references/catalogue.md`
- Modify (source paths only): `tests/test_changelog_gate.py`, `tests/test_release_guard.py`, `tests/test_release_pr.py`, `tests/test_build_assets.py`, `tests/test_man_build.py`, `tests/test_container_m4.py`, `tests/test_container_selftest.py`

**Interfaces:**
- Produces pieces: `changelog` v5, `release-pr` v6, `dependabot` v2, `workflow-lib` v7, `container` v3, `container-m4` v2, `man` v4, `man-lua` v2.

| Piece | Copied from (`assets/`) | Target | Manifest extras | Purpose / Choose / Supplies / Pieces | CHANGES v-new |
|---|---|---|---|---|---|
| `changelog` | `workflows/changelog.yml` | `.github/workflows/changelog.yml` | `group: release, core: true` | The changelog-updated required check (D2, D6). / Always. / CHANGES.md with an Unreleased section; the no-changelog label. / workflow-lib | No caller change. The file gained the header block. |
| `release-pr` | `workflows/release-pr.yml` | `.github/workflows/release-pr.yml` | `group: release, core: true` | Create release PR: build, test and open the release pull request (D28). / Always. / ci.yml and release-build.yml callers that declare the inputs it passes; version_files in .github/repo-infra.json. / workflow-lib | No caller change. The file gained the header block. |
| `dependabot` | `workflows/dependabot.yml` | `.github/dependabot.yml` | `group: release, core: true` | Keep the pinned GitHub Actions current. / Always. / The no-changelog label. | No caller change. The file gained the header block. |
| `workflow-lib` | `workflows/lib/` (every file) | `.github/workflows/lib` | `group: release, core: true, kind: dir, header: release.js` | The JavaScript the release flow and the publish pieces run (D8). / Always. / Nothing. | No caller change. release.js gained the header block; every file carries the new marker. |
| `container` | `build/container.mk` | `build/container.mk` | `group: build` | Autotools as a container driver (D18). / The build needs a container (D16). / A Containerfile and the CONTAINER_DRIVER conditional in configure.ac. / container-m4 | No change for the repository. The file gained the header block. |
| `container-m4` | `m4/repo-infra-container.m4` | `m4/repo-infra-container.m4` | `group: build` | The container-driver mode switch for configure.ac (D18). / With container. / The macro call in configure.ac. | Same as above. |
| `man` | `build/man.mk` | `build/man.mk` | `group: build` | Build the man page from docs/manual.md (D23). / The project ships a man page. / docs/manual.md; MAN_NAME and MAN_SECTION in the Makefile. / man-lua | Same as above. |
| `man-lua` | `build/man-deflist.lua` | `build/man-deflist.lua` | `group: build` | The pandoc filter man.mk runs for term lists. / With man. / Nothing. | Same as above. |

Check the Supplies wording against the asset's own comments while moving them; the asset is the authority.

- [ ] **Step 1: Copy each file into its piece folder** (`cp`, not `git mv`: the old assets stay until Task 14).
- [ ] **Step 2: Add the header (R2) and bump the marker** to the version in the Interfaces line. For `workflow-lib`, bump the marker in every file of `pieces/workflow-lib/lib/` and put the header fields in `release.js` right after its marker line, before `'use strict';`. Reword any comment in a piece that says "assembled" or "generated by the assembler" to say what the file is now.
- [ ] **Step 3: Write each `CHANGES.md`** (R6) and the manifest entries (R1).
- [ ] **Step 4: Carry the history** (R5) for every file, then run `make generations`.
- [ ] **Step 5: Point the tests at the pieces.** In each test file listed above, change the path constant that names the old asset (for example `ASSETS / "workflows/changelog.yml"`, `ASSETS / "build/man.mk"`, `ASSETS / "workflows/lib/checks.js"`) to the piece path (`ASSETS / "pieces/changelog/changelog.yml"`, `ASSETS / "pieces/man/man.mk"`, `ASSETS / "pieces/workflow-lib/lib/checks.js"`). Leave tests that call `detect` or `render_all` untouched; Task 14 deletes them.
- [ ] **Step 6: Run** `make catalogue && make check`. Expected: PASS. `tests/test_pieces.py` now runs on eight pieces; `changelog` and `release-pr` get the timeout and action-pin checks, not the reusable-workflow ones (they are not in `CALLED`).
- [ ] **Step 7: Run the container test** once, since `container.mk` moved: `systemd-run --user --scope -p MemoryMax=4G -- make test-container`. Expected: PASS (it builds a real container and takes minutes).
- [ ] **Step 8: Commit**

```bash
git add skills/repo-infra/assets/pieces skills/repo-infra/assets/manifest.json \
  skills/repo-infra/assets/generations.json skills/repo-infra/references/catalogue.md tests
git commit -m "Carry the release flow and build files over as pieces (D30)

changelog, release-pr, dependabot, the workflow library and the four build
files become pieces with a header block. The header changes their bytes, so
each takes the next version; generations.json keeps the old version's hash
under the new path, so a repository on the old file reads outdated.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: CI pieces without tests of their own

**Files:**
- Create: `skills/repo-infra/assets/pieces/ri-ci-{lib,claude-plugin,python,go,node-pnpm,node-bun,perl-autotools,perl-mkpl,checkmk-plugin}/`
- Modify: `manifest.json`, `generations.json`, `references/catalogue.md`

Each from `assets/ci/<block>.yml` by R3, group `ci`, version 1. Call snippet: the job id from the table, `uses:` the piece, `with: ref: ${{ inputs.ref }}`.

| Piece | Block | Workflow name | Call job id | Choose | Supplies | Pieces |
|---|---|---|---|---|---|---|
| `ri-ci-lib` | `ci-lib` | Workflow library | `lib` | Always: it runs the tests of the workflow library every repository carries. | Nothing. | workflow-lib |
| `ri-ci-claude-plugin` | `ci-claude-plugin` | Claude plugin | `plugin` | The repository has .claude-plugin/plugin.json. | .claude-plugin/plugin.json. | |
| `ri-ci-python` | `ci-python` | Python | `python` | The repository has pyproject.toml. | pyproject.toml; requirements-dev.txt for the test dependencies, when it exists. | |
| `ri-ci-go` | `ci-go` | Go | `go` | The repository has go.mod. | go.mod. | |
| `ri-ci-node-pnpm` | `ci-node-pnpm` | Node (pnpm) | `node` | package.json and pnpm-lock.yaml, and no other lockfile. | The package.json scripts check, test and build. | |
| `ri-ci-node-bun` | `ci-node-bun` | Node (bun) | `node` | package.json and bun.lock, and no other lockfile. | A tsconfig for `bunx tsc --noEmit`, and tests for `bun test`. | |
| `ri-ci-perl-autotools` | `ci-perl-autotools` | Perl (autotools) | `perl` | configure.ac and cpanfile. | ./bootstrap, configure, and the targets all and test. | |
| `ri-ci-perl-mkpl` | `ci-perl-mkpl` | Perl (Makefile.PL) | `perl` | Makefile.PL and no configure.ac. | Makefile.PL and the target test. | |
| `ri-ci-checkmk-plugin` | `ci-checkmk-plugin` | Checkmk plugin | `checkmk` | The repository has .mkp-builder.ini. | Plugin code under local/, tests for pytest, .mkp-builder.ini. | |

CHANGES v1 text for each: "First version as a piece. It was the `<block>` block of the assembled ci.yml. Call it from ci.yml with the snippet in the catalogue, and add its job to the needs: list of ci-passed."

Verify the Choose and Supplies lines against the block's own steps while converting; the block is the authority.

- [ ] **Step 1: Create the nine pieces** (R1, R2, R3, R6).
- [ ] **Step 2: Run** `make generations && make catalogue && python3 -m pytest -q tests/test_pieces.py tests/test_workflow.py`. Expected: PASS for every new piece.
- [ ] **Step 3: Run** `make check`. Expected: PASS.
- [ ] **Step 4: Commit** with subject `Ship nine CI blocks as reusable workflow pieces (D30)` and a body naming the nine and saying the block jobs are unchanged.

---

### Task 9: CI pieces whose steps are tested

**Files:**
- Create: `skills/repo-infra/assets/pieces/ri-ci-{rust,rust-musl,man,github-action,repo-infra-selftest}/`
- Modify: `manifest.json`, `generations.json`, `references/catalogue.md`
- Modify: `tests/test_ci_rust.py`, `tests/test_ci_rust_musl.py`, `tests/test_ci_man.py`, `tests/test_github_action.py`, `tests/test_blocks.py`

| Piece | Block | Workflow name | Call job id | Choose | Supplies | Pieces |
|---|---|---|---|---|---|---|
| `ri-ci-rust` | `ci-rust` | Rust | `rust` | The repository has Cargo.toml. | Cargo.toml and Cargo.lock; the optional "rust" key in .github/repo-infra.json names the crates to lint and to test (D24). | workflow-lib |
| `ri-ci-rust-musl` | `ci-rust-musl` | Rust static binary | `rust-musl` | The project ships a static Linux binary; call it beside ri-ci-rust. | Cargo.toml with a binary target. | |
| `ri-ci-man` | `ci-man` | Manual | `man` | The project ships a man page built from docs/manual.md (D23). | docs/manual.md and a `man` target from build/man.mk. | man, man-lua |
| `ri-ci-github-action` | `ci-github-action` | GitHub Action | `action` | The repository has action.yml. | action.yml, and .github/workflows/action-test.yml: the project's own test, called with `ref` (D20). | |
| `ri-ci-repo-infra-selftest` | `ci-repo-infra-selftest` | repo-infra self-test | `selftest` | Only in repo-infra itself. | The pytest suite with the container and pandoc markers. | |

`ri-ci-rust` keeps its three jobs; `needs.rust-plan.outputs` stays inside the piece. `ri-ci-github-action` keeps its `action-test` job calling `./.github/workflows/action-test.yml` with `ref` and `secrets: inherit`; check validates that nested call in every repository that installs the piece.

- [ ] **Step 1: Create the five pieces** (R1, R2, R3, R6; CHANGES v1 text as in Task 8).
- [ ] **Step 2: Point the step-running tests at the pieces.** Each of these helpers reads a job from an assembled file today; make it read the piece instead (`yaml.safe_load` of `ASSETS / "pieces/<name>/<name>.yml"`, then `["jobs"][<job>]`):
  - `tests/test_ci_rust.py`: the helper that calls `assemble_ci(ASSETS, ["ci-rust"])` returns the jobs of `ri-ci-rust.yml`. The test that the plan's outputs feed the matrix stays as is: the outputs never cross a call boundary.
  - `tests/test_ci_rust_musl.py`: `verify_script()` reads job `rust-musl` of `ri-ci-rust-musl.yml`.
  - `tests/test_ci_man.py`: `check_script()` reads job `man` of `ri-ci-man.yml`.
  - `tests/test_github_action.py`: `validator_script()` reads job `action-manifest` of `ri-ci-github-action.yml`.
  - `tests/test_blocks.py`: the invariants on block text (the autotools apt line identical in `ci-perl-autotools`, `ci-repo-infra-selftest` and `release-source-tarball`; the selftest runs `-m container`; every pytest job mentions requirements-dev.txt; the man toolchain line appears once in `ci-man` and in the selftest) read the pieces. `release-source-tarball` arrives in Task 11; until then that one comparison keeps reading the old block.
- [ ] **Step 3: Run** `make generations && make catalogue && make check`. Expected: PASS. The detection and assembly tests in these files still pass against the old code; Task 14 deletes them.
- [ ] **Step 4: Commit** with subject `Ship the Rust, musl, man, action and self-test CI pieces (D30)`; the body says the tests that run their steps now read the pieces.

---

### Task 10: The release-flow jobs become pieces, ci-passed becomes a pattern

**Files:**
- Create: `skills/repo-infra/assets/pieces/{ri-release-pr-current,ri-publish-tag,ri-publish-finalize}/`
- Create: `skills/repo-infra/assets/callers/ci-passed.yml`
- Modify: `manifest.json`, `generations.json`, `references/catalogue.md`
- Modify: `tests/test_release_mode.py`, `tests/test_publish_build.py`, `tests/test_publish.py`

**Interfaces:**
- Produces: `ri-release-pr-current` v1 (input `ref`; job permissions `contents: read`, `pull-requests: read`, `checks: write`), `ri-publish-tag` v1 (no inputs; outputs `version`, `tag`, `release_id`, `head`; workflow permissions `contents: write`, `pull-requests: read`), `ri-publish-finalize` v1 (inputs `release_id`, `tag`, `head` required; `expected` optional, default `'[]'`; job permissions as today: `contents: write`, `actions: write`). All three `core: true`.

- [ ] **Step 1: Write the ci-passed pattern.** `assets/callers/ci-passed.yml` holds `jobs:` and the `ci-passed` job copied verbatim from `assets/ci/ci-aggregator.yml`, with `needs: []`. Replace the comment sentence "The needs list is generated by the assembler from the blocks that went into this file." with "Its needs: list names every other job of ci.yml; check verifies it (D30). Copy the rest word for word." Start the file with:

```yaml
# The ci-passed job of every ci.yml (D2, D30). Copy it under `jobs:` word for
# word and fill in `needs:` with every other job of the file. check compares
# it with this text, so a change here reaches every repository as a finding.
```

- [ ] **Step 2: Create `ri-release-pr-current`** from the `release-pr-current` job of `ci-aggregator.yml` by R3, group `ci`. The job keeps its `if: github.event_name == 'push'` (inside a called workflow, `github` is the caller's context). Purpose: "Mark open release pull requests stale when main moves (D28)." Choose: "Always; ci.yml calls it." Supplies: "Nothing." Pieces: `workflow-lib`. Call snippet:

```
#   release-pr-current:
#     uses: ./.github/workflows/ri-release-pr-current.yml
#     permissions:
#       contents: read
#       pull-requests: read
#       checks: write
#     with:
#       ref: ${{ inputs.ref }}
```

- [ ] **Step 3: Create `ri-publish-tag`** from the `publish` job of `assets/publish/publish-frame.yml`, group `publish`. Its `on:` is `workflow_call` with `outputs:` mapping each of `version`, `tag`, `release_id`, `head` to `${{ jobs.publish.outputs.<x> }}`, each with a description. Workflow permissions `contents: write`, `pull-requests: read`. Purpose: "Tag the merged release and create its draft release (D28)." Choose: "Always; release-publish.yml calls it." Supplies: "version_files and moving_major_tag in .github/repo-infra.json." Pieces: `workflow-lib`. Call snippet:

```
#   publish:
#     uses: ./.github/workflows/ri-publish-tag.yml
#     permissions:
#       contents: write
#       pull-requests: read
```

- [ ] **Step 4: Create `ri-publish-finalize`** from `assets/publish/publish-finalize.yml` by R4, group `publish`. Replace `const expected = [];` and the comment above it with:

```javascript
            // The files the publish jobs of release-publish.yml attach, from
            // the caller's `expected` input; release_assets below are the
            // files the release build made.
            let expected;
            try {
              expected = JSON.parse(process.env.EXPECTED || '[]');
            } catch (error) {
              core.setFailed(`The input expected is not JSON: ${error.message}`);
              return;
            }
            if (!Array.isArray(expected)
                || !expected.every((p) => typeof p === 'string' && /^[A-Za-z0-9._+*~-]+$/.test(p))) {
              core.setFailed('The input expected must be a JSON list of file name patterns.');
              return;
            }
```

and add `env: EXPECTED: ${{ inputs.expected }}` to that step. Reword the failure message that points at "finalize's needs: list" and "publish_local" to: "Either a publish job did not run (compare the needs: list of finalize in release-publish.yml with its jobs) or it attached something under another name (see the expected input of finalize and release_assets in .github/repo-infra.json)." Inputs:

```yaml
    inputs:
      release_id:
        description: The draft release to publish, from ri-publish-tag.
        type: string
        required: true
      tag:
        description: The release tag, from ri-publish-tag.
        type: string
        required: true
      head:
        description: The commit the release was built from, from ri-publish-tag.
        type: string
        required: true
      expected:
        description: JSON list of file name patterns the publish jobs attach, such as '["*.crate"]'.
        type: string
        required: false
        default: '[]'
```

Purpose: "Check the release carries every file, then publish it." Choose: "Always; release-publish.yml calls it last." Supplies: "release_assets in .github/repo-infra.json." Pieces: `workflow-lib`. Call snippet:

```
#   finalize:
#     needs: [publish]
#     if: needs.publish.outputs.release_id != ''
#     uses: ./.github/workflows/ri-publish-finalize.yml
#     permissions:
#       contents: write
#       actions: write
#     with:
#       release_id: ${{ needs.publish.outputs.release_id }}
#       tag: ${{ needs.publish.outputs.tag }}
#       head: ${{ needs.publish.outputs.head }}
```

CHANGES v1 for all three: "First version as a piece. It was the `<job>` job of the assembled <file>. Call it as the catalogue shows."

- [ ] **Step 5: Point the tests at the new files.**
  - `tests/test_release_mode.py`: `ci_passed()` reads job `ci-passed` of `assets/callers/ci-passed.yml`; `release_pr_current()` reads job `release-pr-current` of the piece. The parametrization over `ci_blocks` (every block checks out `ref`) becomes a parametrization over the `ci` group of `load_pieces()`; it duplicates `test_a_ci_or_build_piece_keeps_the_ref_contract` and may be deleted instead.
  - `tests/test_publish_build.py`: `publish_script()` reads step `id: publish` of job `publish` of `ri-publish-tag.yml`.
  - `tests/test_publish.py`: `_run_finalize` and `_run_parked` read job `finalize` of `ri-publish-finalize.yml`. Where the harness substitutes `${{ needs.publish.outputs.<x> }}` into the script, substitute `${{ inputs.<x> }}`; where a test relied on the assembler's `expected` list, set `EXPECTED` in the environment the harness passes to node. Add one test: `EXPECTED='{"a": 1}'` fails with "must be a JSON list".
- [ ] **Step 6: Run** `make generations && make catalogue && make check`. Expected: PASS.
- [ ] **Step 7: Commit** with subject `Ship the publish, finalize and stale-marking jobs as pieces (D30)`; the body explains Decision A and B in two sentences each.

---

### Task 11: Release-build and publish add-on pieces

**Files:**
- Create: `skills/repo-infra/assets/pieces/{ri-release-source-tarball,ri-publish-crates-io,ri-publish-gitea}/`
- Modify: `manifest.json`, `generations.json`, `references/catalogue.md`
- Modify: `tests/test_release_build_assembly.py`, `tests/test_publish.py`, `tests/test_publish_gitea.py`, `tests/test_blocks.py`

| Piece | From | Group | Inputs | Secrets | Purpose / Choose / Supplies / Produces | Call snippet |
|---|---|---|---|---|---|---|
| `ri-release-source-tarball` | `release-build/release-source-tarball.yml` by R3, with inputs `version` and `ref` (both required, as `release-build.yml` passes them) | `release-build` | `version`, `ref` | | Build the `make dist` tarball before the merge (D28). / The project is autotools and ships a source tarball. / ./bootstrap, configure and `make dist`. / The artifact release-asset-source-tarball (`*.tar.gz`); list `*.tar.gz` in release_assets. | job `tarball`, `with: version: ${{ inputs.version }}`, `ref: ${{ inputs.ref }}` |
| `ri-publish-crates-io` | `publish/publish-crates-io.yml` by R4 | `publish` | `head` | | Publish the crate to crates.io with trusted publishing. / The crate is published on crates.io. / The trusted publisher configured on crates.io for this workflow. | job `crates`, `needs: [publish]`, `if: needs.publish.outputs.release_id != ''`, `permissions: contents: read, id-token: write`, `with: head: ${{ needs.publish.outputs.head }}` |
| `ri-publish-gitea` | `publish/publish-gitea-packages.yml` by R4 | `publish` | `release_id`, `head` | `GITEA_PACKAGE_TOKEN` (`required: false`: the job's own check names it when it is empty) | Upload the release's .deb and .rpm files to a Gitea package registry. / The project ships packages to Gitea. / gitea_packages (url, owner) in .github/repo-infra.json, the secret GITEA_PACKAGE_TOKEN and the variable GITEA_PACKAGE_USER. / Pieces: workflow-lib | job `gitea`, `needs: [publish]`, `if: needs.publish.outputs.release_id != ''`, `permissions: contents: write`, `with: release_id, head` from `needs.publish.outputs`, `secrets: inherit` |

Take the permissions in the snippets from the job's own `permissions:` block; the table copies what the blocks declare today.

- [ ] **Step 1: Create the three pieces** (R1, R2, R3/R4, R6; CHANGES v1 text as in Task 10).
- [ ] **Step 2: Point the tests at the pieces.**
  - `tests/test_release_build_assembly.py`: `_locate()` and the tarball tests read job `release-source-tarball` of the piece. Rename the file `tests/test_release_source_tarball.py` (`git mv`) and keep only those tests; the frame, seam and assembly tests go now, since no new code depends on them and Task 14 removes what they test.
  - `tests/test_publish.py`: `_run_crates_publish` reads job `publish-crates-io` of `ri-publish-crates-io.yml`.
  - `tests/test_publish_gitea.py`: every `assemble_publish(...)["jobs"][BLOCK]` reads job `publish-gitea-packages` of `ri-publish-gitea.yml`. The test of the job-level guard becomes a test that the `Call:` snippet carries `if: needs.publish.outputs.release_id != ''`.
  - `tests/test_blocks.py`: the apt line comparison reads `ri-release-source-tarball`.
- [ ] **Step 3: Run** `make generations && make catalogue && make check`. Expected: PASS.
- [ ] **Step 4: Commit** with subject `Ship the tarball build and the crates.io and Gitea publish as pieces (D30)`.

---

### Task 12: apply on pieces, and the new check report

**Files:**
- Modify: `skills/repo-infra/scripts/repo_infra/apply.py`
- Rewrite: `skills/repo-infra/scripts/repo_infra/cli.py`
- Modify: `skills/repo-infra/scripts/repo_infra/report.py` (render functions)
- Rewrite: `tests/test_report.py`, `tests/test_cli.py`
- Create: `tests/test_apply_pieces.py`

**Interfaces:**
- Consumes: `check.piece_state/PieceState/missing_dependencies/config_items/run`, `callers.read_workflows/validate`, `pieces.load_pieces/load_published/upgrade_notes/ASSETS`, `report.Item/ATTENTION`.
- Produces:
  - `apply.install_piece(repo_root, piece, state, history, merged=None) -> list[str]` (paths written or removed).
  - `apply.commit_piece(repo_root, name, version, paths, merged=False) -> str` (subject `Install <name> v<N> from the repo-infra standard`, or `Merge <name> v<N> from the repo-infra standard with local edits`).
  - `apply.latest_release(text) -> str | None`, `apply.release_in_progress(repo_root, facts) -> str | None` (moved from `migrate.py`, returning the detail text).
  - `report.render_text(repo, items) -> str`, `report.render_json(repo, items) -> str`.
  - `cli.main(argv)`, `cli.check(args)`, `cli.apply_command(args)`, `cli.read_facts(repo)`, `cli.CONFORMING_FACTS`, `cli.ASSETS` (module global read at call time, so tests can monkeypatch it).

- [ ] **Step 1: Write the failing report tests**

```python
# tests/test_report.py
import json

from repo_infra.report import Item, render_json, render_text

ITEMS = [Item("pieces", "ri-ci-rust", "outdated", "v1 installed, v2 available"),
         Item("pieces", "changelog", "current", "v5"),
         Item("callers", "ci.yml", "problem", "job a calls ri-zz.yml, which does not exist"),
         Item("administration", "default-branch", "ok", "main")]


def test_text_groups_rows_by_section_and_counts_what_needs_attention():
    text = render_text("o/r", ITEMS)
    assert text.startswith("repo-infra check: o/r\n\npieces\n  ri-ci-rust")
    assert "\ncallers\n  ci.yml" in text
    assert "\nadministration\n  default-branch" in text
    assert "config" not in text
    assert text.endswith("2 items need attention.\n")


def test_text_says_so_when_nothing_needs_attention():
    assert render_text("o/r", ITEMS[1:2]).endswith(
        "Up to date with the standard; nothing to do.\n")


def test_json_carries_the_section():
    data = json.loads(render_json("o/r", ITEMS))
    assert data["repo"] == "o/r"
    assert data["items"][2] == {"section": "callers", "name": "ci.yml", "state": "problem",
                                "detail": "job a calls ri-zz.yml, which does not exist"}
```

- [ ] **Step 2: Rewrite the render functions in `report.py`**

Keep `NAME_WIDTH`, `STATE_WIDTH`, `_compute_name_width` and `_row`; drop the `from .state import` line and the old `render_text`/`render_json`.

```python
def render_text(repo, items):
    lines = [f"repo-infra check: {repo}", ""]
    name_width = _compute_name_width(items)
    indent = " " * (2 + name_width + STATE_WIDTH)
    for section in SECTIONS:
        rows = [item for item in items if item.section == section]
        if not rows:
            continue
        lines.append(section)
        for item in rows:
            lines.extend(_row(item, name_width, indent))
        lines.append("")
    count = sum(1 for item in items if item.state in ATTENTION)
    if count:
        noun, verb = ("item", "needs") if count == 1 else ("items", "need")
        lines.append(f"{count} {noun} {verb} attention.")
    else:
        lines.append("Up to date with the standard; nothing to do.")
    return "\n".join(lines) + "\n"


def render_json(repo, items):
    return json.dumps({"repo": repo, "items": [item._asdict() for item in items]}, indent=2)
```

Run: `python3 -m pytest -q tests/test_report.py`. Expected: PASS. The old `cli.py` still calls the old signature, so `make check` is red until Step 6; do not commit in between.

- [ ] **Step 3: Write the failing apply tests**

```python
# tests/test_apply_pieces.py
import subprocess

import pytest
from piecekit import install, lib_file, make_assets, workflow_piece

from repo_infra import apply, check, cli
from repo_infra.pieces import load_pieces, load_published

OLD = workflow_piece("ri-x", 1, body="old")
NEW_INPUT = ("      target:\n        description: The make target.\n"
             "        type: string\n        required: true\n")
NEW = workflow_piece("ri-x", 2, body="new", inputs=NEW_INPUT)
LIB1 = {"a.js": lib_file("lib-x", 1, "a1"), "gone.js": lib_file("lib-x", 1, "g1")}
LIB2 = {"a.js": lib_file("lib-x", 2, "a2")}


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True,
                          text=True).stdout


@pytest.fixture
def store(tmp_path):
    history = [("ri-x", None, OLD)] + [("lib-x", f, t) for f, t in LIB1.items()]
    return make_assets(tmp_path / "assets", {"ri-x": NEW, "lib-x": LIB2}, history,
                       core=("lib-x",))


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    install(root, ".github/workflows/ri-x.yml", OLD)
    for f, t in LIB1.items():
        install(root, f".github/workflows/lib-x/{f}", t)
    install(root, ".github/workflows/ci.yml",
            "on:\n  push:\npermissions:\n  contents: read\njobs:\n  x:\n"
            "    uses: ./.github/workflows/ri-x.yml\n")
    git(root, "add", ".")
    git(root, "commit", "-qm", "start")
    return root


def run_apply(monkeypatch, store, repo, *extra):
    monkeypatch.setattr(cli, "ASSETS", store)
    monkeypatch.setattr(cli, "read_facts", lambda repo_name: cli.CONFORMING_FACTS)
    return cli.main(["apply", "--root", str(repo), "--repo", "o/r", *extra])


def test_apply_replaces_outdated_pieces_one_commit_each(monkeypatch, capsys, store, repo):
    assert run_apply(monkeypatch, store, repo) == 0
    log = git(repo, "log", "--format=%s").splitlines()
    assert log[:2] == ["Install ri-x v2 from the repo-infra standard",
                       "Install lib-x v2 from the repo-infra standard"]
    assert (repo / ".github/workflows/ri-x.yml").read_text(encoding="utf-8") == NEW
    assert git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip() == "repo-infra/apply"


def test_apply_removes_a_file_the_new_version_no_longer_ships(monkeypatch, store, repo):
    run_apply(monkeypatch, store, repo)
    assert not (repo / ".github/workflows/lib-x/gone.js").exists()


def test_apply_prints_the_notes_and_the_new_caller_finding(monkeypatch, capsys, store, repo):
    run_apply(monkeypatch, store, repo)
    out = capsys.readouterr().out
    assert "ri-x v2\nNotes for ri-x v2." in out
    assert "ci.yml: job x calls ri-x.yml without its required input target" in out
    assert "then run check until it exits 0" in out


def test_apply_installs_a_piece_that_is_not_there(monkeypatch, store, repo):
    (repo / ".github/workflows/ri-x.yml").unlink()
    git(repo, "commit", "-qam", "drop")
    run_apply(monkeypatch, store, repo, "--item", "ri-x")
    assert git(repo, "log", "-1", "--format=%s").strip() == (
        "Install ri-x v2 from the repo-infra standard")


def test_an_edited_piece_stops_with_the_merge_files(monkeypatch, store, repo):
    install(repo, ".github/workflows/ri-x.yml", OLD + "# mine\n")
    git(repo, "commit", "-qam", "edit")
    with pytest.raises(apply.NeedsMerge) as stopped:
        run_apply(monkeypatch, store, repo, "--item", "ri-x")
    assert stopped.value.new.read_text(encoding="utf-8") == NEW
    merged = repo.parent / "merged.yml"
    merged.write_text(NEW, encoding="utf-8")
    run_apply(monkeypatch, store, repo, "--item", "ri-x", "--from", str(merged))
    assert git(repo, "log", "-1", "--format=%s").strip() == (
        "Install ri-x v2 from the repo-infra standard")


def test_a_hand_back_with_local_edits_is_committed_as_a_merge(monkeypatch, store, repo):
    install(repo, ".github/workflows/ri-x.yml", OLD + "# mine\n")
    git(repo, "commit", "-qam", "edit")
    with pytest.raises(apply.NeedsMerge):
        run_apply(monkeypatch, store, repo, "--item", "ri-x")
    merged = repo.parent / "merged.yml"
    merged.write_text(NEW + "# mine\n", encoding="utf-8")
    run_apply(monkeypatch, store, repo, "--item", "ri-x", "--from", str(merged))
    assert git(repo, "log", "-1", "--format=%s").strip() == (
        "Merge ri-x v2 from the repo-infra standard with local edits")


def test_a_release_in_progress_stops_apply(monkeypatch, store, repo):
    monkeypatch.setattr(cli, "release_in_progress", lambda root, facts: "pull request #3 is open")
    with pytest.raises(apply.ApplyError, match="release-in-progress: pull request #3"):
        run_apply(monkeypatch, store, repo)


def test_an_unknown_item_is_refused(monkeypatch, store, repo):
    with pytest.raises(apply.ApplyError, match="ri-zz: not a piece"):
        run_apply(monkeypatch, store, repo, "--item", "ri-zz")


def test_state_after_apply_is_current(monkeypatch, store, repo):
    run_apply(monkeypatch, store, repo)
    pieces, published = load_pieces(store), load_published(store)
    assert {n: check.piece_state(repo, p, published[n]).state for n, p in pieces.items()} == {
        "ri-x": "current", "lib-x": "current"}
```

Then move every test of `apply_admin_item` that lives in `tests/test_apply_files.py` or `tests/test_cli.py` into `tests/test_apply_admin.py` if it is not already there, and delete `tests/test_cli.py`; replace it with:

```python
# tests/test_cli.py
import pytest
from piecekit import install, make_assets, workflow_piece

from repo_infra import cli


def test_help_lists_check_and_apply(capsys):
    with pytest.raises(SystemExit):
        cli.main(["--help"])
    out = capsys.readouterr().out
    assert "check" in out and "apply" in out


def test_check_exits_1_when_something_needs_attention(monkeypatch, tmp_path, capsys):
    store = make_assets(tmp_path / "assets", {"ri-x": workflow_piece("ri-x", 1)})
    monkeypatch.setattr(cli, "ASSETS", store)
    monkeypatch.setattr(cli, "read_facts", lambda repo: cli.CONFORMING_FACTS)
    install(tmp_path / "repo", ".github/workflows/ri-x.yml", workflow_piece("ri-x", 1) + "#\n")
    assert cli.main(["check", "--root", str(tmp_path / "repo"), "--repo", "o/r"]) == 1
    assert "edited" in capsys.readouterr().out


def test_check_json(monkeypatch, tmp_path, capsys):
    store = make_assets(tmp_path / "assets", {"ri-x": workflow_piece("ri-x", 1)})
    monkeypatch.setattr(cli, "ASSETS", store)
    monkeypatch.setattr(cli, "read_facts", lambda repo: cli.CONFORMING_FACTS)
    cli.main(["check", "--json", "--root", str(tmp_path), "--repo", "o/r"])
    assert '"section": "callers"' in capsys.readouterr().out
```

- [ ] **Step 4: Change `apply.py`**

Delete `targets_for`, `apply_file_item` and `_apply_dir_asset`. Change the import line to `from .markers import parse_markers` (the stamp functions are no longer used here) and keep `from .remote import protects_default_branch`. Replace the module docstring's second paragraph with: "There is exactly one thing this module refuses to do. A piece whose bytes match no published version (D30: `edited`) carries local edits, and merging a new version into those is judgement, not mechanism. It writes the new version, the current file and the file's git log out and raises NeedsMerge. The model merges; the script keeps the irreversible half." In the `NeedsMerge` message, replace "is not what apply last wrote (no stamp, or edited since)" with "matches no published version of the piece". Then add:

```python
def install_piece(repo_root, piece, state, history, merged=None):
    """Write `piece` at its current version; return the paths written or removed.

    A file an older version shipped and this one does not is removed when its
    bytes are a published version; an edited one stays for the human."""
    if merged is not None:
        return [_hand_back(repo_root, piece, merged)]
    root = pathlib.Path(repo_root)
    if state.state == "edited":
        path = state.edited[0]
        _prepare_merge(repo_root, piece.name, path, piece.files.get(path, ""),
                       _read_raw(root / path))
    written = [write_asset(repo_root, path, text) for path, text in sorted(piece.files.items())]
    for path, versions in sorted(history.items()):
        target = root / path
        if path not in piece.files and target.is_file():
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            if digest in versions.values():
                target.unlink()
                written.append(path)
    return written


def _hand_back(repo_root, piece, merged):
    """The merged file from --from, written where the refusal recorded."""
    scratch = _scratch_dir(repo_root)
    recorded = scratch / f"{piece.name}.path"
    snapshot = scratch / f"{piece.name}.current"
    if not recorded.is_file() or not snapshot.is_file():
        raise ApplyError(f"{piece.name}: no merge is in progress; run "
                         f"`apply --item {piece.name}` first to prepare one")
    path = recorded.read_text(encoding="utf-8").strip()
    if path not in piece.files:
        raise ApplyError(f"{piece.name}: the prepared merge names {path}, which this piece "
                         "no longer ships; redo the merge")
    target = pathlib.Path(repo_root) / path
    current = _read_raw(target) if target.is_file() else None
    if current != snapshot.read_text(encoding="utf-8"):
        raise ApplyError(f"{path}: changed since the merge was prepared; redo the merge "
                         "against the current file")
    text = pathlib.Path(merged).read_text(encoding="utf-8")
    got = next((m.version for m in parse_markers(text) if m.asset == piece.name), None)
    if got != piece.version:
        raise ApplyError(f"{piece.name}: the merged file says v{got}, the piece is "
                         f"v{piece.version}")
    write_asset(repo_root, path, text)
    for suffix in ("new", "current", "path", "log"):
        (scratch / f"{piece.name}.{suffix}").unlink(missing_ok=True)
    return path


def commit_piece(repo_root, name, version, paths, merged=False):
    """One commit per piece, so any single piece can be dropped at review. A
    merge with local edits says so: the next NeedsMerge hands the model the
    file's log, and an Install commit there means "no local edits"."""
    subject = (f"Merge {name} v{version} from the repo-infra standard with local edits"
               if merged else f"Install {name} v{version} from the repo-infra standard")
    git(repo_root, "add", "--all", "--", *paths)
    git(repo_root, "commit", "-m", f"{subject}\n\n{TRAILER}")
    return git(repo_root, "rev-parse", "HEAD").strip()
```

Add `import hashlib` and `import re`. Move `latest_release` and `release_in_progress` from `migrate.py` into `apply.py` with `_RELEASE = re.compile(r"^## (\d+\.\d+\.\d+) - \d{4}-\d{2}-\d{2}\s*$")`; `release_in_progress` returns the detail string instead of an `Item`, and its last words change from "then migrate" to "then run apply". Leave `commit_item`, `write_config`, `config_text`, `_compact`, `CONFIG` and `WIDTH` in place: `migrate.py` still imports them, and Task 14 deletes them with it.

- [ ] **Step 5: Rewrite `cli.py`**

```python
"""Command line entry point: `python3 -m repo_infra check|apply`."""

import argparse
import pathlib

from . import callers, report
from . import check as checking
from .apply import (
    ApplyError,
    apply_admin_item,
    changed,
    commit_piece,
    ensure_branch,
    install_piece,
    release_in_progress,
)
from .pieces import ASSETS, load_pieces, load_published, upgrade_notes
from .remote import Facts, Gh

# Administration items write repository settings through `remote.Gh`, and
# each is outward-facing, so apply runs one only when it is named (D30).
ADMIN = {"default-branch", "branch-protection", "required-checks",
         "no-changelog-label", "actions-open-pr"}

# Used by the tests to run without a network. Never used at runtime.
CONFORMING_FACTS = Facts(default_branch="main", protected=True,
                         required_contexts={"ci-passed", "changelog-updated"},
                         labels={"no-changelog"}, workflow_permissions="write",
                         can_approve_pr=True, strict=True)


def read_facts(repo):
    return Gh().facts(repo)


def check(args):
    repo = args.repo or Gh().current_repo()
    items = checking.run(args.root, read_facts(repo), ASSETS)
    renderer = report.render_json if args.json else report.render_text
    print(renderer(repo, items))
    return 1 if any(item.state in report.ATTENTION for item in items) else 0


def _pending(pieces, states):
    """The pieces a bare apply installs: outdated ones, absent core pieces,
    and pieces an installed piece needs."""
    names = [name for name, state in sorted(states.items())
             if state.state in ("outdated", "edited")
             or (state.state == "absent" and pieces[name].core)]
    return names + [dep for dep, _ in checking.missing_dependencies(pieces, states)
                    if dep not in names]


def apply_command(args):
    repo = args.repo or Gh().current_repo()
    facts = read_facts(repo)
    if args.item in ADMIN:
        print(apply_admin_item(Gh(), repo, args.item, facts, ASSETS, args.root))
        return 0
    if args.from_file and not args.item:
        raise ApplyError("--from needs --item: name the piece the merged file is for")
    pieces, published = load_pieces(ASSETS), load_published(ASSETS)
    if args.item is not None and args.item not in pieces:
        raise ApplyError(f"{args.item}: not a piece and not an administration item")
    states = {name: checking.piece_state(args.root, piece, published.get(name, {}))
              for name, piece in pieces.items()}
    names = [args.item] if args.item else _pending(pieces, states)
    if names:
        blocker = release_in_progress(args.root, facts)
        if blocker:
            raise ApplyError(f"release-in-progress: {blocker}")
        ensure_branch(args.root)
    notes = []
    for name in names:
        piece, state = pieces[name], states[name]
        written = changed(args.root, install_piece(args.root, piece, state,
                                                   published.get(name, {}),
                                                   merged=args.from_file))
        if not written:
            print(f"{name}: already v{piece.version}")
            continue
        merged = args.from_file is not None and any(
            (pathlib.Path(args.root) / path).is_file()
            and (pathlib.Path(args.root) / path).read_text(encoding="utf-8")
            != piece.files.get(path) for path in written)
        commit_piece(args.root, name, piece.version, written, merged=merged)
        print(f"installed {name} v{piece.version}")
        if state.installed and state.state == "outdated":
            notes += [(name, v, text) for v, text in
                      upgrade_notes(name, state.installed, piece.version, ASSETS)]
    for name, version, text in notes:
        print(f"\n{name} v{version}\n{text}")
    docs = callers.read_workflows(args.root)
    findings = [item for item in callers.validate(docs, pieces, ASSETS)
                + checking.config_items(args.root, docs) if item.state in report.ATTENTION]
    if findings:
        print("\nThe callers and the config need these changes:")
        for item in findings:
            print(f"  {item.name}: {item.detail}")
    print("\nChange the callers and the config from the notes and findings above, "
          "then run check until it exits 0.")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="repo-infra")
    sub = parser.add_subparsers(dest="command", required=True)

    checker = sub.add_parser("check", help="report the state of the pieces, callers and "
                                           "settings; never writes")
    checker.add_argument("--repo", help="owner/name; defaults to the current checkout")
    checker.add_argument("--root", default=".", help="repository root")
    checker.add_argument("--json", action="store_true")
    checker.set_defaults(run=check)

    applier = sub.add_parser("apply", help="install or replace pieces on a branch; "
                                           "with --item, one piece or one setting")
    applier.add_argument("--repo")
    applier.add_argument("--root", default=".")
    applier.add_argument("--item", help="one piece or administration item")
    applier.add_argument("--from", dest="from_file", help="take the merged file from here")
    applier.set_defaults(run=apply_command)

    args = parser.parse_args(argv)
    return args.run(args)
```

`ASSETS` is imported into `cli`'s namespace and read at call time, which is what the tests monkeypatch. An `edited` piece is in `_pending` so a bare `apply` stops on it with the merge files, as the spec says.

- [ ] **Step 6: Run the tests**

Run: `python3 -m pytest -q tests/test_report.py tests/test_cli.py tests/test_apply_pieces.py tests/test_apply_admin.py`
Expected: PASS.

Run: `make check`
Expected: failures only in tests that import the old `cli._prepare`, `cli.migrate` or the old report signature (`test_teach.py`, `test_ci_local.py`, `test_migrate.py`, `test_self_render.py`, and the files listed in Task 14). Delete `tests/test_teach.py` (the refusal it tests is gone) now. For each other failing test, delete it now if Task 14 lists its file or the test for deletion; otherwise fix it. `test_self_render.py` stays red until Task 13 replaces it: skip it with `pytest.mark.skip(reason="replaced in Task 13")` so this task can commit green.

- [ ] **Step 7: Commit**

```bash
git add -A skills/repo-infra/scripts tests
git commit -m "check and apply work on pieces and callers (D30)

check reports pieces, callers, config and administration items in four
sections and never refuses a repository. apply installs or replaces pieces
on repo-infra/apply, one commit per piece, prints the upgrade notes of every
version crossed and what the callers must change, then stops. An edited
piece stops it with the merge files as before. Administration items run only
when named with --item.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 13: repo-infra runs on its own pieces

**Files:**
- Create in `.github/workflows/`: `ri-ci-lib.yml`, `ri-ci-claude-plugin.yml`, `ri-ci-python.yml`, `ri-ci-repo-infra-selftest.yml`, `ri-release-pr-current.yml`, `ri-publish-tag.yml`, `ri-publish-finalize.yml`
- Replace: `.github/workflows/changelog.yml`, `.github/workflows/release-pr.yml`, `.github/workflows/lib/*`, `.github/dependabot.yml`
- Rewrite: `.github/workflows/ci.yml`, `.github/workflows/release-build.yml`, `.github/workflows/release-publish.yml`, `.github/repo-infra.json`
- Create: `skills/repo-infra/references/examples/repo-infra/{ci.yml,release-build.yml,release-publish.yml,repo-infra.json}`
- Create: `tests/test_self_check.py`; delete: `tests/test_self_render.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_self_check.py
"""repo-infra is the first repository on its own pieces (D30): check on this
checkout finds nothing to do, and the example callers in the skill are this
repository's own files, so they cannot rot."""

import pathlib

import pytest

from repo_infra import cli

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "skills/repo-infra/references/examples/repo-infra"


def test_this_repository_passes_its_own_check(monkeypatch, capsys):
    monkeypatch.setattr(cli, "read_facts", lambda repo: cli.CONFORMING_FACTS)
    code = cli.main(["check", "--root", str(ROOT), "--repo", "oposs/repo-infra"])
    assert code == 0, capsys.readouterr().out


@pytest.mark.parametrize("name, installed", [
    ("ci.yml", ".github/workflows/ci.yml"),
    ("release-build.yml", ".github/workflows/release-build.yml"),
    ("release-publish.yml", ".github/workflows/release-publish.yml"),
    ("repo-infra.json", ".github/repo-infra.json"),
])
def test_the_examples_are_this_repositorys_files(name, installed):
    assert (EXAMPLES / name).read_text(encoding="utf-8") == (
        ROOT / installed).read_text(encoding="utf-8")
```

Run: `python3 -m pytest -q tests/test_self_check.py`. Expected: FAIL (the check reports `unknown` for the assembled files and `outdated` pieces).

- [ ] **Step 2: Install the pieces with the new apply.** From the worktree root, without network:

```bash
for p in changelog release-pr dependabot workflow-lib ri-ci-lib ri-ci-claude-plugin \
         ri-ci-python ri-ci-repo-infra-selftest ri-release-pr-current ri-publish-tag \
         ri-publish-finalize; do
  python3 - "$p" <<'EOF'
import pathlib, sys
sys.path.insert(0, "skills/repo-infra/scripts")
from repo_infra.pieces import load_pieces
piece = load_pieces()[sys.argv[1]]
for path, text in piece.files.items():
    target = pathlib.Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
EOF
done
```

This writes the files exactly as `apply` would; `apply` itself needs the GitHub facts, and this step must not touch the network. The commit is made in Step 5.

- [ ] **Step 3: Write the three callers and the config.**

`.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  # D28: Create release PR runs this file on the release branch before it
  # opens the pull request, with the commit to test in `ref`.
  workflow_call:
    inputs:
      ref:
        description: The commit to test; empty on push and pull_request.
        type: string
        required: false
        default: ''

permissions:
  contents: read

jobs:
  lib:
    uses: ./.github/workflows/ri-ci-lib.yml
    with:
      ref: ${{ inputs.ref }}

  plugin:
    uses: ./.github/workflows/ri-ci-claude-plugin.yml
    with:
      ref: ${{ inputs.ref }}

  python:
    uses: ./.github/workflows/ri-ci-python.yml
    with:
      ref: ${{ inputs.ref }}

  selftest:
    uses: ./.github/workflows/ri-ci-repo-infra-selftest.yml
    with:
      ref: ${{ inputs.ref }}

  release-pr-current:
    uses: ./.github/workflows/ri-release-pr-current.yml
    permissions:
      contents: read
      pull-requests: read
      checks: write
    with:
      ref: ${{ inputs.ref }}

<the ci-passed job from assets/callers/ci-passed.yml, word for word, with
 needs: [lib, plugin, python, selftest, release-pr-current]>
```

Paste the job; the angle-bracket line above is the instruction, not file text.

`.github/workflows/release-build.yml`:

```yaml
name: Release build

# Called by Create release PR on the release branch before the pull request
# exists (D28). repo-infra attaches no files to a release, so its build
# names the version and nothing else.
on:
  workflow_call:
    inputs:
      version:
        description: The version being released.
        type: string
        required: true
      ref:
        description: The release branch head to build.
        type: string
        required: true

permissions:
  contents: read

jobs:
  release-version:
    name: Release version
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - run: echo "Building v${VERSION} from ${REF}"
        env:
          VERSION: ${{ inputs.version }}
          REF: ${{ inputs.ref }}
```

`.github/workflows/release-publish.yml`:

```yaml
name: Publish release (automatic)

# Tags and publishes the release once its pull request merges (D28).
on:
  push:
    branches: [main]
    paths:
      - CHANGES.md

concurrency:
  group: release-publish
  cancel-in-progress: false

permissions:
  contents: read

jobs:
  publish:
    uses: ./.github/workflows/ri-publish-tag.yml
    permissions:
      contents: write
      pull-requests: read

  # finalize needs every other job of this file; check verifies it (D30).
  finalize:
    needs: [publish]
    if: needs.publish.outputs.release_id != ''
    uses: ./.github/workflows/ri-publish-finalize.yml
    permissions:
      contents: write
      actions: write
    with:
      release_id: ${{ needs.publish.outputs.release_id }}
      tag: ${{ needs.publish.outputs.tag }}
      head: ${{ needs.publish.outputs.head }}
```

Take the permissions of `publish` and `finalize` from the pieces' own `permissions:`; if a piece declares more, grant that.

`.github/repo-infra.json`: drop `ecosystems`, `publish` and `build`; keep `moving_major_tag` and `version_files` as they are.

- [ ] **Step 4: Copy the four files into the examples folder and run the checks**

```bash
mkdir -p skills/repo-infra/references/examples/repo-infra
cp .github/workflows/ci.yml .github/workflows/release-build.yml \
   .github/workflows/release-publish.yml .github/repo-infra.json \
   skills/repo-infra/references/examples/repo-infra/
git rm -q tests/test_self_render.py
python3 -m pytest -q tests/test_self_check.py
```

Expected: PASS. If `check` reports something, read its row: it is either a mistake in the callers above or a defect in the check; fix the right one and say which in the commit body.

- [ ] **Step 5: Run the gate, look at the release-pr grant, and commit**

Run: `make check`
Expected: PASS. `test_self_check` also proves that Create release PR's fixed grant to `ci.yml` covers what `ci.yml` now needs (Review Focus 4).

```bash
git add -A .github skills/repo-infra/references/examples tests
git commit -m "Run repo-infra on its own pieces and callers (D30)

ci.yml, release-build.yml and release-publish.yml are callers now: short
files that call the pieces with uses: ./.github/workflows/... and hold
ci-passed and finalize. The pieces are installed byte for byte. The
skill's examples are these files, and a test keeps them equal.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 14: Remove the detector, the assembler, the migration and the stamp

**Files:**
- Delete: `skills/repo-infra/scripts/repo_infra/{detect,assemble,migrate,seam,state}.py`
- Modify: `skills/repo-infra/scripts/repo_infra/markers.py`, `apply.py`
- Delete: `skills/repo-infra/assets/{ci,publish,release-build,workflows,build,m4}/`, `skills/repo-infra/assets/detection.json`
- Modify: `skills/repo-infra/assets/manifest.json`, `skills/repo-infra/assets/generations.json`, `tests/generations.py`, `tests/test_generations.py`, `tests/test_manifest.py`, `tests/test_markers.py`
- Delete tests and fixtures as listed in Step 3

- [ ] **Step 1: Delete the modules and the old assets**

```bash
git rm -q skills/repo-infra/scripts/repo_infra/{detect,assemble,migrate,seam,state}.py
git rm -rq skills/repo-infra/assets/{ci,publish,release-build,workflows,build,m4}
git rm -q skills/repo-infra/assets/detection.json
```

Remove `ci_blocks`, `publish_blocks`, `release_build_blocks`, `build_assets` and `assets` from `manifest.json`; it keeps `pieces`, `actions` and `gh`. In `tests/test_manifest.py`, the expected key set becomes `{"pieces", "actions", "gh"}`; delete the tests about the removed sections and keep the action-major test.

- [ ] **Step 2: Trim `markers.py`**

Delete `_STAMP`, `_digest`, `_first_marker`, `strip_stamp`, `stamp`, `pristine` and `marker_line`, and the `hashlib` import. Replace the module docstring with:

```python
"""Version markers.

Every piece carries `repo-infra: <piece> vN` on its first comment line (D30).
The marker says which piece and which version a file claims to be; whether
the file is that version is decided by its bytes against generations.json,
in check.py. A marker that names no piece is how check finds a file of the
assembled standard that still needs converting.
"""
```

- [ ] **Step 3: Delete the tests of removed code and fix the rest**

```bash
git rm -q tests/{test_assemble,test_detect,test_migrate,test_ci_local,test_seam,test_state,test_apply_files,test_release_contracts}.py
git rm -rq tests/fixtures/{assets-mini,repo-both,repo-checkmk,repo-claude-plugin,repo-empty,repo-go,repo-node-ambiguous,repo-node-bun-npm,repo-node-bun,repo-node-npm,repo-node-pnpm-bun,repo-node-pnpm-npm,repo-node-pnpm,repo-perl-autotools,repo-perl-mkpl,repo-python,repo-rust,repo-selfhost}
git rm -q tests/fixtures/detection-mini.json
```

Keep `tests/fixtures/lib-v0.2.0` (`test_changelog_gate.py` uses it), `tests/fixtures/gh`, `tests/fixtures/autotools-driver`.

Before deleting `test_state.py`, confirm Task 5 moved its `classify_remote` tests; before deleting `test_release_contracts.py`, confirm Task 5 covers `refused_release_files` and `gitea_packages`; before deleting `test_seam.py`, port any case it has that `tests/test_callers.py` does not (a checkout with a quoted `ref`, an upload name differing only in case) as a `ref_problems` test.

Then remove from the remaining test files every test that imports `detect`, `assemble`, `render_all`, `migrate`, `stamp`, `pristine` or `strip_stamp`:

```bash
grep -ln "detect\|assemble\|render_all\|migrate\|stamp\|pristine\|ci_blocks\|publish_blocks" tests/*.py
```

For each hit, delete the test functions that use them (the survey in the plan's history lists them: `test_blocks.py` detection and aggregator tests, `test_build_assets.py::test_a_repository_that_did_not_ask_for_it_does_not_get_it`, `test_container_m4.py` same name, `test_man_build.py::test_a_repository_that_did_not_ask_for_them_does_not_get_them`, `test_ci_man.py` detection and config-key tests, `test_ci_rust_musl.py` add-on placement tests, `test_github_action.py` detection and contract tests, `test_release_pr.py::test_the_union_covers_every_permission_ci_yml_asks_for` (`test_self_check` covers it), `test_release_mode.py` tests built on `render_all`, `test_markers.py` stamp tests and `test_parses_indented_block_markers_in_an_assembled_file`). Keep every test that runs a step or reads a piece.

- [ ] **Step 4: Simplify `tests/generations.py`**

Replace `BLOCK_FOLDERS` and `_manifest_versions` with:

```python
def _manifest_versions(assets_root, marked):
    """{path: version} for the unmarked files whose version the manifest
    gives (the ruleset under `gh`)."""
    manifest_path = assets_root / "manifest.json"
    if not manifest_path.is_file():
        return {}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    versions = {meta["source"]: meta["version"]
                for meta in manifest.get("gh", {}).values()
                if isinstance(meta, dict) and "source" in meta and "version" in meta}
    return {path: version for path, version in versions.items()
            if path not in marked and (assets_root / path).is_file()}
```

and change the module docstring's second paragraph to: "A piece is recorded under its marker's version, file by file. An unmarked file the manifest names under `gh` (the ruleset) is recorded under that entry's version." In `tests/test_generations.py`, delete the tests built on `blocks()` (`test_a_block_is_recorded_under_its_manifest_version`, `test_a_block_reworded_under_the_same_manifest_version_is_refused`) and the `blocks` helper.

Remove every key of `generations.json` whose file no longer exists (the old `ci/`, `publish/`, `release-build/`, `workflows/`, `build/`, `m4/` paths), then run `make generations` to confirm it refuses nothing.

- [ ] **Step 5: Trim `apply.py`**

Delete whatever Task 12 left that has no user now (`commit_item`, `write_config`, `config_text`, `_compact`, `CONFIG`, `WIDTH`). Confirm:

```bash
grep -rn "detect\|assemble\|migrate\|seam\|from .state\|stamp\|pristine\|commit_item\|config_text" skills/repo-infra/scripts tests
```

Expected: no output.

- [ ] **Step 6: Run the gate and the container test, then commit**

Run: `make check`
Expected: PASS.

Run: `systemd-run --user --scope -p MemoryMax=4G -- make test-container`
Expected: PASS.

```bash
git add -A
git commit -m "Remove detection, the assembler, the D28 migration and the stamp (D30)

Nothing decides any more what a repository needs, and no workflow is
assembled: repo-infra and its tests run on pieces and callers. The D29
stamp is gone because a piece is identified by its bytes against every
published version.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 15: The skill, the references and the commands

**Files:**
- Rewrite: `skills/repo-infra/SKILL.md`, `commands/check.md`, `commands/apply.md`
- Create: `skills/repo-infra/references/onboarding.md`
- Modify: `skills/repo-infra/references/conventions.md`, `release-flow.md`, `teaching-the-standard.md`, `README.md`, `skills/man-pages/SKILL.md`, `skills/man-pages/evals/files/setup/.github/repo-infra.json`, `CHANGES.md`
- Modify: `tests/test_skill.py`

Load the `writing-style` skill before writing any of this.

- [ ] **Step 1: Update `tests/test_skill.py` first**

Keep the frontmatter, commands, entry point and help tests. Replace the reference assertions with:

```python
REFS = ROOT / "skills/repo-infra/references"


def test_the_references_the_skill_names_exist():
    skill = (ROOT / "skills/repo-infra/SKILL.md").read_text(encoding="utf-8")
    for name in ("catalogue.md", "onboarding.md", "conventions.md", "release-flow.md",
                 "teaching-the-standard.md", "examples/repo-infra"):
        assert f"references/{name}" in skill
        assert (REFS / name).exists()


def test_the_skill_stays_short():
    assert len((ROOT / "skills/repo-infra/SKILL.md").read_text(
        encoding="utf-8").splitlines()) <= 120


def test_onboarding_holds_what_detection_used_to_know():
    text = (REFS / "onboarding.md").read_text(encoding="utf-8")
    for needle in ("Cargo.lock", "pnpm-lock.yaml", "package-lock.json", "VERSION",
                   ".claude-plugin/plugin.json", "assets/callers/ci-passed.yml",
                   "apply --item"):
        assert needle in text


def test_nothing_points_at_the_removed_machinery():
    for path in [ROOT / "skills/repo-infra/SKILL.md", ROOT / "commands/check.md",
                 ROOT / "commands/apply.md", ROOT / "README.md",
                 *REFS.glob("*.md"), ROOT / "skills/man-pages/SKILL.md"]:
        text = path.read_text(encoding="utf-8")
        for gone in ("detection.json", "does not recognise", "ci_local", "release_build_local",
                     "publish_local", "sha256=", "\"ci\": [\"ci-man\"]"):
            assert gone not in text, f"{path.name} still says {gone}"
```

Keep the container and `writing-style`/`man-pages` assertions that still hold; drop the `["ci-man"]` and "A CI block may carry build assets" assertions.

Run: `python3 -m pytest -q tests/test_skill.py`. Expected: FAIL.

- [ ] **Step 2: Write `references/onboarding.md`**

Sections, in this order:
1. **The procedure**: the six steps of the spec's "Onboarding procedure", with `apply --item <piece>` as the way to copy a piece and `check` as the gate.
2. **Callers**: the shape of `ci.yml`, `release-build.yml` and `release-publish.yml`, pointing at `references/examples/repo-infra/` and `assets/callers/ci-passed.yml`; the rules check enforces (needs lists, `if: always()`, permissions on each call job, `ref` on every checkout, reserved artifact names, no remote references).
3. **Project-owned workflows**: `ci-local.yml`, `release-build-local.yml`, `action-test.yml`; the contract from the old "Project-owned workflows behind a fixed seam" section of `conventions.md`, rewritten for callers.
4. **version_files by build file**: the entries `detection.json` proposed, as JSON, for `.claude-plugin/plugin.json`, `pyproject.toml`, `Cargo.toml`, `package.json` and `VERSION`, plus the `Cargo.lock` entry per crate (what `_cargo_lock_entries` built: the root package and every workspace member taking its version from `[workspace.package]`).
5. **Questions to ask**: the lockfile ambiguities (`pnpm-lock.yaml` with `package-lock.json`, `pnpm-lock.yaml` with `bun.lock`, and the others in `detection.json` `ambiguities`), in the words `detection.json` used; and the candidates (`docs/manual.md` suggests `ri-ci-man`, `configure.ac` with `cpanfile` suggests `ri-release-source-tarball`, `book.toml` is a docs site no piece covers).
6. **Administration items**: the order (rename the default branch, land `ci.yml` and `changelog.yml` on main, then the ruleset), each item by `apply --item`, each confirmed with the user.

Take section 4 and 5 from `git show HEAD~5:skills/repo-infra/assets/detection.json` (any commit before Task 14).

- [ ] **Step 3: Rewrite `SKILL.md`** (at most 120 lines)

What repo-infra is (one paragraph); the three file kinds (the spec's table); the two jobs: onboarding (`references/onboarding.md`) and updating (`check`, `apply`, the printed notes, caller changes, `check` until 0); the settled decisions, one line each with the reference file that explains it (D1 to D30, marking D11 and D29 as superseded by D30 and D24 to D27 as superseded by D28 as conventions.md already records); the traps that stay (ci-passed is inline and word for word, the ruleset waits for main, administration items are outward-facing, the merge procedure for an edited piece); links to `references/catalogue.md`, `onboarding.md`, `examples/repo-infra/`, `conventions.md`, `release-flow.md`, `teaching-the-standard.md`, and the `writing-style` and `man-pages` skills.

- [ ] **Step 4: Update the other references**

- `conventions.md`: delete "`.github/repo-infra.json` is the repository's own decisions, not detection output" and replace it with the kept key list and Decision G; move "Project-owned workflows behind a fixed seam" into onboarding.md and leave a one-line pointer; rewrite "Markers record a generation, never a content hash" and "The stamp (D29)" as one section "Markers and bytes (D30)" saying D11 and D29 are superseded and why.
- `release-flow.md`: every mention of the assembled `finalize` needs list or `publish_local` becomes the caller's `needs:` list that check verifies; "Gitea packages (publish-gitea-packages)" becomes `ri-publish-gitea`, called from `release-publish.yml`.
- `teaching-the-standard.md`: the trigger is "no piece fits"; stage 3 (upstream) lists what a new piece needs: folder, marker, header block, `CHANGES.md`, manifest entry, `make generations`, `make catalogue`, tests that run its steps.
- `commands/check.md`: the four sections, the states, exit code; ask the user before acting on an `edited` piece.
- `commands/apply.md`: bare `apply` installs and replaces pieces, prints notes and findings, stops; change callers and config; `check` until 0; the merge procedure for an edited piece (kept from today's text, with "stamp" replaced by "matches no published version"); administration items with `--item`, each confirmed, in the onboarding order; delete the D28 migration section.
- `README.md`: describe the toolbox and the two commands in the new terms.
- `skills/man-pages/SKILL.md` and its eval fixture: replace `"ci": ["ci-man"]` with calling `ri-ci-man` from `ci.yml` and installing the `man` and `man-lua` pieces.

- [ ] **Step 5: Changelog entries**

Under `## [Unreleased]` in `CHANGES.md` (readers are users and administrators; three sentences at most each):

```markdown
### Changed
- `check` no longer stops with "the standard does not recognise this repository": it reports every installed piece as `current`, `outdated`, `edited` or `unknown`, checks the repository's own `ci.yml`, `release-build.yml` and `release-publish.yml` against the pieces they call, and lists the administration items. A repository picks its pieces from the catalogue in the skill and calls them from these files.
- The workflows repo-infra ships are now separate files named `ri-*.yml` that the repository calls; `ci.yml`, `release-build.yml` and `release-publish.yml` are no longer generated and belong to the repository. A repository on the generated files sees `unknown` for them in `check` until they are rewritten (see `references/onboarding.md` in the skill).
- `apply` replaces outdated pieces, one commit each named `Install <piece> vN from the repo-infra standard`, prints the upgrade notes of every version it crossed and what the callers must change, and stops. Branch protection, the `no-changelog` label and the Actions setting are applied only when named with `apply --item`.
- `.github/repo-infra.json` no longer reads `ecosystems`, `ci`, `ci_local`, `publish`, `build`, `publish_local`, `release_build`, `release_build_local`, `skip` or `answers`; `check` asks for them to be removed.

### Fixed
- `check` reports a call that would fail at the start of a run: an input or secret the called workflow does not declare or requires, a missing workflow file, or a job that grants fewer token permissions than the workflow it calls needs.
```

Run `python3 -m pytest -q tests/test_no_em_dash.py tests/test_skill.py`.

- [ ] **Step 6: Run the gate and commit**

Run: `make check`
Expected: PASS.

```bash
git add -A skills commands README.md CHANGES.md tests/test_skill.py
git commit -m "Teach the skill pieces and callers instead of detection (D30)

SKILL.md names the three file kinds and the two jobs. onboarding.md holds
the procedure, the caller rules check enforces, and what detection.json
knew: the version_files entries per build file and the questions to ask.
The command docs describe the new check and apply.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 16: Verify on GitHub

**Files:** none changed unless a step finds a defect.

- [ ] **Step 1: Run every gate locally once more**

```bash
make check
systemd-run --user --scope -p MemoryMax=4G -- make test-container
make catalogue && git diff --exit-code skills/repo-infra/references/catalogue.md
make generations && git diff --exit-code skills/repo-infra/assets/generations.json
```

Expected: all pass, no diff.

- [ ] **Step 2: Ask the user before pushing.** Pushing publishes the branch. With approval:

```bash
git push -u origin worktree-pieces
gh pr create --base main --title "Pieces and callers (D30)" --label no-changelog --body-file <file>
```

The pull request carries changelog entries, so drop `--label no-changelog` if `changelog-updated` should run; decide with the user. The body summarises the spec, lists Decisions A to M, says the plugin takes a major version step at the next release, and ends with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.

- [ ] **Step 3: Watch the checks of the pull request**

Run: `gh pr checks --watch`
Expected: `ci-passed` and `changelog-updated` green. Nested jobs report as `lib / Workflow library tests` and similar; `ci-passed` is still a top-level context, which is what the ruleset requires. If GitHub refuses to start a run with a permissions message, the permission validation of Task 4 missed a case: add the case as a test before fixing the caller.

- [ ] **Step 4: Report the open end-to-end proof.** The release flow on the new files (Create release PR running `ci.yml` and `release-build.yml` as calls, the guard ignoring nested jobs by id, `ri-publish-tag` and `ri-publish-finalize` publishing) is proven only by the next real release of repo-infra. Tell the user, and propose cutting that release as a major version once the pull request merges.

---

## Self-review

**Spec coverage.** Decisions: onboarding by the AI (Task 15 onboarding.md, no detector after Task 14); update by tool plus notes (Tasks 2, 12); pieces 1:1 (Tasks 7 to 11, 13); local include (all callers); no remote references (Task 3); mdmost by hand (out of this plan, stated). File kinds: pieces (Task 2 model, Tasks 7 to 11), callers (Tasks 3, 4, 13), config (Task 5). What goes away (Task 14). What stays: release flow (Tasks 10, 13), administration items (Tasks 5, 12), decisions (Task 15), merge procedure (Task 12). The skill (Tasks 6, 15). The tool: `check` states and validations (Tasks 3 to 5), `apply` (Task 12), upgrade notes (Tasks 2, 7 to 11, 12). Converting the assets (Tasks 7 to 11, with Decision A for the frames). New pieces on Smalti and Order of work steps 2 and 3: separate plans. Testing: catalogue (Task 6), pieces (Tasks 2, 3), check fixtures (Tasks 3 to 5), apply (Task 12), end to end (Tasks 13, 16).

**Review Focus.** 1 → `test_an_assembled_file_is_unknown_and_points_at_onboarding` (Task 5). 2 → `test_an_unreadable_caller_is_one_problem_and_the_rest_is_still_validated` (Task 3). 3 → `test_apply_prints_the_notes_and_the_new_caller_finding` (Task 12). 4 → `tests/test_permissions.py` (Task 4) and `test_this_repository_passes_its_own_check` (Task 13). 5 → `test_a_project_file_in_a_piece_directory_is_ignored` (Task 5) and `test_apply_removes_a_file_the_new_version_no_longer_ships` (Task 12).

**Names used across tasks.** `Item(section, name, state, detail)`, `ATTENTION`, `PieceState(state, installed, edited)`, `piece_state(repo_root, piece, history)`, `install_piece(repo_root, piece, state, history, merged=None)`, `commit_piece(repo_root, name, version, paths, merged=False)`, `validate(docs, pieces, assets=ASSETS)`, `needed(name, docs)`, `permission_text(levels)`, `load_pieces(assets)`, `load_published(assets)`, `upgrade_notes(name, old, new, assets)`.

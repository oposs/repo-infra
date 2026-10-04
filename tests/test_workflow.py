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
    "empty flow mapping": "permissions: {}\njobs:\n  a:\n    with: { }\n",
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
    "document end": "a: b\n...\n",
    "literal keep at the end": "run: |+\n  one\n",
    "literal keep at the end with a blank": "run: |+\n  one\n\n",
    "flow sequence with a quoted hash": "a: [x, 'b #c', \"d #e\"] # note\n",
    "crlf": "run: |\r\n  one\r\n  two\r\nb: c\r\n",
    "literal with a wide blank line": "run: |\n  one\n      \n  two\n",
    "folded with a wide blank line": "run: >\n  one\n      \n  two\n",
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
    "plain value continued as a key": ("a: b\n  c: d\n", "line 2"),
    "second document": ("a: b\n---\nc: d\n", "line 2"),
    "content after the document end": ("a: b\n...\nc: d\n", "line 3"),
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

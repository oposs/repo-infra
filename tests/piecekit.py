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
      - uses: actions/checkout@v7
        with:
          ref: ${{ github.event.pull_request.base.sha }}
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

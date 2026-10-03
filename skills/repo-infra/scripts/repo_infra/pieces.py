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

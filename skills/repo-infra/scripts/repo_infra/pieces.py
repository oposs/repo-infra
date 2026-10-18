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
from dataclasses import dataclass, replace

from .markers import parse_markers

ASSETS = pathlib.Path(__file__).resolve().parents[2] / "assets"

# D33: consumers call the pieces of this repository remotely, at the moving
# major tag. The pieces lie in .github/workflows/ of the plugin root, the
# only directory GitHub runs a reusable workflow from.
HOME_REPO = "oposs/repo-infra"
MAJOR = "v2"


def plugin_root(assets):
    """The repository root of the plugin: assets is skills/repo-infra/assets."""
    return pathlib.Path(assets).resolve().parents[2]


COMMENT = {".yml": "#", ".yaml": "#", ".mk": "#", ".js": "//", ".m4": "dnl", ".lua": "--"}
FIELDS = ("Purpose", "Choose", "Supplies", "Pieces", "Produces", "Call", "Also")
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
    def remote(self):
        return self.kind == "remote"

    @property
    def workflow(self):
        return self.remote or (self.kind == "file"
                               and self.target.startswith(".github/workflows/"))

    @property
    def uses(self):
        """How a consumer calls a remote piece (D33)."""
        return f"{HOME_REPO}/{self.target}@{MAJOR}"

    @property
    def needs(self):
        return [p.strip() for p in self.header.get("Pieces", "").split(",") if p.strip()]


def comment_of(path):
    return COMMENT[pathlib.PurePosixPath(path).suffix]


def _commented(stripped, comment):
    """True when the stripped line is a comment. A token that is a word
    (`dnl`) must stand alone: `dnlPurpose:` is another m4 word."""
    if not stripped.startswith(comment):
        return False
    after = stripped[len(comment):len(comment) + 1]
    return not (comment[-1].isalnum() and (after.isalnum() or after == "_"))


def parse_header(text, comment):
    """The header fields after the marker (D30), as {field: text}."""
    lines = text.split("\n")
    first = next((i for i, line in enumerate(lines) if _commented(line.strip(), comment)),
                 None)
    if first is None or not parse_markers(lines[first]):
        raise PieceError("the marker must be the first comment line")
    fields, current, started = {}, None, False
    for line in lines[first + 1:]:
        stripped = line.strip()
        if not _commented(stripped, comment):
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


def _remote_target(name):
    return f".github/workflows/{name}.yml"


def source_path(name, spec, assets):
    """Where the store keeps the piece: under assets, or for a remote piece
    in .github/workflows/ of the plugin root."""
    if spec.get("kind") == "remote":
        return plugin_root(assets) / _remote_target(name)
    return pathlib.Path(assets) / _source(name, spec)


def load_pieces(assets=ASSETS):
    assets = pathlib.Path(assets)
    found = {}
    for name, spec in _manifest(assets).get("pieces", {}).items():
        kind = spec.get("kind", "file")
        if kind == "remote":
            target = _remote_target(name)
            source = source_path(name, spec, assets)
            if not source.is_file():
                raise PieceError(f"{name}: {target} is missing from the plugin")
            text = source.read_text(encoding="utf-8")
            markers = parse_markers(text)
            if not markers or markers[0].asset != name:
                raise PieceError(f"{target}: the first marker must be `repo-infra: {name} "
                                 f"{MAJOR}`")
            if f"v{markers[0].version}" != MAJOR:
                raise PieceError(f"{target}: a remote piece is {MAJOR}, the major tag "
                                 f"consumers call; it says v{markers[0].version}")
            try:
                header = parse_header(text, "#")
            except PieceError as error:
                raise PieceError(f"{target}: {error}") from error
            found[name] = Piece(name, markers[0].version, target, kind,
                                spec.get("group", ""), bool(spec.get("core")),
                                {target: text}, header)
            continue
        for key in ("target", "header") if kind == "dir" else ("target",):
            if key not in spec:
                raise PieceError(f"{name}: the manifest entry lacks {key}")
        source = assets / _source(name, spec)
        if not (source.is_dir() if kind == "dir" else source.is_file()):
            raise PieceError(f"{name}: {_source(name, spec)} is missing from the asset store")
        if kind == "dir":
            files = {f"{spec['target']}/{child.name}": child.read_text(encoding="utf-8")
                     for child in sorted(source.iterdir()) if child.is_file()}
            lead = f"{spec['target']}/{spec['header']}"
            if lead not in files:
                raise PieceError(f"{name}: the header file {spec['header']} is not in "
                                 f"{_source(name, spec)}")
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
        if spec.get("kind") == "remote":
            published[name] = {}
            continue
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


# The one piece whose text depends on the repository (#92). Dependabot reads
# only .github/dependabot.yml, so the ecosystems of the repository's own code
# cannot be pieces of their own. The asset is the text for a repository that
# calls none of the CI pieces below; one entry per ecosystem follows it.
DEPENDABOT = "dependabot"
ECOSYSTEMS = {"ri-ci-go": "gomod", "ri-ci-node-bun": "bun", "ri-ci-node-pnpm": "npm",
              "ri-ci-python": "pip", "ri-ci-rust": "cargo", "ri-ci-rust-musl": "cargo"}


def dependabot_entry(ecosystem):
    """The entry for one ecosystem. generations.json records only the asset,
    and `published_base` finds it by stripping this text, so a change here
    must keep stripping the old text, or every v3 copy reads edited.
    tests/fixtures/dependabot/v3-cargo-npm.yml holds a frozen v3 copy."""
    return (f"  - package-ecosystem: {ecosystem}\n"
            "    directory: /\n"
            "    schedule:\n"
            "      interval: weekly\n"
            "    labels:\n"
            "      - dependencies\n"
            "      - no-changelog\n")


def render(piece, called):
    """`piece` as a repository holds it whose callers call the pieces named
    in `called`. Only dependabot differs from its asset."""
    if piece.name != DEPENDABOT:
        return piece
    ecosystems = sorted({ECOSYSTEMS[name] for name in called if name in ECOSYSTEMS})
    text = piece.files[piece.target] + "".join(map(dependabot_entry, ecosystems))
    return replace(piece, files={piece.target: text})


def published_base(name, data):
    """The bytes of a copy of piece `name` without the entries `render`
    appends: the text generations.json records a version by."""
    if name != DEPENDABOT:
        return data
    entries = [dependabot_entry(e).encode("utf-8") for e in sorted(set(ECOSYSTEMS.values()))]
    stripped = True
    while stripped:
        stripped = False
        for entry in entries:
            if data.endswith(entry):
                data, stripped = data[:-len(entry)], True
    return data


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

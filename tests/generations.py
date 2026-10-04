"""The text of every shipped asset, recorded under its version.

A test fails when an asset's text changes and its version does not. PR #43
reworded a comment in changelog.yml and kept v3, so two repositories both at
"v3" held different files. `make generations` records a new version and
refuses to change a recorded one.

A piece is recorded under its marker's version, file by file. An unmarked
file the manifest names under `gh` (the ruleset) is recorded under that
entry's version.

Every release tag's piece files are recorded too, under the path the piece
has now. v0.2.0 shipped changelog v2 under workflows/, and without its bytes
a repository still on it read edited instead of outdated (Decision L).
"""

import hashlib
import json
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "skills/repo-infra/scripts"))
from repo_infra.check import unstamped  # noqa: E402
from repo_infra.markers import parse_markers  # noqa: E402
from repo_infra.pieces import _source  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSETS = ROOT / "skills/repo-infra/assets"
RECORD = ASSETS / "generations.json"
TAG_ASSETS = "skills/repo-infra/assets"


class NoHistory(Exception):
    """git cannot list the tags here (no git, or not a checkout)."""

def _digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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


def scan(assets_root):
    assets_root = pathlib.Path(assets_root)
    found = {}
    for path in sorted(assets_root.rglob("*")):
        if not path.is_file() or path.name == "generations.json":
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        markers = parse_markers(text)
        if markers:
            found[str(path.relative_to(assets_root))] = (markers[0].version, _digest(text))
    marked = {path: version for path, (version, _) in found.items()}
    for path, version in _manifest_versions(assets_root, marked).items():
        text = (assets_root / path).read_text(encoding="utf-8", errors="ignore")
        found[path] = (version, _digest(text))
    return dict(sorted(found.items()))


def piece_sources(assets_root):
    """The source path of every piece the manifest ships: a file, or a
    directory whose files lie below it."""
    manifest_path = pathlib.Path(assets_root) / "manifest.json"
    if not manifest_path.is_file():
        return []
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return sorted(_source(name, spec) for name, spec in manifest.get("pieces", {}).items())


def _of_a_piece(path, shipped):
    return any(path == source or path.startswith(source + "/") for source in shipped)


def vanished(record, scanned, shipped=()):
    """The recorded paths `scan` no longer finds, with what to do about each.

    A path below a piece the manifest still ships stays: it is a file an
    older version shipped and the current one dropped, and apply removes a
    copy only when its bytes are a published version. Advising its removal
    made `make generations` loop, since the next run re-added it from the
    release tags."""
    return [f"{path} is recorded but no longer scanned; if it was removed on "
            "purpose, delete it from generations.json"
            for path in sorted(record)
            if path not in scanned and not _of_a_piece(path, shipped)]


def updated(record, scanned, shipped=()):
    gone = vanished(record, scanned, shipped)
    if gone:
        raise ValueError("\n".join(gone))
    record = {path: dict(versions) for path, versions in record.items()}
    for path, (version, digest) in scanned.items():
        known = record.setdefault(path, {}).get(str(version))
        if known is not None and known != digest:
            raise ValueError(f"{path}: v{version} is recorded with other text; "
                             "bump the marker, or for a file without one its "
                             "version in manifest.json")
        record[path][str(version)] = digest
    return record


def _git(*args, text=True):
    try:
        result = subprocess.run(("git", *args), cwd=ROOT, capture_output=True, text=text)
    except OSError as error:
        raise NoHistory(f"git cannot run: {error}") from error
    if result.returncode != 0:
        raise NoHistory(f"git {' '.join(args)} failed: {result.stderr}")
    return result.stdout


def release_tags():
    """The vX.Y.Z tags of this checkout. A shallow clone has none."""
    return sorted(t for t in _git("tag", "--list", "v*").split() if t)


def fetch_release_tags():
    """Fetch the vX.Y.Z tags from origin, one commit deep each, into a clone
    made without them."""
    _git("fetch", "--quiet", "--depth=1", "origin", "+refs/tags/v*:refs/tags/v*")


def _old_sources(manifest):
    """{piece name: (source path below the assets, is a directory)} from a
    manifest of any release. Up to v0.3.1 the entries named their `source`;
    from D30 on, the `pieces` entries derive it."""
    found = {}
    for section, entries in manifest.items():
        if not isinstance(entries, dict):
            continue
        for name, spec in entries.items():
            if not isinstance(spec, dict):
                continue
            if "source" in spec:
                found[name] = (spec["source"], spec.get("kind") == "dir")
            elif section == "pieces" and "target" in spec:
                found[name] = (_source(name, spec), spec.get("kind") == "dir")
    return found


def released_files(tag, assets_root=ASSETS):
    """{record path: (version, bytes)} for the piece files shipped at `tag`,
    under the path each piece has now, the D29 stamp removed. A file without
    the piece's marker is skipped."""
    names = _git("ls-tree", "-r", "--name-only", tag, "--", TAG_ASSETS).split("\n")
    if f"{TAG_ASSETS}/manifest.json" not in names:
        return {}
    old = _old_sources(json.loads(_git("show", f"{tag}:{TAG_ASSETS}/manifest.json")))
    now = json.loads((pathlib.Path(assets_root) / "manifest.json").read_text(
        encoding="utf-8")).get("pieces", {})
    found = {}
    for name, spec in now.items():
        if name not in old:
            continue
        source, is_dir = old[name]
        new = _source(name, spec)
        if is_dir:
            prefix = f"{TAG_ASSETS}/{source}/"
            pairs = [(f"{new}/{f[len(prefix):]}", f) for f in names if f.startswith(prefix)]
        else:
            pairs = [(new, f"{TAG_ASSETS}/{source}")] if f"{TAG_ASSETS}/{source}" in names else []
        for record_path, path in pairs:
            data = unstamped(_git("show", f"{tag}:{path}", text=False))
            markers = parse_markers(data.decode("utf-8", errors="replace"))
            if markers and markers[0].asset == name:
                found[record_path] = (markers[0].version, data)
    return dict(sorted(found.items()))


def released(tag, assets_root=ASSETS):
    """{record path: (version, digest)} for the piece files shipped at `tag`."""
    return {path: (version, hashlib.sha256(data).hexdigest())
            for path, (version, data) in released_files(tag, assets_root).items()}


def with_released(record, found):
    """`record` with the released versions in `found` added. A released
    version recorded with other bytes is refused: one version, one text."""
    record = {path: dict(versions) for path, versions in record.items()}
    for path, (version, digest) in found.items():
        known = record.setdefault(path, {}).get(str(version))
        if known is not None and known != digest:
            raise ValueError(f"{path}: v{version} is recorded with other text than "
                             "a release shipped")
        record[path][str(version)] = digest
    return record


if __name__ == "__main__":
    current = json.loads(RECORD.read_text(encoding="utf-8")) if RECORD.is_file() else {}
    try:
        new = updated(current, scan(ASSETS), piece_sources(ASSETS))
        try:
            tags = release_tags()
        except NoHistory as error:
            print(f"release tags not read: {error}", file=sys.stderr)
            tags = []
        for tag in tags:
            new = with_released(new, released(tag))
    except ValueError as error:
        sys.exit(str(error))
    RECORD.write_text(json.dumps(new, indent=2, sort_keys=True) + "\n", encoding="utf-8")

"""The text of every shipped asset, recorded under its version.

A test fails when an asset's text changes and its version does not. PR #43
reworded a comment in changelog.yml and kept v3, so two repositories both at
"v3" held different files. `make generations` records a new version and
refuses to change a recorded one.

A file with a marker is recorded under the marker's version. A block of an
assembled file carries no marker of its own; assemble.py writes one from the
version manifest.json gives it, so that is the version it is recorded under.
The unmarked rest of a block folder (the CI aggregator, the publish finalize
job) is part of the frame, and is recorded under the frame's marker version.
An unmarked file named as a `source` in manifest.json (the ruleset) is
recorded under that entry's version.
"""

import hashlib
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "skills/repo-infra/scripts"))
from repo_infra.markers import parse_markers  # noqa: E402

ASSETS = pathlib.Path(__file__).resolve().parents[1] / "skills/repo-infra/assets"
RECORD = ASSETS / "generations.json"

# Where assemble.py reads each kind of block from: `<folder>/<name>.yml`.
BLOCK_FOLDERS = {"ci_blocks": "ci", "publish_blocks": "publish",
                 "release_build_blocks": "release-build"}


def _digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _manifest_versions(assets_root, marked):
    """{path: version} for the unmarked files whose version lives in the
    manifest; `marked` maps every marked path to its marker version."""
    manifest_path = assets_root / "manifest.json"
    if not manifest_path.is_file():
        return {}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    versions = {}
    for section in manifest.values():
        if not isinstance(section, dict):
            continue
        for meta in section.values():
            if isinstance(meta, dict) and "source" in meta and "version" in meta:
                versions[meta["source"]] = meta["version"]
    for section, folder in BLOCK_FOLDERS.items():
        names = manifest.get(section, {})
        for name, meta in names.items():
            versions[f"{folder}/{name}.yml"] = meta["version"]
        frames = [v for p, v in marked.items() if p.startswith(folder + "/")]
        if len(frames) != 1:
            continue
        for path in sorted((assets_root / folder).glob("*")):
            relative = f"{folder}/{path.name}"
            if path.is_file() and path.stem not in names:
                versions.setdefault(relative, frames[0])
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


def updated(record, scanned):
    record = {path: dict(versions) for path, versions in record.items()}
    for path, (version, digest) in scanned.items():
        known = record.setdefault(path, {}).get(str(version))
        if known is not None and known != digest:
            raise ValueError(f"{path}: v{version} is recorded with other text; "
                             "bump the marker, or for a file without one its "
                             "version in manifest.json")
        record[path][str(version)] = digest
    return record


if __name__ == "__main__":
    current = json.loads(RECORD.read_text(encoding="utf-8")) if RECORD.is_file() else {}
    try:
        new = updated(current, scan(ASSETS))
    except ValueError as error:
        sys.exit(str(error))
    RECORD.write_text(json.dumps(new, indent=2, sort_keys=True) + "\n", encoding="utf-8")

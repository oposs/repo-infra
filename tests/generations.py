"""The text of every shipped asset, recorded under its version.

A test fails when an asset's text changes and its version does not. PR #43
reworded a comment in changelog.yml and kept v3, so two repositories both at
"v3" held different files. `make generations` records a new version and
refuses to change a recorded one.

A piece is recorded under its marker's version, file by file. An unmarked
file the manifest names under `gh` (the ruleset) is recorded under that
entry's version.
"""

import hashlib
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "skills/repo-infra/scripts"))
from repo_infra.markers import parse_markers  # noqa: E402

ASSETS = pathlib.Path(__file__).resolve().parents[1] / "skills/repo-infra/assets"
RECORD = ASSETS / "generations.json"

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


def vanished(record, scanned):
    """The recorded paths `scan` no longer finds, with what to do about each."""
    return [f"{path} is recorded but no longer scanned; if it was removed on "
            "purpose, delete it from generations.json"
            for path in sorted(record) if path not in scanned]


def updated(record, scanned):
    gone = vanished(record, scanned)
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


if __name__ == "__main__":
    current = json.loads(RECORD.read_text(encoding="utf-8")) if RECORD.is_file() else {}
    try:
        new = updated(current, scan(ASSETS))
    except ValueError as error:
        sys.exit(str(error))
    RECORD.write_text(json.dumps(new, indent=2, sort_keys=True) + "\n", encoding="utf-8")

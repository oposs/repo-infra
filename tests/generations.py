"""The text of every marked asset, recorded under its marker version.

A test fails when an asset's text changes and its marker version does not.
PR #43 reworded a comment in changelog.yml and kept v3, so two repositories
both at "v3" held different files. `make generations` records a new version
and refuses to change a recorded one.
"""

import hashlib
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "skills/repo-infra/scripts"))
from repo_infra.markers import parse_markers  # noqa: E402

ASSETS = pathlib.Path(__file__).resolve().parents[1] / "skills/repo-infra/assets"
RECORD = ASSETS / "generations.json"


def scan(assets_root):
    found = {}
    for path in sorted(pathlib.Path(assets_root).rglob("*")):
        if not path.is_file() or path.name == "generations.json":
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        markers = parse_markers(text)
        if markers:
            found[str(path.relative_to(assets_root))] = (
                markers[0].version, hashlib.sha256(text.encode("utf-8")).hexdigest())
    return found


def updated(record, scanned):
    record = {path: dict(versions) for path, versions in record.items()}
    for path, (version, digest) in scanned.items():
        known = record.setdefault(path, {}).get(str(version))
        if known is not None and known != digest:
            raise ValueError(f"{path}: v{version} is recorded with other text; "
                             "bump the marker")
        record[path][str(version)] = digest
    return record


if __name__ == "__main__":
    current = json.loads(RECORD.read_text(encoding="utf-8")) if RECORD.is_file() else {}
    try:
        new = updated(current, scan(ASSETS))
    except ValueError as error:
        sys.exit(str(error))
    RECORD.write_text(json.dumps(new, indent=2, sort_keys=True) + "\n", encoding="utf-8")

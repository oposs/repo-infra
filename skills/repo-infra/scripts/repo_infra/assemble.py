"""Turn the asset store into the files a repository installs.

ci.yml is the only assembled file: a frame, one job block per detected
ecosystem, and the ci-passed aggregator whose `needs:` list is the single piece
of generated content anywhere in the standard (D15). Everything else is copied
verbatim, because an asset is the literal file it installs.
"""

import pathlib
import re

from . import markers

NEEDS_PLACEHOLDER = "    needs: []"
_JOB_ID = re.compile(r"^  ([a-z][a-z0-9-]*):\s*$")


class AssemblyError(Exception):
    """An inconsistency in the asset store. Never recovered from silently."""


def _read(path):
    if not path.is_file():
        raise AssemblyError("missing asset file: %s" % path)
    return path.read_text(encoding="utf-8")


def block_job_ids(text):
    """The job ids a block declares -- the keys at two-space indent."""
    return [m.group(1) for m in (_JOB_ID.match(line) for line in text.splitlines()) if m]


def assemble_ci(assets_root, blocks, manifest):
    assets_root = pathlib.Path(assets_root)
    ci = assets_root / "ci"
    parts = [_read(ci / "ci-frame.yml").rstrip("\n")]
    needs = []

    for block in blocks:
        meta = manifest["ci_blocks"].get(block)
        if meta is None:
            raise AssemblyError("block %s is not declared in the manifest" % block)
        body = _read(ci / (block + ".yml"))
        parts.append("")
        parts.append(markers.marker_line(block, meta["version"], indent="  "))
        parts.append(body.rstrip("\n"))
        needs.extend(meta["jobs"])

    aggregator = _read(ci / "ci-aggregator.yml").rstrip("\n")
    if aggregator.count(NEEDS_PLACEHOLDER) != 1:
        raise AssemblyError(
            "ci-aggregator.yml must contain exactly one %r line to fill in" % NEEDS_PLACEHOLDER)
    aggregator = aggregator.replace(NEEDS_PLACEHOLDER, "    needs: [%s]" % ", ".join(needs))

    parts.append("")
    parts.append(aggregator)
    return "\n".join(parts) + "\n"


def render_all(assets_root, result, manifest):
    """Every file this repository should have, keyed by repo-relative path."""
    assets_root = pathlib.Path(assets_root)
    files = {}
    for name, spec in manifest["assets"].items():
        source = assets_root / spec["source"]
        if spec.get("kind") == "dir":
            if not source.is_dir():
                raise AssemblyError("asset %s: %s is not a directory" % (name, source))
            for child in sorted(source.iterdir()):
                if child.is_file():
                    files["%s/%s" % (spec["target"], child.name)] = _read(child)
        else:
            files[spec["target"]] = _read(source)
    files[".github/workflows/ci.yml"] = assemble_ci(assets_root, result.blocks, manifest)
    return files

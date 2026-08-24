"""Turn the asset store into the files a repository installs.

Two files are assembled rather than copied: ci.yml, from a frame, one job
block per detected ecosystem, and the ci-passed aggregator (D15); and
release-publish.yml, from a frame, one job block per installed publish
add-on, and the finalize job. Both follow the same shape -- a frame, zero or
more blocks each carrying its own marker, and a tail whose `needs:` list is
generated from the blocks actually present. Everything else is copied
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
        raise AssemblyError(f"missing asset file: {path}")
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
            raise AssemblyError(f"block {block} is not declared in the manifest")
        body = _read(ci / (block + ".yml"))
        parts.append("")
        parts.append(markers.marker_line(block, meta["version"], indent="  "))
        parts.append(body.rstrip("\n"))
        needs.extend(meta["jobs"])

    aggregator = _read(ci / "ci-aggregator.yml").rstrip("\n")
    if aggregator.count(NEEDS_PLACEHOLDER) != 1:
        raise AssemblyError(
            f"ci-aggregator.yml must contain exactly one {NEEDS_PLACEHOLDER!r} line to fill in")
    aggregator = aggregator.replace(NEEDS_PLACEHOLDER, "    needs: [{}]".format(", ".join(needs)))

    parts.append("")
    parts.append(aggregator)
    return "\n".join(parts) + "\n"


def assemble_publish(assets_root, addons, manifest):
    """release-publish.yml: the frame, the add-on blocks, then finalize.

    The second generated `needs:` list in the standard. `finalize` must wait for
    every add-on, or a release would go public before its artifacts were
    attached -- and the core must not name add-ons it does not ship, or it would
    depend on spec 2 to run at all.
    """
    assets_root = pathlib.Path(assets_root)
    publish = assets_root / "publish"
    parts = [_read(publish / "publish-frame.yml").rstrip("\n")]
    needs = ["publish"]

    for addon in addons:
        meta = manifest["publish_blocks"].get(addon)
        if meta is None:
            raise AssemblyError(f"publish add-on {addon} is not declared in the manifest")
        body = _read(publish / (addon + ".yml"))
        parts.append("")
        parts.append(markers.marker_line(addon, meta["version"], indent="  "))
        parts.append(body.rstrip("\n"))
        needs.extend(meta["jobs"])

    finalize = _read(publish / "publish-finalize.yml").rstrip("\n")
    if finalize.count(NEEDS_PLACEHOLDER) != 1:
        raise AssemblyError(
            f"publish-finalize.yml must contain exactly one {NEEDS_PLACEHOLDER!r} "
            "line to fill in")
    finalize = finalize.replace(
        NEEDS_PLACEHOLDER, "    needs: [{}]".format(", ".join(needs)))

    parts.append("")
    parts.append(finalize)
    return "\n".join(parts) + "\n"


def render_all(assets_root, result, manifest, publish=(), build=()):
    """Every file this repository should have, keyed by repo-relative path.

    `publish` and `build` are decisions the repository recorded, not things
    detection can see (D12, D16): whether it attaches a tarball, whether it
    builds in a container. An asset in `assets` ships to everyone; one in
    `publish_blocks` or `build_assets` ships only when named.
    """
    assets_root = pathlib.Path(assets_root)
    files = {}
    for name, spec in manifest["assets"].items():
        source = assets_root / spec["source"]
        if spec.get("kind") == "dir":
            if not source.is_dir():
                raise AssemblyError(f"asset {name}: {source} is not a directory")
            for child in sorted(source.iterdir()):
                if child.is_file():
                    files[f"{spec['target']}/{child.name}"] = _read(child)
        else:
            files[spec["target"]] = _read(source)

    for name in build:
        spec = manifest["build_assets"].get(name)
        if spec is None:
            raise AssemblyError(f"build asset {name} is not declared in the manifest")
        files[spec["target"]] = _read(assets_root / spec["source"])

    files[".github/workflows/ci.yml"] = assemble_ci(assets_root, result.blocks, manifest)
    files[".github/workflows/release-publish.yml"] = assemble_publish(
        assets_root, publish, manifest)
    return files

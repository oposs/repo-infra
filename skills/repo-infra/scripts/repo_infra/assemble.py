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
EXPECTED_PLACEHOLDER = "            const expected = [];"
_JOB_ID = re.compile(r"^  ([a-z][a-z0-9-]*):\s*$")

# An asset pattern is interpolated into a JavaScript string literal in the
# generated workflow, so it is validated rather than escaped: a quote or a
# backslash from a hand-written config would end the literal and turn a
# declaration into code. GitHub's own release asset names are this alphabet.
_ASSET_PATTERN = re.compile(r"^[A-Za-z0-9._+*~-]+$")


class AssemblyError(Exception):
    """An inconsistency in the asset store. Never recovered from silently."""


def _read(path):
    if not path.is_file():
        raise AssemblyError(f"missing asset file: {path}")
    return path.read_text(encoding="utf-8")


def block_job_ids(text):
    """The job ids a block declares -- the keys at two-space indent."""
    return [m.group(1) for m in (_JOB_ID.match(line) for line in text.splitlines()) if m]


def ci_addon_blocks(result, addons, manifest):
    """The opt-in CI blocks a repository named, checked against what it is (D22).

    A CI add-on is the first block a repository *chooses* rather than detection
    finding it -- `publish` and `build` already work this way (D12, D16),
    because whether a project ships a static Linux binary is a decision its
    files do not state. Two mistakes are cheap to make in a hand-written config
    and expensive to debug in a generated workflow, so neither is rendered:

    * naming a block whose ecosystem this repository does not have, which
      installs a job that cannot pass and blocks every pull request;
    * naming a block detection already installs, which emits the same job id
      twice -- invalid YAML, so *no* job in ci.yml runs and the required check
      never reports at all.

    An optional block that omits `requires` fits any ecosystem (D23): a man
    page is built the same way in a Rust, Perl or Go repository, so `ci-man`
    names none. The other refusals hold for it unchanged.
    """
    chosen = []
    for name in addons:
        meta = manifest["ci_blocks"].get(name)
        if meta is None:
            raise AssemblyError(f"ci add-on {name} is not declared in the manifest")
        if meta.get("seam"):
            raise AssemblyError(
                f"ci add-on {name} is a seam; set \"{meta['seam']}\": true in "
                ".github/repo-infra.json instead of naming it")
        if not meta.get("optional"):
            raise AssemblyError(
                f"ci add-on {name} is not an opt-in block; detection installs it")
        required = meta.get("requires")
        if required and required not in result.ecosystems:
            raise AssemblyError(
                f"ci add-on {name} requires the {required} ecosystem, "
                f"which this repository does not have")
        if name in result.blocks or name in chosen:
            raise AssemblyError(f"ci add-on {name} is already installed")
        chosen.append(name)
    return chosen


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


def _checked_patterns(where, patterns):
    for pattern in patterns:
        if not isinstance(pattern, str) or not _ASSET_PATTERN.match(pattern):
            raise AssemblyError(f"{where}: {pattern!r} is not an asset name pattern")
    return list(patterns)


def local_publish_jobs(local, generated):
    """A repository's own publish jobs, checked against the generated ones (A1).

    Some repositories run a publish job the standard does not ship -- smtp-proxy-rs
    builds a .deb and a container image, and there is no add-on for that pair yet
    (R32: prove it here, upstream it later). The job block itself is a local edit
    to the assembled file, which `apply` reports as a conflict and a human merges.
    Its entry in finalize's `needs:` was a local edit too, and that half does not
    survive: one line, silently reverted by the next `apply`, and the revert does
    not fail -- finalize simply stops waiting and publishes a release whose .deb
    does not exist yet.

    So the job id is declared instead of hand-edited, and this generates the line.
    Declaring a job the assembler already generates is refused: the repository
    would be claiming a job it does not own, and the next version of that add-on
    would then fight its local block.
    """
    jobs, assets = [], []
    for entry in local:
        name = entry.get("job")
        if not name:
            raise AssemblyError(f"publish_local entry must name a job: {entry!r}")
        if name in generated or name in jobs:
            raise AssemblyError(
                f"publish_local job {name} is already generated by the assembler; "
                "remove it from .github/repo-infra.json")
        jobs.append(name)
        assets.extend(_checked_patterns(f"publish_local {name}", entry.get("assets", [])))
    return jobs, assets


def assemble_publish(assets_root, addons, manifest, local=()):
    """release-publish.yml: the frame, the add-on blocks, then finalize.

    The second generated `needs:` list in the standard. `finalize` must wait for
    every add-on, or a release would go public before its artifacts were
    attached -- and the core must not name add-ons it does not ship, or it would
    depend on spec 2 to run at all.

    `needs:` alone is not the guarantee, though. It is ordering, and ordering
    cannot report its own absence. So finalize also gets the list of assets the
    installed blocks say they attach, and asserts them against the real release
    before publishing it. The two lists are generated side by side, from the
    same declarations, because a guard that disagrees with the ordering it
    guards is worse than no guard.
    """
    assets_root = pathlib.Path(assets_root)
    publish = assets_root / "publish"
    parts = [_read(publish / "publish-frame.yml").rstrip("\n")]
    needs = ["publish"]
    expected = []

    for addon in addons:
        meta = manifest["publish_blocks"].get(addon)
        if meta is None:
            raise AssemblyError(f"publish add-on {addon} is not declared in the manifest")
        body = _read(publish / (addon + ".yml"))
        parts.append("")
        parts.append(markers.marker_line(addon, meta["version"], indent="  "))
        parts.append(body.rstrip("\n"))
        needs.extend(meta["jobs"])
        expected.extend(_checked_patterns(addon, meta.get("assets", [])))

    local_jobs, local_assets = local_publish_jobs(local, needs)
    needs.extend(local_jobs)
    expected.extend(local_assets)

    finalize = _read(publish / "publish-finalize.yml").rstrip("\n")
    for placeholder in (NEEDS_PLACEHOLDER, EXPECTED_PLACEHOLDER):
        if finalize.count(placeholder) != 1:
            raise AssemblyError(
                f"publish-finalize.yml must contain exactly one {placeholder!r} "
                "line to fill in")
    finalize = finalize.replace(
        NEEDS_PLACEHOLDER, "    needs: [{}]".format(", ".join(needs)))
    finalize = finalize.replace(
        EXPECTED_PLACEHOLDER,
        "            const expected = [{}];".format(
            ", ".join(f"'{pattern}'" for pattern in expected)))

    parts.append("")
    parts.append(finalize)
    return "\n".join(parts) + "\n"


def render_all(assets_root, result, manifest, publish=(), build=(), ci=(),
               publish_local=(), ci_local=False):
    """Every file this repository should have, keyed by repo-relative path.

    `publish`, `build`, `ci` and `publish_local` are decisions the repository
    recorded, not things detection can see (D12, D16, D22): whether it attaches
    a tarball, whether it builds in a container, whether it ships a static
    binary, and which publish job of its own finalize must wait for. An asset
    in `assets` ships to everyone; one in `publish_blocks`, `build_assets` or
    an *optional* `ci_blocks` entry ships only when named.

    The add-on blocks land after the detected ones, so adding one never
    reorders the jobs a repository already has -- and they join the generated
    `needs:` list like any other block, which is what makes an add-on a
    required check rather than advisory.

    An optional block may carry build assets (`"build"` in its `ci_blocks`
    entry). Choosing the block installs them as if they had been named in
    `build`, so a repository cannot choose `ci-man` and forget the fragment
    its job runs.

    `ci_local` adds the `ci-local` seam after every other block (D25), so
    the project's own jobs join the generated `needs:` list.
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

    addons = ci_addon_blocks(result, ci, manifest)
    # A chosen block brings the build assets its job runs (D23): ci-man runs
    # `make man`, which is nothing without build/man.mk. Naming one of them in
    # `build` as well is allowed and installs it once.
    carried = [asset for name in addons
               for asset in manifest["ci_blocks"][name].get("build", [])]
    for name in dict.fromkeys([*build, *carried]):
        spec = manifest["build_assets"].get(name)
        if spec is None:
            raise AssemblyError(f"build asset {name} is not declared in the manifest")
        files[spec["target"]] = _read(assets_root / spec["source"])

    blocks = result.blocks + addons + (["ci-local"] if ci_local else [])
    files[".github/workflows/ci.yml"] = assemble_ci(assets_root, blocks, manifest)
    files[".github/workflows/release-publish.yml"] = assemble_publish(
        assets_root, publish, manifest, publish_local)
    return files

"""File-signal detection.

GitHub's own language field is not usable here: `oetiker/callbackery` reports
JavaScript and is a Perl application, `oetiker/skill-optimizer` reports Python
and is a Claude plugin. Detection is by file signal, always.

A repository routinely matches more than one ecosystem -- `oposs/wg-wrangler`
is perl and node, `oposs/mkp-builder` is python and claude-plugin -- which is
what forces one assembled ci.yml rather than one workflow per ecosystem (D2).
"""

import copy
import json
import pathlib
import tomllib
from dataclasses import dataclass, field


@dataclass
class DetectResult:
    ecosystems: list[str] = field(default_factory=list)
    blocks: list[str] = field(default_factory=list)
    version_files: list[dict] = field(default_factory=list)
    candidates: list[str] = field(default_factory=list)
    ambiguities: list[dict] = field(default_factory=list)


def _present(repo_root, signal):
    """A signal ending in `/` means a directory; anything else means a file."""
    target = pathlib.Path(repo_root) / signal.rstrip("/")
    return target.is_dir() if signal.endswith("/") else target.is_file()


def _matches(repo_root, signals):
    if not all(_present(repo_root, s) for s in signals.get("all", [])):
        return False
    any_of = signals.get("any", [])
    if any_of and not any(_present(repo_root, s) for s in any_of):
        return False
    if any(_present(repo_root, s) for s in signals.get("none", [])):
        return False
    return True


def _cargo_lock_entries(repo_root):
    """A version_files entry per crate whose version Cargo.lock records.

    The release PR rewrites files with regexes and commits exactly the
    version_files paths, so a Cargo.lock left out keeps the old version:
    mdmost v0.1.1 was tagged with Cargo.toml at 0.1.1 and Cargo.lock at
    0.1.0, and `cargo --locked` failed in the publish. The crate name is
    part of the pattern, which is why a fixed entry in detection.json cannot
    carry it. The root package counts, and every workspace member that
    takes its version from `[workspace.package]`; a member with a version of
    its own (a vendored crate) is not released with the repository.
    """
    root = pathlib.Path(repo_root)
    if not (root / "Cargo.lock").is_file():
        return []

    def read(path):
        try:
            return tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
            return None

    manifest = read(root / "Cargo.toml")
    if manifest is None:
        return []
    names = []
    if isinstance(manifest.get("package", {}).get("name"), str):
        names.append(manifest["package"]["name"])
    for member in manifest.get("workspace", {}).get("members", []):
        for directory in sorted(root.glob(member)):
            package = (read(directory / "Cargo.toml") or {}).get("package", {})
            version = package.get("version")
            if (isinstance(version, dict) and version.get("workspace") is True
                    and isinstance(package.get("name"), str)
                    and package["name"] not in names):
                names.append(package["name"])
    return [{
        "path": "Cargo.lock",
        "pattern": f'^name = "{name}"\nversion = "[^"]*"',
        "replacement": f'name = "{name}"\nversion = "$VERSION"',
        "verify": f'^name = "{name}"\nversion = "$VERSION"',
    } for name in names]


class Detection:
    def __init__(self, data):
        self.data = data

    @classmethod
    def load(cls, path):
        return cls(json.loads(pathlib.Path(path).read_text(encoding="utf-8")))

    def detect(self, repo_root):
        result = DetectResult()
        for entry in self.data["ecosystems"]:
            if not _matches(repo_root, entry["signals"]):
                continue
            result.ecosystems.append(entry["id"])
            result.version_files.extend(copy.deepcopy(entry.get("version_files", [])))
            if entry.get("cargo_lock"):
                result.version_files.extend(_cargo_lock_entries(repo_root))
        for entry in self.data.get("candidates", []):
            if _matches(repo_root, entry["signals"]):
                result.candidates.append(entry["id"])
        for entry in self.data.get("ambiguities", []):
            if _matches(repo_root, entry["signals"]):
                result.ambiguities.append(copy.deepcopy(entry))

        # Every converted repository gets the workflow library, so ci-lib is
        # unconditional. The rest are sorted so a re-run assembles a
        # byte-identical ci.yml -- the equality check in CI depends on it.
        blocks = {e["ci_block"] for e in self.data["ecosystems"] if e["id"] in result.ecosystems}
        result.blocks = ["ci-lib"] + sorted(blocks)
        result.ecosystems.sort()
        return result

    def open_candidates(self, candidates, chosen_ci):
        """The candidates a repository has not acted on yet (D23).

        A candidate is a hint that more of the standard fits this repository.
        Once the repository has chosen the CI block that answers it -- `ci-man`
        for `man-pages` -- the hint has been acted on, and repeating it on
        every `check` would read as advice still open. Detection cannot see
        the choice, so the caller passes the `ci` list in.
        """
        served = {entry["id"] for entry in self.data.get("candidates", [])
                  if entry.get("ci_block") in chosen_ci}
        return [c for c in candidates if c not in served]

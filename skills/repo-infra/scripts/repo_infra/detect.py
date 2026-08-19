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

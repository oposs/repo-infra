"""The differences between two trees of fixtures/nfpm/facts.sh output, one
unified diff per file. ri-release-nfpm's container test compares its packages
with mtuspy's cargo-deb baseline through it."""

import difflib
import pathlib


def facts_diff(baseline, actual):
    baseline, actual = pathlib.Path(baseline), pathlib.Path(actual)
    names = sorted({p.relative_to(root).as_posix()
                    for root in (baseline, actual) for p in root.rglob("*") if p.is_file()})
    lines = []
    for name in names:
        old = (baseline / name).read_text(encoding="utf-8").splitlines() \
            if (baseline / name).is_file() else []
        new = (actual / name).read_text(encoding="utf-8").splitlines() \
            if (actual / name).is_file() else []
        lines += difflib.unified_diff(old, new, f"baseline/{name}", f"nfpm/{name}", lineterm="")
    return "".join(line + "\n" for line in lines)

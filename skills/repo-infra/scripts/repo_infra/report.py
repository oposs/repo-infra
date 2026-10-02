"""The report: rows grouped by the part of the repository they are about."""

import json
import textwrap
from collections import namedtuple

# D30. One row of the report: which part of the repository it is about, the
# piece, file or setting, its state and what to do about it.
Item = namedtuple("Item", "section name state detail")
SECTIONS = ("pieces", "callers", "config", "administration")
# check's exit code and the report's count both read this, so they cannot
# disagree about what needs attention.
ATTENTION = ("missing", "outdated", "edited", "unknown", "problem", "conflict")

NAME_WIDTH = 22
STATE_WIDTH = 11


def _compute_name_width(items):
    """Compute the name column width to fit the longest item name with at least
    one space before the state column."""
    if not items:
        return NAME_WIDTH
    max_name_len = max(len(item.name) for item in items)
    # Ensure at least one space after the longest name
    return max(NAME_WIDTH, max_name_len + 1)


def _row(item, name_width, indent):
    head = f"  {item.name:<{name_width}}{item.state:<{STATE_WIDTH}}"
    if not item.detail:
        return [head.rstrip()]
    wrapped = textwrap.wrap(item.detail, width=78 - len(indent))
    return [head + wrapped[0]] + [indent + line for line in wrapped[1:]]


def render_text(repo, items):
    lines = [f"repo-infra check: {repo}", ""]
    name_width = _compute_name_width(items)
    indent = " " * (2 + name_width + STATE_WIDTH)
    for section in SECTIONS:
        rows = [item for item in items if item.section == section]
        if not rows:
            continue
        lines.append(section)
        for item in rows:
            lines.extend(_row(item, name_width, indent))
        lines.append("")
    count = sum(1 for item in items if item.state in ATTENTION)
    if count:
        noun, verb = ("item", "needs") if count == 1 else ("items", "need")
        lines.append(f"{count} {noun} {verb} attention.")
    else:
        lines.append("Up to date with the standard; nothing to do.")
    return "\n".join(lines) + "\n"


def render_json(repo, items):
    return json.dumps({"repo": repo, "items": [item._asdict() for item in items]}, indent=2)

"""The report.

`conflict` is the state that earns its keep. Everything else means "install a
file". A conflict means adopting an item breaks something that already works,
so it is spelled out at length rather than abbreviated to a status word.
"""

import json
import textwrap

from .state import NEEDS_ATTENTION_STATES

NAME_WIDTH = 22
STATE_WIDTH = 11
INDENT = " " * (2 + NAME_WIDTH + STATE_WIDTH)


def _row(item):
    head = f"  {item.name:<{NAME_WIDTH}}{item.state:<{STATE_WIDTH}}"
    if not item.detail:
        return [head.rstrip()]
    wrapped = textwrap.wrap(item.detail, width=78 - len(INDENT))
    return [head + wrapped[0]] + [INDENT + line for line in wrapped[1:]]


def render_text(repo, result, items):
    lines = [f"repo-infra check — {repo}", ""]
    lines.append(f"detected   {' · '.join(result.ecosystems) or 'nothing'}")
    lines.append("")
    for item in items:
        lines.extend(_row(item))
    lines.append("")

    # Ambiguities already appear above as `ambiguous` item rows (one per
    # question, via state.classify_ambiguities) with the question as their
    # detail -- a second "? question" block here would just repeat them.

    if result.candidates:
        lines.append("  candidates (later specs)")
        lines.append("  " + "  ".join(result.candidates))
        lines.append("")

    count = sum(1 for item in items if item.state in NEEDS_ATTENTION_STATES)
    if count:
        noun = "item" if count == 1 else "items"
        verb = "needs" if count == 1 else "need"
        lines.append(f"{count} {noun} {verb} attention.  /repo-infra:apply")
    else:
        lines.append("Up to date with the standard — nothing to do.")
    return "\n".join(lines) + "\n"


def render_json(repo, result, items):
    return json.dumps({
        "repo": repo,
        "ecosystems": result.ecosystems,
        "candidates": result.candidates,
        "ambiguities": result.ambiguities,
        "items": [{"name": i.name, "state": i.state, "detail": i.detail} for i in items],
    }, indent=2)

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

    # No ecosystem matched, so no CI block can be selected and the file items
    # below are conclusions drawn from a repository kind we do not have. Saying
    # "N items need attention" here reads as a broken repository; the true
    # statement is that the standard has never met this shape. Teaching it comes
    # first, and `apply` is not the next step.
    # An unresolved ambiguity means detection is incomplete, not that the shape
    # is unrecognised. Once the operator answers the question, an ecosystem may
    # yet match. Printing "does not recognise" here would be a false statement.
    # The test `test_an_unresolved_ambiguity_keeps_the_count_honest` encodes this.
    has_ambiguous = any(item.state == "ambiguous" for item in items)
    if not result.ecosystems and not has_ambiguous:
        lines.append("the standard does not recognise this repository.")
        lines.append("")
        lines.append("Teach it first: see the repo-infra skill. Running apply now")
        lines.append("would install the repository-wide items and no CI at all.")
        return "\n".join(lines) + "\n"

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

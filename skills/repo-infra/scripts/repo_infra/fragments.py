"""Changelog fragments (D40): the pure rules.

The JS in .github/workflows/lib/fragments.js enforces the same rules when a pull
request is judged and a release rolled; change both. tests/fixtures/
changelog-fragments/cases.json holds the cases both sides must agree on.
"""

import posixpath
import re

SECTIONS = ("new", "changed", "fixed")
NOTE_RE = re.compile(r"^Changelog fragments: `([^`]+?)/?`")
NAME_RE = re.compile(r"^[0-9]{8}-[0-9]{4}-[0-9a-f]{4}-[a-z0-9]+(-[a-z0-9]+)*\.md$")
_NEWLINE = re.compile(r"\r?\n")


def lines_of(text):
    return _NEWLINE.split(text)


def header_end(lines):
    """Index of the first '## ' line; a note below it belongs to a release entry."""
    return next((i for i, line in enumerate(lines) if line.startswith("## ")), len(lines))


def _refused_dir(raw, directory):
    if raw.startswith("/"):
        return "is absolute"
    if ".." in raw.split("/"):
        return "contains '..'"
    if directory == ".":
        return "is the repository root"
    if directory == ".github" or directory.startswith(".github/"):
        return "is or lies under '.github'"
    if directory == "CHANGES.md":
        return "is 'CHANGES.md'"
    return None


def note_dir(text):
    """The directory the note in the header of CHANGES.md names, or None.

    Normalised, so './CHANGES.d/' and 'CHANGES.d//' read as 'CHANGES.d', the way
    GitHub names the files. Raises ValueError for a directory the rules refuse.
    """
    lines = lines_of(text)
    for line in lines[:header_end(lines)]:
        match = NOTE_RE.match(line)
        if not match:
            continue
        raw = match.group(1)
        directory = posixpath.normpath(raw)
        reason = _refused_dir(raw, directory)
        if reason:
            raise ValueError(f"Changelog fragments directory '{raw}' {reason}")
        return directory
    return None


def classify_path(directory, path):
    """('outside' | 'root' | 'fragment' | 'refused', detail) for a path in the repository."""
    if not path.startswith(f"{directory}/"):
        return ("outside", None)
    parts = path[len(directory) + 1:].split("/")
    if len(parts) == 1:
        return ("root", None)
    if parts[0] not in SECTIONS:
        return ("refused", f"'{parts[0]}' is not one of new, changed, fixed")
    if len(parts) > 2:
        return ("refused", f"'{path}' is in a subdirectory of {directory}/{parts[0]}/")
    if not NAME_RE.match(parts[1]):
        return ("refused",
                f"'{parts[1]}' does not match <yyyymmdd>-<hhmm>-<4 hex>-<topic>.md")
    return ("fragment", parts[0])


def _parse(text):
    """(problem, entries): entries are '- ' lines plus two-space continuation lines."""
    out = []
    for line in lines_of(text):
        if line.strip() == "":
            continue
        if line.startswith("- "):
            if line[2:].strip() == "":
                return (f"an entry without text: '{line}'", [])
            out.append([line])
        elif line.startswith("  ") and out:
            out[-1].append(line)
        elif line.startswith("#"):
            return (f"a line starts with '#': {line}", [])
        else:
            return (f"text outside an entry: {line}", [])
    if not out:
        return ('no entry (a line starting with "- ")', [])
    return (None, ["\n".join(entry) for entry in out])


def fragment_problem(text):
    return _parse(text)[0]


def entries(text):
    return _parse(text)[1]

"""Version markers.

Every file repo-infra installs carries a marker naming the asset and the
generation of that asset. A file assembled from several assets carries one
marker per block (spec D11).

The marker records *which generation this is* and nothing else. A content hash
would be wrong here: every repository legitimately edits its workflows -- the
project name, the matrix targets, an extra publish job -- so a hash would report
drift on every repository forever.

The stamp (D29) is a different thing from a content hash for drift: it only
answers whether a file is byte for byte what apply wrote, so apply may overwrite
it. check never reads it.
"""

import hashlib
import re
from collections import namedtuple

Marker = namedtuple("Marker", "asset version line")

# Asset identifiers: start with alphanumeric, then alphanumeric or hyphen.
# This pattern is the single source of truth. Task 2 (manifest.json validation)
# and later modules must validate against exactly this.
ASSET_ID = r"[a-z0-9][a-z0-9-]*"

# `#` for YAML and make, `//` for the JavaScript workflow library, `dnl` for m4,
# `--` for the Lua filter the man page build runs (D23). Trailing prose after
# the version is allowed so a marker can carry "do not delete this line".
_MARKER = re.compile(
    r"^\s*(?:#|//|--|dnl\b)\s*repo-infra:\s+(" + ASSET_ID + r")\s+v(\d+)(?:\s.*)?$")


def parse_markers(text):
    """Return every marker in `text`, in file order. `line` is 1-based."""
    found = []
    for number, line in enumerate(text.splitlines(), start=1):
        match = _MARKER.match(line)
        if match:
            found.append(Marker(asset=match.group(1), version=int(match.group(2)), line=number))
    return found


def marker_line(asset, version, indent="", comment="#"):
    """Render the marker for `asset` at `version`."""
    return f"{indent}{comment} repo-infra: {asset} v{version:d}"


# D29. Appended to the file's first marker line by apply, and nothing else.
_STAMP = re.compile(r" sha256=([0-9a-f]{16})$")


def _digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _first_marker(lines):
    return next((i for i, line in enumerate(lines) if _MARKER.match(line)), None)


def strip_stamp(text):
    """`text` without the stamp on its first marker line, if it has one."""
    lines = text.split("\n")
    first = _first_marker(lines)
    if first is not None:
        lines[first] = _STAMP.sub("", lines[first])
    return "\n".join(lines)


def stamp(text):
    """`text` with its first marker line stamped with the digest of the rest."""
    bare = strip_stamp(text)
    lines = bare.split("\n")
    first = _first_marker(lines)
    if first is None:
        raise ValueError("no repo-infra marker to stamp")
    lines[first] = f"{lines[first]} sha256={_digest(bare)}"
    return "\n".join(lines)


def pristine(text):
    """True when the stamp matches the text, False when the text changed
    since it was stamped, None when there is no stamp to judge by."""
    lines = text.split("\n")
    first = _first_marker(lines)
    if first is None:
        return None
    found = _STAMP.search(lines[first])
    if found is None:
        return None
    return found.group(1) == _digest(strip_stamp(text))

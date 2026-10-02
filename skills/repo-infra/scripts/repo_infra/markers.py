"""Version markers.

Every piece carries `repo-infra: <piece> vN` on its first comment line (D30).
The marker says which piece and which version a file claims to be; whether
the file is that version is decided by its bytes against generations.json,
in check.py. A marker that names no piece is how check finds a file of the
assembled standard that still needs converting.
"""

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

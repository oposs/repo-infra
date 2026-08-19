"""Version markers.

Every file repo-infra installs carries a marker naming the asset and the
generation of that asset. A file assembled from several assets carries one
marker per block (spec D11).

The marker records *which generation this is* and nothing else. A content hash
would be wrong here: every repository legitimately edits its workflows -- the
project name, the matrix targets, an extra publish job -- so a hash would report
drift on every repository forever.
"""

import re
from collections import namedtuple

Marker = namedtuple("Marker", "asset version line")

# Asset identifiers: start with alphanumeric, then alphanumeric or hyphen.
# This pattern is the single source of truth — Task 2 (manifest.json validation)
# and later modules must validate against exactly this.
ASSET_ID = r"[a-z0-9][a-z0-9-]*"

# `#` for YAML, `//` for the JavaScript workflow library. Trailing prose after
# the version is allowed so a marker can carry "do not delete this line".
_MARKER = re.compile(r"^\s*(?:#|//)\s*repo-infra:\s+(" + ASSET_ID + r")\s+v(\d+)(?:\s.*)?$")


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

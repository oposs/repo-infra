"""Also runnable as `python3 path/to/scripts/repo_infra check|apply` -- the
form every skill and command in this plugin uses, via `${CLAUDE_PLUGIN_ROOT}`,
because that path is known without anyone having set PYTHONPATH first.

Executing a package directory this way (`python3 <dir>`) puts only that
directory on sys.path, not its parent, so a plain `from .cli import main`
fails at import time with "attempted relative import with no known parent
package" -- before running a single line of `main()`. Putting `scripts/` (this
file's grandparent) on sys.path first is what makes `repo_infra` importable as
a package either way; `python3 -m repo_infra`, cli.py's own docstring's form,
still works unchanged because PYTHONPATH or an already-importable package
short-circuits this insert.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from repo_infra.cli import main  # noqa: E402

sys.exit(main())

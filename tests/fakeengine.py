"""A stand-in for podman and docker, so the fast suite never starts a container.

install_fake writes the script as both `podman` and `docker` into a directory
the test puts first on PATH. The script appends one JSON line per call to the
file named by FAKE_ENGINE_LOG; calls() reads that file back.

Behaviour is steered by environment variables:

- FAKE_BUILD_FAIL_PULL=1: `build` fails when it carries a `--pull*` argument.
- FAKE_PODMAN_INFO: what `info` prints (default `false crun`).
- FAKE_VOLUME=1: `volume inspect` succeeds, otherwise it fails.
- FAKE_RUN_STATUS: the exit status of `run` (default 0).
- FAKE_EXEC=1: `run` emulates the container (added with the wrapper).
"""

import json
import pathlib
import stat
import sys

SCRIPT = '''\
#!{python}
import json
import os
import sys

argv = sys.argv[1:]
sub = argv[0] if argv else ""
entry = {{"engine": os.path.basename(sys.argv[0]), "argv": argv, "stdin": None}}
if sub == "build":
    entry["stdin"] = sys.stdin.read()
log = os.environ.get("FAKE_ENGINE_LOG")
if log:
    with open(log, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\\n")

if sub == "build":
    pulling = any(a.startswith("--pull") for a in argv)
    sys.exit(1 if os.environ.get("FAKE_BUILD_FAIL_PULL") == "1" and pulling else 0)
if sub == "info":
    print(os.environ.get("FAKE_PODMAN_INFO", "false crun"))
    sys.exit(0)
if sub == "volume" and argv[1:2] == ["inspect"]:
    sys.exit(0 if os.environ.get("FAKE_VOLUME") == "1" else 1)
if sub == "run":
    sys.exit(int(os.environ.get("FAKE_RUN_STATUS", "0")))
sys.exit(0)
'''


def install_fake(bin_dir: pathlib.Path) -> None:
    """Write executable `podman` and `docker` into bin_dir.

    The shebang names the interpreter by absolute path: the PATH a test gives
    make holds no python3 for `#!/usr/bin/env python3` to find.
    """
    bin_dir.mkdir(parents=True, exist_ok=True)
    for name in ("podman", "docker"):
        path = bin_dir / name
        path.write_text(SCRIPT.format(python=sys.executable), encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def calls(log: pathlib.Path) -> list[dict]:
    """The engine calls recorded in log, oldest first; empty when none."""
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]

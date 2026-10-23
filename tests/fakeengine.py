"""A stand-in for podman and docker, so the fast suite never starts a container.

install_fake writes the script as both `podman` and `docker` into a directory
the test puts first on PATH. The script appends one JSON line per call to the
file named by FAKE_ENGINE_LOG; calls() reads that file back.

Behaviour is steered by environment variables:

- FAKE_BUILD_FAIL_PULL=1: `build` fails when it carries a `--pull*` argument.
- FAKE_PODMAN_INFO: what `info` prints (default `false crun`).
- FAKE_PODMAN_INFO_FAIL=1: `info` exits 1.
- FAKE_VOLUME=1: `volume inspect` succeeds, otherwise it fails.
- FAKE_RUN_STATUS: the exit status of `run` (default 0).
- FAKE_EXEC=1: `run` emulates the container: the `-v host:/src` mount maps
  /src to the host directory, the working directory is the `-w` path below it,
  the environment is the `-e` pairs plus PATH and HOME, and the command after
  the image tag runs for real. /etc/gitconfig in the script becomes
  $FAKE_ETC/gitconfig. FAKE_HOME names HOME.
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
    if os.environ.get("FAKE_PODMAN_INFO_FAIL") == "1":
        sys.exit(1)
    print(os.environ.get("FAKE_PODMAN_INFO", "false crun"))
    sys.exit(0)
if sub == "volume" and argv[1:2] == ["inspect"]:
    sys.exit(0 if os.environ.get("FAKE_VOLUME") == "1" else 1)
if sub == "run" and os.environ.get("FAKE_EXEC") == "1":
    import subprocess
    takes_value = {{"-v", "-e", "-w", "--security-opt", "--device", "--group-add"}}
    mounts, env, cwd, i = [], {{}}, "/src", 1
    while argv[i].startswith("-"):
        flag = argv[i]
        if flag in takes_value:
            value = argv[i + 1]
            i += 2
            if flag == "-v":
                mounts.append(value.split(":", 1))
            elif flag == "-e":
                name, eq, val = value.partition("=")
                env[name] = val if eq else os.environ.get(name, "")
            elif flag == "-w":
                cwd = value
        else:
            i += 1
    command = argv[i + 1:]
    top = next(host for host, ctr in mounts if ctr == "/src")
    etc = os.environ.get("FAKE_ETC", "/nonexistent") + "/gitconfig"
    command = [a.replace("/etc/gitconfig", etc) if a != "/src" else top
               for a in command]
    env["PATH"] = os.environ["PATH"]
    env["HOME"] = os.environ.get("FAKE_HOME", "/nonexistent")
    if cwd == "/src" or cwd.startswith("/src/"):
        cwd = top + cwd[4:]
    sys.exit(subprocess.run(command, cwd=cwd, env=env).returncode)
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

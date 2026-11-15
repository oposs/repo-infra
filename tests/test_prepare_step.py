"""The preparation step (D39): what it runs, and which pieces carry it.

A tree with `configure.ac` has no Makefile until `./bootstrap` and
`./configure` have run, and a project may name another preparation in the
`prepare` key of .github/repo-infra.json. The step's requirement is
behavioural, so its own shell runs here against fixture trees, with `sudo`
and `apt-get` replaced by stand-ins.
"""

import os
import pathlib
import stat
import subprocess

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github/workflows"
MAN_PIECE = WORKFLOWS / "ri-ci-man.yml"
STEP_NAME = "Prepare the tree (D39)"
TOOLCHAIN = "install -y autoconf automake gettext podman"

# A stand-in for ./bootstrap or ./configure: it records its own name in `log`,
# in the directory it was started from.
STUB = '#!/bin/sh\necho "$(basename "$0")" >> log\n'
AUTOTOOLS = {"configure.ac": "AC_INIT\n", "bootstrap": STUB, "configure": STUB}


def _jobs(workflow_path):
    return yaml.safe_load(workflow_path.read_text(encoding="utf-8"))["jobs"]


def prepare_step(workflow_path):
    """The `run:` script of the preparation step in a piece."""
    for job in _jobs(workflow_path).values():
        for step in job.get("steps", ()):
            if step.get("name") == STEP_NAME:
                return step["run"]
    raise AssertionError("%s has no step named %r" % (workflow_path.name, STEP_NAME))


def run_prepare(tmp_path, script, files, directory="."):
    """Run the step's script in a tree holding `files` ({path: text}).

    A file whose text starts with `#!` is made executable. `sudo` runs its
    arguments; `apt-get` records them in tmp_path/apt.log.
    """
    root = tmp_path / "tree"
    root.mkdir()
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        if text.startswith("#!"):
            path.chmod(path.stat().st_mode | stat.S_IEXEC)
    stubs = tmp_path / "bin"
    stubs.mkdir()
    for name, body in (("sudo", 'exec "$@"\n'),
                       ("apt-get", 'echo "$@" >> "%s"\n' % (tmp_path / "apt.log"))):
        stub = stubs / name
        stub.write_text("#!/bin/sh\n" + body, encoding="utf-8")
        stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    env = dict(os.environ, PATH="%s:%s" % (stubs, os.environ["PATH"]),
               DIRECTORY=directory)
    done = subprocess.run(["bash", "-e", "-c", script], cwd=root, env=env,
                          capture_output=True, text=True, timeout=60)
    done.root = root
    done.apt = ((tmp_path / "apt.log").read_text(encoding="utf-8")
                if (tmp_path / "apt.log").exists() else "")
    return done


def _config(prepare):
    import json
    return {".github/repo-infra.json": json.dumps({"prepare": prepare})}


def test_no_configure_ac_and_no_prepare_does_nothing(tmp_path):
    done = run_prepare(tmp_path, prepare_step(MAN_PIECE), {"Makefile": "man:\n"})
    assert done.returncode == 0, done.stderr
    assert done.apt == ""
    assert sorted(p.name for p in done.root.iterdir()) == ["Makefile"]


def test_configure_ac_runs_toolchain_then_bootstrap_and_configure(tmp_path):
    done = run_prepare(tmp_path, prepare_step(MAN_PIECE), AUTOTOOLS)
    assert done.returncode == 0, done.stderr
    assert (done.root / "log").read_text(encoding="utf-8") == "bootstrap\nconfigure\n"
    assert TOOLCHAIN in done.apt.splitlines()


def test_prepare_key_runs_instead_of_the_default(tmp_path):
    done = run_prepare(tmp_path, prepare_step(MAN_PIECE),
                       {**AUTOTOOLS, **_config("echo custom > out")})
    assert done.returncode == 0, done.stderr
    assert (done.root / "out").read_text(encoding="utf-8") == "custom\n"
    assert not (done.root / "log").exists()
    assert TOOLCHAIN in done.apt.splitlines()


def test_prepare_key_runs_without_configure_ac(tmp_path):
    done = run_prepare(tmp_path, prepare_step(MAN_PIECE), _config("echo custom > out"))
    assert done.returncode == 0, done.stderr
    assert (done.root / "out").read_text(encoding="utf-8") == "custom\n"
    assert done.apt == ""


def test_a_failing_prepare_fails_the_step(tmp_path):
    done = run_prepare(tmp_path, prepare_step(MAN_PIECE), _config("false; touch reached"))
    assert done.returncode != 0
    assert not (done.root / "reached").exists()


def test_a_failing_bootstrap_fails_the_step(tmp_path):
    files = {**AUTOTOOLS, "bootstrap": "#!/bin/sh\nexit 3\n"}
    done = run_prepare(tmp_path, prepare_step(MAN_PIECE), files)
    assert done.returncode != 0
    assert not (done.root / "log").exists()


def test_missing_config_file_counts_as_no_prepare(tmp_path):
    done = run_prepare(tmp_path, prepare_step(MAN_PIECE), AUTOTOOLS)
    assert not (done.root / ".github").exists()
    assert done.returncode == 0, done.stderr
    assert (done.root / "log").read_text(encoding="utf-8") == "bootstrap\nconfigure\n"


def test_a_config_file_without_the_key_counts_as_no_prepare(tmp_path):
    files = {**AUTOTOOLS, ".github/repo-infra.json": '{"exceptions": []}'}
    done = run_prepare(tmp_path, prepare_step(MAN_PIECE), files)
    assert done.returncode == 0, done.stderr
    assert (done.root / "log").read_text(encoding="utf-8") == "bootstrap\nconfigure\n"


def test_a_blank_prepare_counts_as_unset(tmp_path):
    # `check` reports the value; the step must not run nothing and call it done
    # on a tree that needs the autotools default.
    done = run_prepare(tmp_path, prepare_step(MAN_PIECE), {**AUTOTOOLS, **_config("  ")})
    assert done.returncode == 0, done.stderr
    assert (done.root / "log").read_text(encoding="utf-8") == "bootstrap\nconfigure\n"


def test_a_prepare_that_is_no_string_fails_the_step(tmp_path):
    done = run_prepare(tmp_path, prepare_step(MAN_PIECE), {**AUTOTOOLS, **_config(["a"])})
    assert done.returncode != 0
    assert "prepare" in done.stderr
    assert not (done.root / "log").exists()


def test_the_step_runs_in_directory(tmp_path):
    files = {"sub/" + name: text for name, text in AUTOTOOLS.items()}
    done = run_prepare(tmp_path, prepare_step(MAN_PIECE), files, directory="sub")
    assert done.returncode == 0, done.stderr
    assert (done.root / "sub/log").read_text(encoding="utf-8") == "bootstrap\nconfigure\n"
    assert sorted(p.name for p in done.root.iterdir()) == ["sub"]


def test_the_prepare_key_is_read_at_the_root_and_run_in_directory(tmp_path):
    files = {"sub/Makefile": "man:\n", **_config("pwd > where")}
    done = run_prepare(tmp_path, prepare_step(MAN_PIECE), files, directory="sub")
    assert done.returncode == 0, done.stderr
    assert (done.root / "sub/where").read_text(encoding="utf-8").strip().endswith("/sub")


def test_the_step_comes_before_make_man():
    steps = _jobs(MAN_PIECE)["man"]["steps"]
    prepare = next(i for i, s in enumerate(steps) if s.get("name") == STEP_NAME)
    make = next(i for i, s in enumerate(steps) if "make man" in s.get("run", ""))
    assert prepare < make

# Container Self-Test (D19) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make repo-infra's own CI run the container-driver assets it ships against a real container on a real runner, as a required check.

**Architecture:** A new detected ecosystem `repo-infra`, keyed on the presence of
repo-infra's own `manifest.json`, carries one CI block. Because `ci-passed`'s
`needs:` list is generated from the blocks in `ci.yml`, that makes the job
required without touching `REQUIRED_CONTEXTS` or the ruleset asset. The job runs
a pytest test that is marked `container` and deselected by default, so the
sub-second local gate is unchanged.

**Tech Stack:** Python 3 (pytest), autoconf/automake, GNU make, podman, GitHub Actions YAML.

**Spec:** `docs/superpowers/specs/2026-08-24-container-selftest-design.md`

## Global Constraints

- **Assets are literal files. No substitution tokens.** No `{{`, no `@PACKAGE@`,
  no install-time rewriting (D15).
- **No mechanism for declaring system packages to CI** (D16), in any shape.
- **`make test`, never `make check`,** is the autotools test contract.
- **The fixed host toolchain string is exactly `autoconf automake gettext podman`.**
  `tests/test_blocks.py::test_the_autotools_block_installs_only_the_fixed_host_toolchain`
  pins it for `ci-perl-autotools`; Task 2 pins the new block equal to it.
- **`### New`, never `### Added`.** `CHANGES.md` is newest-first within a
  section; new bullets go at the **top**.
- **repo-infra gets no exemption from its own standard.** Its `.github/` is the
  assembler's output and `tests/test_self_render.py` fails if they diverge.
- **Never remove `if: always()` from `ci-passed`; never rename a required job;
  never add `paths`/`paths-ignore` to a required workflow.**
- Asset ids must match `ASSET_ID = r"[a-z0-9][a-z0-9-]*"` (`markers.py`).
- Gates, both from the repo root:
  - `python3 -m pytest -q tests` — **232 passing** at the start of this plan, and
    it must stay sub-second and must not require podman.
  - `uvx ruff check .` — must print `All checks passed!`. This is what CI runs and
    it covers the repo root. `make lint` fails locally because `ruff` is not
    importable from the sandboxed python here; that is expected and not a defect.
- Work on branch `spec/teach-and-build-containers`, continuing the D18 work. **Do
  not push, do not open a PR, do not merge** — the integration decision is the
  user's and is still open.
- This machine is shared. Never run `make -j` above 4. Pass `timeout: 600000` on
  any Bash call that builds a container, and never end a turn with a build still
  running.

## Task order — every task ends green

The block asset comes before the ecosystem that references it, deliberately.
`tests/test_blocks.py` checks the direction *ecosystem → manifest*, so a manifest
block that no ecosystem points at yet is valid; the reverse is not. And the
ecosystem task is what changes the rendered `.github/`, so it re-renders in the
same commit rather than leaving the tree inconsistent.

The marker and the self-test also land before the ecosystem, so that the moment
the job appears in CI there are container-marked tests for it to select. Between
those points a `pytest -m container` run would select nothing, which CI would
treat as a failure — harmless here because nothing is pushed, but the ordering
removes the window entirely.

## There is no render-to-disk command

`repo_infra.cli` has only `check` (never writes) and `apply` (writes on a
branch). To re-render repo-infra's own `.github/` in place, run this from the
repo root:

```bash
python3 - <<'PY'
import json, pathlib, sys
sys.path.insert(0, "skills/repo-infra/scripts")
from repo_infra.assemble import render_all
from repo_infra.detect import Detection
ROOT = pathlib.Path(".")
ASSETS = ROOT / "skills/repo-infra/assets"
manifest = json.loads((ASSETS / "manifest.json").read_text(encoding="utf-8"))
result = Detection.load(ASSETS / "detection.json").detect(ROOT)
for path, text in sorted(render_all(ASSETS, result, manifest).items()):
    p = ROOT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    print("wrote", path)
PY
```

Use it only where a task says to. Never hand-edit a file under `.github/`.

---

### Task 1: The CI block

**Files:**
- Create: `skills/repo-infra/assets/ci/ci-repo-infra-selftest.yml`
- Modify: `skills/repo-infra/assets/manifest.json` (`ci_blocks`)
- Test: `tests/test_blocks.py`

**Interfaces:**
- Consumes: nothing. This task comes first on purpose: `tests/test_blocks.py`
  asserts every *ecosystem's* block is in the manifest, not the reverse, so a
  manifest block nothing references yet is valid and the suite stays green.
- Produces: the CI block asset `ci-repo-infra-selftest` at version 1, declaring
  exactly one job id **`repo-infra-selftest`**. It invokes
  `python3 -m pytest -m container -v tests`, which Task 2 makes meaningful and
  Task 3 makes non-empty. Task 4 adds the ecosystem that installs this block.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_blocks.py`:

```python
def test_the_selftest_block_declares_exactly_its_one_job():
    from repo_infra.assemble import block_job_ids
    text = (ASSETS / "ci/ci-repo-infra-selftest.yml").read_text(encoding="utf-8")
    assert block_job_ids(text) == MANIFEST["ci_blocks"]["ci-repo-infra-selftest"]["jobs"]
    assert block_job_ids(text) == ["repo-infra-selftest"]


def test_the_selftest_block_runs_only_the_container_marked_tests():
    # The marker is what keeps the ordinary pytest job sub-second. A selftest
    # job that ran the whole suite would duplicate it and hide its own cost.
    text = (ASSETS / "ci/ci-repo-infra-selftest.yml").read_text(encoding="utf-8")
    assert "-m container" in text


def test_both_blocks_install_a_byte_identical_host_toolchain():
    # D19: podman on an Ubuntu runner is the link the self-test exists to
    # exercise. If the two blocks drift, the self-test keeps passing against a
    # toolchain the autotools block no longer ships -- green and worthless.
    line = "sudo apt-get install -y autoconf automake gettext podman"
    for name in ("ci/ci-perl-autotools.yml", "ci/ci-repo-infra-selftest.yml"):
        assert line in (ASSETS / name).read_text(encoding="utf-8"), name
```

Reuse the file's existing `ASSETS` and `MANIFEST` bindings.

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest tests/test_blocks.py -q`
Expected: FAIL — `FileNotFoundError` and `KeyError: 'ci-repo-infra-selftest'`.

- [ ] **Step 3: Write the block**

Create `skills/repo-infra/assets/ci/ci-repo-infra-selftest.yml`. A CI block is a
job fragment, indented two spaces, with no `name:`/`on:` header — the assembler
supplies the frame and injects the version marker. Read
`skills/repo-infra/assets/ci/ci-python.yml` first and match its shape exactly.

```yaml
  repo-infra-selftest:
    name: Container self-test
    runs-on: ubuntu-latest
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@v7

      # The same fixed host toolchain `ci-perl-autotools` installs, and
      # deliberately the same string (D19). Podman on an Ubuntu runner is the
      # one link nothing else exercises, and this is the line that carries it.
      # A test pins the two blocks equal so they cannot drift apart silently.
      - name: Install the autotools host toolchain
        run: |
          sudo apt-get update
          sudo apt-get install -y autoconf automake gettext podman

      # Only the container-marked tests. The ordinary `pytest` job already ran
      # everything else in under a second, and it did not need podman to do it.
      - run: python3 -m pytest -m container -v tests
```

- [ ] **Step 4: Declare it in the manifest**

Add to `ci_blocks` in `skills/repo-infra/assets/manifest.json`:

```json
    "ci-repo-infra-selftest": {"version": 1, "jobs": ["repo-infra-selftest"]}
```

- [ ] **Step 5: Run the whole suite**

Run: `python3 -m pytest -q tests`
Expected: **PASS** — all green. No ecosystem references this block yet, and
nothing requires one to. `.github/` is unchanged because the assembler only
installs blocks a detected ecosystem asks for.

If anything is red, report it rather than working around it: a red suite here
means the direction of the manifest check is not what this plan assumed.

- [ ] **Step 6: Commit**

```bash
git add skills/repo-infra/assets/ci/ci-repo-infra-selftest.yml \
        skills/repo-infra/assets/manifest.json tests/test_blocks.py
git commit -m "Add the container self-test CI block"
```

---

---

### Task 2: The `container` marker

**Files:**
- Modify: `pytest.ini`
- Test: `tests/test_markers_config.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces: a registered pytest marker named `container`, **deselected by
  default** via `addopts`. Task 3's test carries `@pytest.mark.container`, and
  Task 1's CI job selects it with `-m container`.

The whole point is that `python3 -m pytest -q tests` stays sub-second and needs no
podman, while `python3 -m pytest -m container` opts in.

- [ ] **Step 1: Write the failing test**

Create `tests/test_markers_config.py`:

```python
import configparser
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _pytest_ini():
    parser = configparser.ConfigParser()
    parser.read(ROOT / "pytest.ini")
    return parser["pytest"]


def test_the_container_marker_is_registered():
    # An unregistered marker is a warning today and an error under
    # --strict-markers; either way a typo would silently deselect nothing.
    assert "container" in _pytest_ini().get("markers", "")


def test_container_tests_are_deselected_by_default():
    # D19: the ordinary gate must stay sub-second and must not need podman.
    # A developer with no container engine runs the suite unaffected.
    assert 'not container' in _pytest_ini().get("addopts", "")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 -m pytest tests/test_markers_config.py -q`
Expected: FAIL — `pytest.ini` has neither `markers` nor `addopts`.

- [ ] **Step 3: Configure the marker**

Rewrite `pytest.ini`:

```ini
[pytest]
testpaths = tests
pythonpath = skills/repo-infra/scripts
markers =
    container: exercises the shipped assets against a real container; needs podman and takes minutes (D19)
addopts = -m "not container"
```

- [ ] **Step 4: Verify both selections behave**

Run: `python3 -m pytest -q tests`
Expected: PASS, and still sub-second. The count grows by the two tests above.

Run: `python3 -m pytest -m container -q tests`
Expected: everything deselected — no tests carry the marker yet. Confirm this
does not exit non-zero in a way that would fail CI; if pytest exits 5 ("no tests
ran"), **say so in your report**, because Task 1's CI job would fail on an empty
selection and Task 3 is what makes it non-empty.

- [ ] **Step 5: Commit**

```bash
git add pytest.ini tests/test_markers_config.py
git commit -m "Register a container marker, deselected by default"
```

---

---

### Task 3: The fixture and the self-test

**Files:**
- Create: `tests/fixtures/autotools-driver/configure.ac`
- Create: `tests/fixtures/autotools-driver/Makefile.am`
- Create: `tests/fixtures/autotools-driver/Containerfile`
- Create: `tests/fixtures/autotools-driver/t/basic.t`
- Create: `tests/test_container_selftest.py`

**Interfaces:**
- Consumes: the `container` marker from Task 2; the shipped assets
  `skills/repo-infra/assets/m4/repo-infra-container.m4` and
  `skills/repo-infra/assets/build/container.mk`.
- Produces: at least one test carrying `@pytest.mark.container`, so Task 1's CI
  job selects something.

**The fixture is a fixture, not an asset.** No version marker, absent from
`manifest.json`, not drift-checked. It lives under `tests/`, so
`test_every_non_yaml_asset_is_covered_by_a_test` (which walks `assets/`) is
unaffected.

- [ ] **Step 1: Write the fixture**

`tests/fixtures/autotools-driver/configure.ac`:

```
AC_INIT([selftest], [0.1])
AC_CONFIG_MACRO_DIRS([m4])
AM_INIT_AUTOMAKE([foreign])
REPO_INFRA_CONTAINER
AS_IF([test "x$enable_container" = xno], [
  AC_CHECK_PROG([PERL], [perl], [perl])
  AS_IF([test -z "$PERL"], [AC_MSG_ERROR([perl is required])])
])
AC_CONFIG_FILES([Makefile])
AC_OUTPUT
```

`tests/fixtures/autotools-driver/Makefile.am` — note there is **deliberately no
`TEST_EXTENSIONS`**, and say so in the file:

```
# No TEST_EXTENSIONS on purpose (D19). Without it automake emits literal
# per-test rules (t/basic.t.log: t/basic.t) instead of a permissive `.t.log:`
# suffix rule. The strict shape is the only one that catches a TESTS= override
# whose path does not match -- the D18 bug where test-dev passed an absolute
# /src/... path and silently ran nothing.
ACLOCAL_AMFLAGS = -I m4
TESTS = t/basic.t
EXTRA_DIST = t/basic.t Containerfile
TEST_DEV_MOUNTS = t
if !CONTAINER_DRIVER
test: check
endif
include $(top_srcdir)/build/container.mk
```

`tests/fixtures/autotools-driver/t/basic.t` (mode 0755):

```sh
#!/bin/sh
# Automake's default driver judges a test by its EXIT STATUS, not by TAP text.
# The self-test proves the live mount by replacing this with `exit 1`.
echo "1..1"
echo "ok 1"
```

`tests/fixtures/autotools-driver/Containerfile`, digest-pinned:

```
FROM docker.io/library/alpine@sha256:a4f4213abb84c497377b8544c81b3564f313746700372ec4fe84653e4fb03805
RUN apk add --no-cache autoconf automake make perl
COPY . /src
WORKDIR /src
RUN autoreconf -i && ./configure --disable-container --prefix=/opt/selftest \
 && make && make install
```

The digest pins `alpine:3.20`. A floating tag would make a required check fail
for upstream reasons.

- [ ] **Step 2: Write the self-test**

Create `tests/test_container_selftest.py`. The image build is the expensive step,
so build once per session and share it — use a **session-scoped fixture** that
copies the fixture plus the two shipped assets into a tmp path, runs
`autoreconf -i`, and yields the prepared directory.

```python
import pathlib
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSETS = ROOT / "skills/repo-infra/assets"
FIXTURE = ROOT / "tests/fixtures/autotools-driver"

pytestmark = pytest.mark.container


def run(args, cwd, check=True, timeout=900):
    """Run a command and return the CompletedProcess, output captured."""
    return subprocess.run(args, cwd=cwd, check=check, timeout=timeout,
                          capture_output=True, text=True)


@pytest.fixture(scope="session")
def tree(tmp_path_factory):
    """The fixture project with the shipped assets installed, bootstrapped."""
    work = tmp_path_factory.mktemp("autotools-driver")
    shutil.copytree(FIXTURE, work, dirs_exist_ok=True)
    (work / "m4").mkdir()
    (work / "build").mkdir()
    shutil.copy(ASSETS / "m4/repo-infra-container.m4", work / "m4")
    shutil.copy(ASSETS / "build/container.mk", work / "build")
    done = run(["autoreconf", "-i"], work)
    # D18's contract guards the project's own `test:` with `if !CONTAINER_DRIVER`
    # precisely so automake does not warn about a duplicate definition.
    assert "warning" not in done.stderr.lower(), done.stderr
    return work


def test_native_mode_runs_the_real_suite_and_defines_no_driver_targets(tree):
    run(["./configure", "--disable-container"], tree)
    done = run(["make", "test"], tree)
    assert "# TOTAL: 1" in done.stdout and "# PASS:  1" in done.stdout
    for target in ("container", "test-dev"):
        missing = run(["make", target], tree, check=False)
        assert missing.returncode != 0, "%s exists in native mode" % target
        assert "No rule to make target" in missing.stderr


def test_driver_mode_builds_the_image_and_tests_inside_it(tree):
    run(["./configure"], tree)
    done = run(["make", "test"], tree)
    assert "# TOTAL: 1" in done.stdout and "# PASS:  1" in done.stdout


def test_dist_leaves_a_tarball_on_the_host(tree):
    run(["./configure"], tree)
    run(["make", "dist"], tree)
    tarballs = sorted(tree.glob("*.tar.gz"))
    assert len(tarballs) == 1, tarballs


def test_test_dev_runs_the_live_working_tree(tree):
    """Proven by exit status, never by TAP text.

    Automake's default driver judges a test by its exit status, so a script
    printing `not ok 1` while exiting 0 reports PASS and proves nothing. Make
    the host copy fail and require test-dev to fail with it.
    """
    run(["./configure"], tree)
    test_file = tree / "t/basic.t"
    original = test_file.read_text(encoding="utf-8")
    test_file.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    try:
        failed = run(["make", "test-dev", "TARGET=t/basic.t"], tree, check=False)
        assert failed.returncode != 0, "test-dev passed against a failing host copy"
    finally:
        test_file.write_text(original, encoding="utf-8")
        test_file.chmod(0o755)
    passed = run(["make", "test-dev", "TARGET=t/basic.t"], tree)
    assert "# PASS:  1" in passed.stdout


def test_the_refusals_abort_make(tree):
    run(["./configure"], tree)
    no_target = run(["make", "test-dev"], tree, check=False)
    assert no_target.returncode != 0
    assert "TARGET is required" in no_target.stdout + no_target.stderr

    no_destdir = run(["make", "install"], tree, check=False)
    assert no_destdir.returncode != 0
    assert "DESTDIR is required" in no_destdir.stdout + no_destdir.stderr
```

- [ ] **Step 3: Run the container tests**

Run: `python3 -m pytest -m container -v tests`
Expected: PASS. The first test builds the image, so allow several minutes. Pass
`timeout: 600000` on the Bash call and **do not end your turn while it runs** —
poll until it exits.

If a test fails, read the failure before changing anything. A genuine defect in
`container.mk` or the m4 macro is a real finding: **report it, do not weaken the
test to get green.** That is the entire purpose of this task.

- [ ] **Step 4: Confirm the ordinary gate is untouched**

Run: `time python3 -m pytest -q tests`
Expected: PASS, still sub-second, and no podman invoked. Paste the timing.

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/autotools-driver tests/test_container_selftest.py
git commit -m "Exercise the container driver against a real container"
```

---

---

### Task 4: The `repo-infra` ecosystem, and the render that makes it required

**Files:**
- Modify: `skills/repo-infra/assets/detection.json`
- Modify: `tests/test_self_render.py:20` (the ecosystems assertion)
- Test: `tests/test_detect.py`

**Interfaces:**
- Consumes: the block `ci-repo-infra-selftest` (Task 1), the `container` marker
  (Task 2) and the container-marked tests (Task 3). All three must be in place
  before this task, or the job this installs would select nothing.
- Produces: the ecosystem id `repo-infra`, signal
  `skills/repo-infra/assets/manifest.json`, and the re-rendered `.github/` that
  makes the job required.

**This is the task that makes the self-test required**, so it re-renders
`.github/` in the same commit. Adding the ecosystem without re-rendering leaves
`tests/test_self_render.py` failing and the repository inconsistent.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_detect.py`:

```python
def test_the_real_file_detects_a_repository_that_ships_repo_infras_assets():
    # D19: "this repository ships repo-infra's own assets" is a real,
    # file-detectable property. Exactly one repository has it, by the settled
    # four-repo split -- and any repository that vendored those assets would
    # want the self-test too.
    result = Detection.load(REAL).detect(HERE / "fixtures/repo-selfhost")
    assert "repo-infra" in result.ecosystems
    assert "ci-repo-infra-selftest" in result.blocks


def test_an_ordinary_repository_does_not_get_the_selftest():
    # The signal must be the manifest itself, not merely a `skills/` directory.
    result = Detection.load(REAL).detect(HERE / "fixtures/repo-claude-plugin")
    assert "repo-infra" not in result.ecosystems
    assert "ci-repo-infra-selftest" not in result.blocks
```

Read the top of `tests/test_detect.py` and reuse its existing `REAL` and `HERE`
bindings rather than redefining them.

- [ ] **Step 2: Create the detection fixture**

```bash
mkdir -p tests/fixtures/repo-selfhost/skills/repo-infra/assets
echo '{}' > tests/fixtures/repo-selfhost/skills/repo-infra/assets/manifest.json
```

A fixture repository only needs the signal file to exist; detection reads paths,
not contents. Check how the sibling fixtures under `tests/fixtures/repo-*` are
built and match their minimalism.

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_detect.py -q`
Expected: the first new test FAILS — `repo-infra` is not in `result.ecosystems`.
The second already passes, which is correct: it is a guard against a signal that
is too loose, and it must keep passing after Step 4.

- [ ] **Step 4: Add the ecosystem**

Append to the `ecosystems` list in `skills/repo-infra/assets/detection.json`.
**Append at the end** — detection preserves file order and that order decides job
order in the rendered `ci.yml`, so appending keeps the diff to one added job:

```json
    {
      "id": "repo-infra",
      "signals": {
        "all": [
          "skills/repo-infra/assets/manifest.json"
        ]
      },
      "ci_block": "ci-repo-infra-selftest"
    }
```

No `version_files` key. That is an established shape — `go`, `checkmk-plugin` and
`perl-mkpl` all have none — and correct here: repo-infra's version comes from its
`claude-plugin` and `python` ecosystems.

- [ ] **Step 5: Update the self-render ecosystems assertion**

`tests/test_self_render.py` asserts the real repository's ecosystem list. Change
it and say why in a comment:

```python
    # D19: repo-infra ships its own assets, so it detects its own self-test
    # ecosystem. This list changing is the proof the wiring is real.
    assert result.ecosystems == ["claude-plugin", "python", "repo-infra"]
```

If the actual order differs, use the order detection produces — do not sort it to
match this plan. Report what you found.

- [ ] **Step 6: Run the detect tests**

Run: `python3 -m pytest tests/test_detect.py -q`
Expected: PASS.

Then: `python3 -m pytest tests/test_self_render.py -q`
Expected: **FAIL** — the committed `.github/` does not yet contain the new job.
Step 7 fixes that; do not hand-edit anything under `.github/` to make it pass.

- [ ] **Step 7: Re-render `.github/`**

Run the snippet from **"There is no render-to-disk command"** at the top of this
plan, from the repo root. It rewrites every assembler-owned file in place.

- [ ] **Step 8: Read the diff before trusting it**

```bash
git diff .github/
```

Expected, and nothing else:
- a new `repo-infra-selftest` job in `.github/workflows/ci.yml`
- `repo-infra-selftest` added to `ci-passed`'s generated `needs:` list
- a `# repo-infra: ci-repo-infra-selftest v1` marker for the new block

**`ci-passed` gaining the new job is what makes this required** — it is the
single required context, so no ruleset change is needed. Confirm `if: always()`
is still on `ci-passed`; without it a failed dependency makes that job *skip*,
and a skipped job reports success, so the required check would go green on a red
build. If the diff shows anything beyond the three items above, stop and report.

- [ ] **Step 9: Run both gates**

```bash
python3 -m pytest -q tests
uvx ruff check .
```

Expected: PASS and `All checks passed!`. Derive the count with `--collect-only`;
do not state a number and explain a difference in prose.

- [ ] **Step 10: Commit**

```bash
git add skills/repo-infra/assets/detection.json tests/test_detect.py \
        tests/test_self_render.py tests/fixtures/repo-selfhost .github
git commit -m "Make the container self-test a required check"
```

---

---

### Task 5: Changelog

**Files:**
- Modify: `CHANGES.md`

**Interfaces:**
- Consumes: everything above.
- Produces: nothing.

- [ ] **Step 1: Read the top of the file**

```bash
head -30 CHANGES.md
```

Match its existing style exactly — heading levels, bullet punctuation, whether
entries end in a period, wrap width. The section heading is `### New`, never
`### Added`, and new bullets go at the **top** of the section.

- [ ] **Step 2: Add the entry**

At the top of the unreleased `### New` section:

```markdown
- repo-infra's own CI builds a real container and runs the autotools driver it
  ships against it, as a required check. The assets are the product, so a
  regression in them no longer merges.
```

- [ ] **Step 3: Run both gates**

```bash
python3 -m pytest -q tests
uvx ruff check .
```

Expected: PASS and `All checks passed!`, with the count unchanged — this task
adds no tests.

- [ ] **Step 4: Commit**

```bash
git add CHANGES.md
git commit -m "Note the container self-test in the changelog"
```

---

## What this plan does not do

- **It does not test the documented contract.** D19 decides this deliberately:
  `conventions.md` is a prompt for Claude, whose conversions target varied
  repositories, so a fixture asserting "the document says enough" would only
  prove it for one shape. A gap in the written contract is caught by a human
  converting a repository, and the remedy is the teach path.
- **It does not push, open a PR, or merge.** The branch is local-only and the
  integration decision is the user's.
- **It does not prove the job works on a GitHub runner.** Everything here runs
  locally with podman. The first real exercise of `ubuntu-latest` + `apt-get
  install podman` is this branch's own pull request — which is the whole reason
  the job exists.
- **It does not add a second fixture shape.** The strict, `TEST_EXTENSIONS`-less
  shape subsumes the permissive one for every property asserted.

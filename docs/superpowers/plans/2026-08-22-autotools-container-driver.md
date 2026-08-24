# Autotools Container Driver (D18) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make an autotools tree serve two roles — a podman driver outside the container, plain autotools inside — so a CI runner never probes a project's system dependencies.

**Architecture:** A new m4 asset ships `REPO_INFRA_CONTAINER`, which adds
`--disable-container` (default: drive the container) and an automake conditional.
A rewritten build fragment defines the driver targets under that conditional, so
the same file is inert inside the container. The CI blocks need no command
changes: plain `./configure` is now driver mode.

**Tech Stack:** Python 3 (pytest), autoconf/automake m4, GNU make, podman, GitHub Actions YAML.

**Spec:** `docs/superpowers/specs/2026-08-22-autotools-container-driver-design.md`

## Global Constraints

- **Assets are literal files. No substitution tokens.** No `{{`, no `@PACKAGE@`,
  no install-time rewriting. Parameterization is by make variable or configure
  flag at run time (D15).
- **`make test`, never `make check`,** is the autotools test contract.
- **No mechanism for declaring system packages to CI** (D16). Do not add one in
  any shape — not a file, not a manifest key, not a setup script.
- **The host toolchain list is fixed and shared:** `autoconf automake gettext
  podman`. `tests/test_blocks.py::test_the_autotools_block_installs_only_the_fixed_host_toolchain`
  pins that exact string.
- **`### New`, never `### Added`.** `CHANGES.md` is newest-first within a
  section; new bullets go at the **top**.
- **repo-infra gets no exemption from its own standard.** `.github/` is the
  assembler's output and a test fails if they diverge.
- **`ruff` is not importable from the sandboxed python here.** Use
  `uvx ruff check .`; `make lint` fails locally for that reason and is fine in CI.
- Run the suite with `python3 -m pytest -q tests` from the repo root. It is
  **207 passing** at the start of this plan.
- Work on branch `spec/teach-and-build-containers`. Do not push, do not open a
  PR, do not merge — the integration decision is the user's and is still open.

---

### Task 1: Spike — what automake actually allows

**Throwaway.** Its deliverable is an answer, not code. Nothing from the scratch
tree is kept. It gates Task 4, and Task 4 must not start before it lands.

**Files:**
- Create: `/scratch/oetiker/claude-tmp/d18-spike/` (throwaway, outside the repo)
- Create: `.superpowers/sdd/2026-08-22-autotools-container-driver/spike-findings.md`

**Interfaces:**
- Consumes: nothing
- Produces: a written answer to Q1 and Q2 below, in `spike-findings.md`, in the
  form Task 4 reads: `Q1: A` or `Q1: B` or `Q1: neither`, and `Q2: yes` or `Q2: no`.

- [ ] **Step 1: Confirm the toolchain is present**

```bash
autoconf --version | head -1
automake --version | head -1
```

If either is missing, stop and report — do not install anything system-wide.

- [ ] **Step 2: Build a minimal autotools tree**

```bash
mkdir -p /scratch/oetiker/claude-tmp/d18-spike && cd /scratch/oetiker/claude-tmp/d18-spike
cat > configure.ac <<'EOF'
AC_INIT([spike], [0.1])
AM_INIT_AUTOMAKE([foreign])
AC_ARG_ENABLE([container], [], [], [enable_container=yes])
AM_CONDITIONAL([CONTAINER_DRIVER], [test "x$enable_container" = xyes])
AC_CONFIG_FILES([Makefile])
AC_OUTPUT
EOF
mkdir -p build t
cat > t/one.t <<'EOF'
#!/bin/sh
echo "1..1"; echo "ok 1"
EOF
cat > t/two.t <<'EOF'
#!/bin/sh
echo "1..1"; echo "ok 1"
EOF
chmod +x t/one.t t/two.t
```

- [ ] **Step 3: Q1 — can an included fragment replace `dist` under a conditional?**

Write the fragment and a `Makefile.am` that includes it:

```bash
cat > build/driver.mk <<'EOF'
if CONTAINER_DRIVER
dist:
	@echo "DRIVER-DIST-RAN"
endif
EOF
cat > Makefile.am <<'EOF'
TESTS = t/one.t t/two.t
TEST_EXTENSIONS = .t
test: check
include $(top_srcdir)/build/driver.mk
EOF
autoreconf -fi >/dev/null 2>&1
./configure >/dev/null && make dist 2>&1 | tail -20
```

Record which happened:

- **A** — `DRIVER-DIST-RAN` printed and automake's own dist did not run.
  Note whether `automake` emitted a `overriding recipe`/`warning: ... overrides`
  message and what exactly it said.
- **B** — automake refused, or its own `dist` ran instead. Then repeat with
  `AUTOMAKE_OPTIONS = -Wno-override` added to `Makefile.am` and record whether
  that changes the answer.
- **neither** — something else. Write down exactly what.

Then confirm the conditional is really off in native mode:

```bash
./configure --disable-container >/dev/null && make dist 2>&1 | tail -5
```

Expected: no `DRIVER-DIST-RAN`, and a real `spike-0.1.tar.gz`.

- [ ] **Step 4: Q2 — does `TESTS=` on the command line override `Makefile.am`?**

```bash
./configure --disable-container >/dev/null
make test 2>&1 | grep -c 'PASS\|ok'          # both tests
make test TESTS=t/one.t 2>&1 | tail -20      # should run ONE
```

Record `Q2: yes` if the second run executed only `t/one.t`, `Q2: no` otherwise.
If `no`, also record what automake did instead — Task 4 needs to know whether the
variable was ignored or the run failed.

- [ ] **Step 5: Write the findings**

```bash
mkdir -p /home/oetiker/checkouts/repo-infra/.superpowers/sdd/2026-08-22-autotools-container-driver
```

Write `spike-findings.md` with, at minimum: the `Q1:` line, the `Q2:` line, the
exact automake warning text if any, and the commands that produced each answer.
Paste real terminal output, not a summary of it.

- [ ] **Step 6: Report and stop**

The findings are git-ignored (the `.superpowers/` workspace is). Report both
answers to the user before Task 2 begins. **If `Q1: neither`, stop the plan and
bring the finding back** — do not invent a third shape.

---

### Task 2: Teach the marker parser `dnl`

**Files:**
- Modify: `skills/repo-infra/scripts/repo_infra/markers.py:27` (the `_MARKER` regex)
- Test: `tests/test_markers.py`

**Interfaces:**
- Consumes: nothing
- Produces: `parse_markers(text)` recognises `dnl repo-infra: <asset> vN`;
  `marker_line(asset, version, indent="", comment="dnl")` renders it. Task 3
  relies on both.

An m4 file's comment is `dnl`, which discards the line rather than copying it
into the generated `configure`. `#` would work too, but it survives into
`configure` as shell noise. The manifest already has a `comment` field for
exactly this; only the parser is missing.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_markers.py`:

```python
def test_dnl_is_a_marker_comment():
    # m4 assets comment with `dnl`, which discards the line instead of copying
    # it into the generated configure.
    found = parse_markers("dnl repo-infra: container-m4 v1\nAC_DEFUN([X], [])\n")
    assert [(m.asset, m.version, m.line) for m in found] == [("container-m4", 1, 1)]


def test_dnl_needs_a_word_boundary():
    # `dnlrepo-infra:` is not a comment in any language.
    assert parse_markers("dnlrepo-infra: container-m4 v1\n") == []


def test_marker_line_renders_the_dnl_comment():
    assert marker_line("container-m4", 1, comment="dnl") == "dnl repo-infra: container-m4 v1"
```

Make sure the import at the top of the file includes `marker_line`:

```python
from repo_infra.markers import marker_line, parse_markers
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest tests/test_markers.py -q`
Expected: FAIL — the two `dnl` parse tests return `[]`.

- [ ] **Step 3: Extend the regex**

In `skills/repo-infra/scripts/repo_infra/markers.py`, replace the `_MARKER`
definition and its comment:

```python
# `#` for YAML and make, `//` for the JavaScript workflow library, `dnl` for m4.
# Trailing prose after the version is allowed so a marker can carry
# "do not delete this line".
_MARKER = re.compile(
    r"^\s*(?:#|//|dnl\b)\s*repo-infra:\s+(" + ASSET_ID + r")\s+v(\d+)(?:\s.*)?$")
```

`marker_line` already takes `comment` and needs no change.

- [ ] **Step 4: Run the whole suite**

Run: `python3 -m pytest -q tests`
Expected: PASS, 210 passed.

If the count is not 210, do not explain the difference — derive it. Collect ids
before and after and diff them.

- [ ] **Step 5: Commit**

```bash
git add skills/repo-infra/scripts/repo_infra/markers.py tests/test_markers.py
git commit -m "Recognise dnl as a marker comment"
```

---

### Task 3: The mode switch — `assets/m4/repo-infra-container.m4`

**Files:**
- Create: `skills/repo-infra/assets/m4/repo-infra-container.m4`
- Create: `tests/test_container_m4.py`
- Modify: `skills/repo-infra/assets/manifest.json` (`build_assets`)
- Modify: `tests/test_blocks.py` (`test_every_non_yaml_asset_is_covered_by_a_test`)

**Interfaces:**
- Consumes: `parse_markers` accepting `dnl` (Task 2)
- Produces: the build asset id `container-m4`, target `m4/repo-infra-container.m4`;
  the m4 macro `REPO_INFRA_CONTAINER`; the automake conditional **`CONTAINER_DRIVER`**;
  the shell variable `enable_container` (`yes` = driver, `no` = native). Task 4's
  fragment keys off `CONTAINER_DRIVER`.

**The conditional is named `CONTAINER_DRIVER`, not `REPO_INFRA_CONTAINER`.**
Giving the `AC_DEFUN` macro and the `AM_CONDITIONAL` the same name puts one
identifier in two namespaces that autoconf and automake each process, and there
is no benefit to justify finding out how that resolves.

- [ ] **Step 1: Write the failing test**

Create `tests/test_container_m4.py`:

```python
import json
import pathlib

from repo_infra.markers import parse_markers

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSETS = ROOT / "skills/repo-infra/assets"
MANIFEST = json.loads((ASSETS / "manifest.json").read_text(encoding="utf-8"))
MACRO = ASSETS / "m4/repo-infra-container.m4"


def test_the_macro_is_declared_in_the_manifest():
    spec = MANIFEST["build_assets"]["container-m4"]
    assert spec["source"] == "m4/repo-infra-container.m4"
    assert spec["target"] == "m4/repo-infra-container.m4"
    assert spec["comment"] == "dnl"


def test_the_macro_carries_its_marker_at_the_declared_version():
    version = MANIFEST["build_assets"]["container-m4"]["version"]
    text = MACRO.read_text(encoding="utf-8")
    assert ("container-m4", version) in [(m.asset, m.version) for m in parse_markers(text)]


def test_the_flag_defaults_to_driving_the_container():
    # D18: the default is the caller you do not control. A stranger with a
    # checkout types ./configure and must not be asked for librrd.
    text = MACRO.read_text(encoding="utf-8")
    assert "AC_ARG_ENABLE([container]" in text
    assert "enable_container=yes" in text
    assert "--disable-container" in text
    # The flag names the semantics, not the location.
    assert "in-container" not in text


def test_driver_mode_probes_only_the_engine_and_the_containerfile():
    text = MACRO.read_text(encoding="utf-8")
    assert "AC_CHECK_PROGS([DOCKER], [podman docker])" in text
    assert "Containerfile" in text


def test_the_error_message_names_the_way_out():
    # A missing engine must not read as "this repository is broken".
    text = MACRO.read_text(encoding="utf-8")
    for message in text.split("AC_MSG_ERROR")[1:]:
        assert "--disable-container" in message.split("])")[0]


def test_it_exports_the_conditional_the_fragment_keys_off():
    text = MACRO.read_text(encoding="utf-8")
    assert "AM_CONDITIONAL([CONTAINER_DRIVER]" in text
    # Not the same identifier as the macro itself.
    assert "AM_CONDITIONAL([REPO_INFRA_CONTAINER]" not in text


def test_a_repository_that_did_not_ask_for_it_does_not_get_it():
    # D16: containerization is a decision, not a detection. Both halves of the
    # pair are selected the same way and neither ships unasked.
    import pathlib as _p

    from repo_infra.assemble import render_all
    from repo_infra.detect import Detection
    result = Detection.load(ASSETS / "detection.json").detect(_p.Path(ROOT))
    assert "m4/repo-infra-container.m4" not in render_all(ASSETS, result, MANIFEST)
    assert "m4/repo-infra-container.m4" in render_all(
        ASSETS, result, MANIFEST, build=["container-m4"])


def test_the_macro_has_no_substitution_tokens():
    # D15: an asset is the literal file it installs.
    text = MACRO.read_text(encoding="utf-8")
    for token in ("$VERSION", "{{", "@PACKAGE@"):
        assert token not in text
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 -m pytest tests/test_container_m4.py -q`
Expected: FAIL — `KeyError: 'container-m4'` and `FileNotFoundError`.

- [ ] **Step 3: Write the macro**

Create `skills/repo-infra/assets/m4/repo-infra-container.m4`:

```m4
dnl repo-infra: container-m4 v1
dnl
dnl The container-driver mode switch (D18).
dnl
dnl repo-infra owns this file. The project owns its Containerfile and what goes
dnl in it. Call this from configure.ac, then wrap the project's own dependency
dnl checks so they never run on a host that is only driving the container:
dnl
dnl     REPO_INFRA_CONTAINER
dnl     AS_IF([test "x$enable_container" = xno], [
dnl       dnl librrd, RRDs, everything real -- probed here and nowhere else
dnl     ])
dnl
dnl The default is the role you do not control: someone clones the repository
dnl and types ./configure && make, and it works on a machine holding none of
dnl the project's dependencies, because the container carries them.
dnl
dnl --disable-container names the semantics, not a location: it means "do the
dnl real build in this tree". The Containerfile passes it, and so does a distro
dnl packager on a bare build host, who wants the same behaviour and is not in a
dnl container.

AC_DEFUN([REPO_INFRA_CONTAINER], [
  AC_ARG_ENABLE([container],
    [AS_HELP_STRING([--disable-container],
       [build in this tree instead of driving a container])],
    [], [enable_container=yes])

  AS_IF([test "x$enable_container" = xyes], [
    AC_CHECK_PROGS([DOCKER], [podman docker])
    AS_IF([test -z "$DOCKER"],
      [AC_MSG_ERROR([no container engine found. Install podman, or pass --disable-container to build in this tree.])])
    AS_IF([test -f "$srcdir/Containerfile"], [],
      [AC_MSG_ERROR([no Containerfile in $srcdir. Write one, or pass --disable-container to build in this tree.])])
  ])

  AM_CONDITIONAL([CONTAINER_DRIVER], [test "x$enable_container" = xyes])
])
```

- [ ] **Step 4: Declare it in the manifest**

In `skills/repo-infra/assets/manifest.json`, add to `build_assets` (keep
`container-test` for now; Task 4 replaces it):

```json
    "container-m4": {
      "version": 1,
      "source": "m4/repo-infra-container.m4",
      "target": "m4/repo-infra-container.m4",
      "comment": "dnl"
    }
```

- [ ] **Step 5: Update the new-asset-kind tripwire**

`tests/test_blocks.py::test_every_non_yaml_asset_is_covered_by_a_test` asserts
the set of non-YAML suffixes is exactly `{".mk"}`, and it is now failing on
purpose. Widen it and say why:

```python
def test_every_non_yaml_asset_is_covered_by_a_test():
    # every_asset_file() only walks YAML. Anything else under assets/ needs its
    # own test file, or it ships unchecked.
    #   .mk -> tests/test_build_assets.py
    #   .m4 -> tests/test_container_m4.py
    others = {p.suffix for p in ASSETS.rglob("*") if p.is_file()} - {".yml", ".yaml", ".json", ".js"}
    assert others == {".mk", ".m4"}, "a new asset kind arrived with no test: %s" % others
```

- [ ] **Step 6: Run the suite**

Run: `python3 -m pytest -q tests`
Expected: PASS, 218 passed.

- [ ] **Step 7: Commit**

```bash
git add skills/repo-infra/assets/m4/repo-infra-container.m4 \
        skills/repo-infra/assets/manifest.json \
        tests/test_container_m4.py tests/test_blocks.py
git commit -m "Ship the container-driver mode switch as an m4 asset"
```

---

### Task 4: The driver — `assets/build/container.mk`

**Files:**
- Create: `skills/repo-infra/assets/build/container.mk`
- Delete: `skills/repo-infra/assets/build/container-test.mk`
- Modify: `skills/repo-infra/assets/manifest.json` (`build_assets`: drop `container-test`, add `container`)
- Modify: `tests/test_build_assets.py` (rewritten)

**Interfaces:**
- Consumes: the automake conditional `CONTAINER_DRIVER` and the substituted
  `DOCKER` from Task 3.
- Produces: the build asset id `container`, target `build/container.mk`,
  defining `container`, `container-base`, `test`, `test-dev`, and the driver's
  `dist` and `install`. Consumed by the docs in Task 5.

**Read `spike-findings.md` from Task 1 first.** Q1 decides which listing in
Step 3 you write; Q2 decides one line in `test-dev`.

- [ ] **Step 1: Write the failing tests**

Replace the whole of `tests/test_build_assets.py`:

```python
import json
import pathlib

from repo_infra.markers import parse_markers

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSETS = ROOT / "skills/repo-infra/assets"
MANIFEST = json.loads((ASSETS / "manifest.json").read_text(encoding="utf-8"))
FRAGMENT = ASSETS / "build/container.mk"


def test_the_fragment_is_declared_in_the_manifest():
    spec = MANIFEST["build_assets"]["container"]
    assert spec["source"] == "build/container.mk"
    assert spec["target"] == "build/container.mk"
    assert spec["comment"] == "#"


def test_the_old_test_only_fragment_is_gone():
    # D18 replaced it. Leaving both would ship two answers to one question.
    assert "container-test" not in MANIFEST["build_assets"]
    assert not (ASSETS / "build/container-test.mk").exists()


def test_the_fragment_carries_its_marker_at_the_declared_version():
    text = FRAGMENT.read_text(encoding="utf-8")
    version = MANIFEST["build_assets"]["container"]["version"]
    assert ("container", version) in [(m.asset, m.version) for m in parse_markers(text)]


def test_a_repository_that_did_not_ask_for_it_does_not_get_it():
    # D16: containerization is a decision, not a detection.
    import pathlib as _p

    from repo_infra.assemble import render_all
    from repo_infra.detect import Detection
    result = Detection.load(ASSETS / "detection.json").detect(_p.Path(ROOT))
    assert "build/container.mk" not in render_all(ASSETS, result, MANIFEST)
    assert "build/container.mk" in render_all(
        ASSETS, result, MANIFEST, build=["container"])


def test_every_driver_target_is_inside_the_conditional():
    # The whole point of D18's conditional: inside the container this file must
    # define nothing, or `make test` there would invoke podman inside podman.
    text = FRAGMENT.read_text(encoding="utf-8")
    body = text.split("if CONTAINER_DRIVER", 1)[1].split("\nendif", 1)[0]
    for target in ("container:", "container-base:", "test:", "test-dev:"):
        assert "\n" + target in body, "%s is outside the conditional" % target
    assert "$(DOCKER)" not in text.split("if CONTAINER_DRIVER", 1)[0]


def test_test_dev_does_not_rebuild_the_full_image():
    # Depending on `container` would rebuild on every source edit and delete the
    # entire point of the target.
    text = FRAGMENT.read_text(encoding="utf-8")
    line = [l for l in text.splitlines() if l.startswith("test-dev:")][0]
    assert "container-base" in line
    assert "test-dev: container\n" not in text


def test_test_dev_requires_a_target():
    text = FRAGMENT.read_text(encoding="utf-8")
    assert "TARGET is required" in text
    assert "make test-dev TARGET=" in text


def test_the_fragment_no_longer_carries_the_test_runner_knobs():
    # D18: inside the container the project runs its own native `make test`, so
    # how the suite is invoked is the project's business again.
    text = FRAGMENT.read_text(encoding="utf-8")
    for knob in ("TEST_RUNNER", "TEST_DIR", "SKIP_TESTS"):
        assert knob not in text


def test_the_engine_comes_from_configure_not_a_make_default():
    # AC_CHECK_PROGS finds podman or docker and substitutes it, so a project with
    # only docker installed needs to do nothing.
    text = FRAGMENT.read_text(encoding="utf-8")
    assert "DOCKER ?=" not in text
    assert "$(DOCKER)" in text


def test_the_dev_mounts_are_declared_by_the_project():
    # The fragment cannot know which directories hold interpreted source, and a
    # blanket overlay would hide everything configure generated in the image.
    text = FRAGMENT.read_text(encoding="utf-8")
    assert "TEST_DEV_MOUNTS" in text
    assert "-v $(abs_top_srcdir):/src" not in text


def test_no_ci_block_calls_the_dev_loop():
    # test-dev is a developer convenience. What CI must verify is that the image
    # builds and its contents pass, which is `make test`.
    for path in sorted((ASSETS / "ci").glob("*.yml")) + sorted((ASSETS / "publish").glob("*.yml")):
        assert "test-dev" not in path.read_text(encoding="utf-8"), path.name


def test_the_fragment_has_no_host_package_declaration():
    # D16: wanting one is the trigger to containerize, not a missing feature.
    text = FRAGMENT.read_text(encoding="utf-8")
    for shape in ("apt-packages", "system_packages", "apt-get"):
        assert shape not in text


def test_the_fragment_has_no_substitution_tokens():
    # D15: an asset is the literal file it installs.
    text = FRAGMENT.read_text(encoding="utf-8")
    for token in ("$VERSION", "{{", "@PACKAGE@"):
        assert token not in text
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest tests/test_build_assets.py -q`
Expected: FAIL — `KeyError: 'container'`, and `test_the_old_test_only_fragment_is_gone` fails because the old file is still there.

- [ ] **Step 3: Write the fragment**

Create `skills/repo-infra/assets/build/container.mk`. **Listing A** — write this
if `spike-findings.md` says `Q1: A`:

```make
# repo-infra: container v1
#
# Autotools as a container driver (D18).
#
# Outside the container this file is the whole build: `make` builds the image,
# and every other target runs in it. Inside the container -- where configure ran
# with --disable-container -- the CONTAINER_DRIVER conditional is false and this
# file defines nothing at all, so the project's own targets stand.
#
# repo-infra owns this file. The project owns its Containerfile and what goes in
# it. Include it from Makefile.am, after calling REPO_INFRA_CONTAINER in
# configure.ac:
#
#     include $(top_srcdir)/build/container.mk
#
# The project may set, before the include:
#
#   CONTAINERFILE     path to the container definition  (default: Containerfile)
#   CONTAINER_TAG     tag to build and run              (default: $(PACKAGE)-build:local)
#   TEST_DEV_MOUNTS   dirs holding interpreted source   (default: none)
#
# There is deliberately no way to declare host packages. Needing one is what
# sent this project to containers in the first place (D16).

CONTAINERFILE ?= Containerfile
CONTAINER_TAG ?= $(PACKAGE)-build:local
TEST_DEV_MOUNTS ?=
TARGET ?=

if CONTAINER_DRIVER

.PHONY: container container-base test test-dev

# The full image. Its build phase runs ./configure --disable-container && make
# && make install, so building the image IS building the project.
container: $(top_srcdir)/$(CONTAINERFILE)
	$(DOCKER) build -t $(CONTAINER_TAG) -f $(top_srcdir)/$(CONTAINERFILE) $(top_srcdir)

# Same image, narrower prerequisite: rebuild only when the container definition
# changes. This is what the dev loop hangs off, so editing a script rebuilds
# nothing.
container-base: .stamp-container-base
.stamp-container-base: $(top_srcdir)/$(CONTAINERFILE)
	$(DOCKER) build -t $(CONTAINER_TAG) -f $(top_srcdir)/$(CONTAINERFILE) $(top_srcdir)
	touch $@

all-local: container

# The seam (D15). Inside the image this is the project's own native test target.
test: container
	$(DOCKER) run --rm $(CONTAINER_TAG) make -C /src test

# The dev loop: one test file, run against the live working tree. Never used by
# CI -- what CI must verify is that the image builds and its contents pass,
# which is `make test`.
test-dev: container-base
	@if [ -z "$(TARGET)" ]; then \
		echo "Error: TARGET is required"; \
		echo "Usage: make test-dev TARGET=t/foo.t"; \
		exit 1; \
	fi
	$(DOCKER) run --rm -it \
		$(foreach d,$(TEST_DEV_MOUNTS),-v $(abs_top_srcdir)/$(d):/src/$(d):ro) \
		$(CONTAINER_TAG) make -C /src test TESTS=/src/$(TARGET)

# The tarball is built by the same toolchain every time. Building it on the host
# instead would let a host-built and an image-built tarball differ, and nobody
# would notice until a user unpacked the wrong one.
dist: container
	$(DOCKER) run --rm -v $(abs_top_builddir):/out $(CONTAINER_TAG) \
		sh -c 'make -C /src dist && cp /src/*.tar.gz /out/'

install: container
	$(DOCKER) run --rm -v $(DESTDIR)$(prefix):/dest $(CONTAINER_TAG) \
		make -C /src install DESTDIR=/dest

clean-local:
	-rm -f .stamp-container-base
	-$(DOCKER) rmi $(CONTAINER_TAG)

endif
```

**Listing B** — write this instead if `spike-findings.md` says `Q1: B`. It is
identical except that automake's own `all`, `dist` and `install` are left alone
and the driver work hangs on hooks and separately named targets, because
automake refused the override:

```make
# ... header and variables exactly as in Listing A ...

if CONTAINER_DRIVER

.PHONY: container container-base test test-dev dist-container install-container

container: $(top_srcdir)/$(CONTAINERFILE)
	$(DOCKER) build -t $(CONTAINER_TAG) -f $(top_srcdir)/$(CONTAINERFILE) $(top_srcdir)

container-base: .stamp-container-base
.stamp-container-base: $(top_srcdir)/$(CONTAINERFILE)
	$(DOCKER) build -t $(CONTAINER_TAG) -f $(top_srcdir)/$(CONTAINERFILE) $(top_srcdir)
	touch $@

all-local: container

test: container
	$(DOCKER) run --rm $(CONTAINER_TAG) make -C /src test

test-dev: container-base
	@if [ -z "$(TARGET)" ]; then \
		echo "Error: TARGET is required"; \
		echo "Usage: make test-dev TARGET=t/foo.t"; \
		exit 1; \
	fi
	$(DOCKER) run --rm -it \
		$(foreach d,$(TEST_DEV_MOUNTS),-v $(abs_top_srcdir)/$(d):/src/$(d):ro) \
		$(CONTAINER_TAG) make -C /src test TESTS=/src/$(TARGET)

# automake owns `dist` and would not yield it, so the driver's tarball has its
# own name. The CI blocks and conventions.md must call `dist-container`.
dist-container: container
	$(DOCKER) run --rm -v $(abs_top_builddir):/out $(CONTAINER_TAG) \
		sh -c 'make -C /src dist && cp /src/*.tar.gz /out/'

install-container: container
	$(DOCKER) run --rm -v $(DESTDIR)$(prefix):/dest $(CONTAINER_TAG) \
		make -C /src install DESTDIR=/dest

clean-local:
	-rm -f .stamp-container-base
	-$(DOCKER) rmi $(CONTAINER_TAG)

endif
```

**If Listing B is the one you write, stop after this task and report it.** It
breaks the spec's claim that `publish-source-tarball.yml` needs no command
change, and Task 6 must then be re-planned rather than followed.

**Q2 adjustment.** If `spike-findings.md` says `Q2: no`, `TESTS=/src/$(TARGET)`
does not select one file. Do not invent a substitute — stop and report, because
the single-file seam is a spec decision, not an implementation detail.

- [ ] **Step 4: Delete the old fragment and re-point the manifest**

```bash
git rm skills/repo-infra/assets/build/container-test.mk
```

In `skills/repo-infra/assets/manifest.json`, replace the `container-test` entry
in `build_assets` with:

```json
    "container": {
      "version": 1,
      "source": "build/container.mk",
      "target": "build/container.mk",
      "comment": "#"
    }
```

The new asset starts at **v1**, not v2. `container-test` never shipped to any
repository — it exists only on this unmerged branch — so there is no installed
copy for a generation number to be relative to.

- [ ] **Step 5: Run the suite**

Run: `python3 -m pytest -q tests`
Expected: PASS. The count changes by the difference between the old
`test_build_assets.py` and the new one. **Derive it, do not explain it** — collect
test ids before and after and diff them. A count that is right for the wrong
reason is the failure mode that erodes trust in every later number.

- [ ] **Step 6: Commit**

```bash
git add -A skills/repo-infra/assets tests/test_build_assets.py
git commit -m "Rewrite the build fragment as the container driver"
```

---

### Task 5: The documented contract

**Files:**
- Modify: `skills/repo-infra/references/conventions.md:93-97` (the `build` key)
- Modify: `skills/repo-infra/references/teaching-the-standard.md:65-69`
- Modify: `commands/apply.md:19`
- Test: `tests/test_skill.py`

**Interfaces:**
- Consumes: the asset ids `container` and `container-m4` from Tasks 3 and 4.
- Produces: nothing later tasks read.

The Containerfile is documented, not shipped. A template would have to be edited
by every project to name its own packages, so a drift checker could not tell an
intended edit from a stale copy — the accommodation problem D15 forbids.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_skill.py`:

```python
def test_conventions_states_the_containerfile_contract():
    # D18: repo-infra owns the shape, the project owns the file. The contract is
    # the only thing standing between them, so it has to be written down.
    text = (ROOT / "skills/repo-infra/references/conventions.md").read_text(encoding="utf-8")
    assert "--disable-container" in text
    assert "/src" in text
    assert "container-m4" in text
    # The old test-only asset id must not survive anywhere in the docs.
    assert "container-test" not in text


def test_the_teach_reference_points_at_the_driver_not_the_test_fragment():
    text = (ROOT / "skills/repo-infra/references/teaching-the-standard.md").read_text(
        encoding="utf-8")
    assert "container-test" not in text
    assert "build/container.mk" in text
```

Check the top of `tests/test_skill.py` for the existing `ROOT` binding and reuse
it rather than redefining it.

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 -m pytest tests/test_skill.py -q`
Expected: FAIL — `container-test` is still in both documents.

- [ ] **Step 3: Rewrite the `build` key in `conventions.md`**

Replace the `- \`build\` -- ...` bullet (currently lines 93-97) with:

```markdown
- `build` -- which build assets this repository's Makefile and `configure.ac`
  install, by id (`manifest.json` `build_assets`). A containerized autotools
  repository names both: `["container-m4", "container"]` installs
  `m4/repo-infra-container.m4` and `build/container.mk`, which together make
  the tree a container driver (D18). Nothing installs them automatically; it is
  a decision, not a detection (see `references/teaching-the-standard.md`).
```

Then add a new section immediately after the `build` bullet's list:

```markdown
## The Containerfile contract (D18)

repo-infra owns the *shape* of the build environment; the project owns its
*content*. The `Containerfile` is therefore the project's own file and is not
shipped, versioned or drift-checked -- every project must edit it to name its
own packages, and a checker could not tell an intended edit from a stale copy.

What it must do, so the driver targets can reach it:

1. **Carry the autotools toolchain** -- `autoconf`, `automake` and `make` are in
   the image, because the image's build phase runs them.
2. **Run the real build in its build phase** --
   `./configure --disable-container && make && make install`. The flag names the
   semantics, not the location: it means "do the real build in this tree", which
   is also what a distro packager on a bare build host wants.
3. **Leave the build tree at `/src`** -- `make dist` and `make test` are run
   against that path from outside.

`configure.ac` calls `REPO_INFRA_CONTAINER` and wraps its own dependency checks:

    REPO_INFRA_CONTAINER
    AS_IF([test "x$enable_container" = xno], [
      dnl librrd, RRDs, everything real -- probed here and nowhere else
    ])

**Single-file test runs.** `make test-dev TARGET=t/foo.t` reaches one file
through `make test TESTS=<file>`. Automake honours a command-line `TESTS=`
override for free, so a project whose `test` target is `test: check` needs to do
nothing. A project that drives `prove` itself must honour `TESTS` the same way.
```

- [ ] **Step 4: Rewrite the paragraph in `teaching-the-standard.md`**

Replace lines 65-69 with:

```markdown
If containerizing is the answer, what repo-infra ships for it is a pair of build
assets: `container-m4` (`m4/repo-infra-container.m4`, the `--disable-container`
switch) and `container` (`build/container.mk`, the driver targets). Install them
by naming both in the repository's own `build` list in `.github/repo-infra.json`
(`references/conventions.md`), and write the `Containerfile` the contract there
describes. Nothing installs them automatically; it is a decision, not a
detection.
```

- [ ] **Step 5: Fix the asset id in `commands/apply.md`**

On line 19, replace `container-test` with `container-m4`, `container`.

- [ ] **Step 6: Run the suite**

Run: `python3 -m pytest -q tests`
Expected: PASS, two more tests than Task 4 left.

- [ ] **Step 7: Commit**

```bash
git add skills/repo-infra/references commands/apply.md tests/test_skill.py
git commit -m "Document the Containerfile contract and the driver asset pair"
```

---

### Task 6: The CI blocks lose their known limit

**Files:**
- Modify: `skills/repo-infra/assets/ci/ci-perl-autotools.yml` (comment only)
- Modify: `skills/repo-infra/assets/publish/publish-source-tarball.yml`
- Modify: `skills/repo-infra/assets/manifest.json` (`publish-source-tarball` to v2)
- Test: `tests/test_blocks.py`, `tests/test_publish.py`

**Interfaces:**
- Consumes: the driver semantics from Tasks 3 and 4 — plain `./configure` is now
  driver mode, so `make` builds the image and `make dist` delegates.
- Produces: nothing later tasks read.

**Do not start this task if Task 4 produced Listing B.** Under Listing B the
driver's tarball target is `dist-container`, and both this task and the spec
section it implements need re-planning.

**`ci-perl-autotools` does not get a version bump.** Its commands do not change;
only a stale comment goes. A marker records "your copy is N generations old,
re-apply to get the fix", and there is no fix here to re-apply.
**`publish-source-tarball` does** go to v2: `podman` on the runner is a real
behaviour change, and a repository on v1 would fail at its next release.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_blocks.py`:

```python
def test_the_autotools_block_no_longer_documents_a_bare_configure_limit():
    # D18 closed it: plain ./configure is driver mode, so the runner never
    # probes the project's system dependencies.
    text = (ASSETS / "ci/ci-perl-autotools.yml").read_text(encoding="utf-8")
    assert "Known limit" not in text
    assert "enable-pkgonly" not in text
```

Add to `tests/test_publish.py`:

```python
def test_the_tarball_block_can_drive_a_container():
    # `make dist` is a container call in driver mode (D18), so the runner needs
    # an engine. Without it configure fails before dist is ever reached.
    text = (ASSETS / "publish/publish-source-tarball.yml").read_text(encoding="utf-8")
    assert "autoconf automake gettext podman" in text
    assert "Known limit" not in text
```

**A publish block carries no marker of its own.** `assemble_publish` injects it
from the manifest version (`assemble.py:82`), so bumping the manifest is the
whole change — there is no marker line in the block file to edit. That also
means an existing test is pinned to v1 and must move. In
`tests/test_publish.py`, change `test_the_tarball_addon_carries_its_marker`:

```python
def test_the_tarball_addon_carries_its_marker():
    text = assemble_publish(ASSETS, ["publish-source-tarball"], MANIFEST)
    assert ("publish-source-tarball", 2) in [
        (m.asset, m.version) for m in parse_markers(text)]
```

Check the top of `tests/test_publish.py` for existing `ASSETS`, `MANIFEST` and
`parse_markers` bindings and reuse them rather than redefining them.

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest tests/test_blocks.py tests/test_publish.py -q`
Expected: FAIL — both `Known limit` comments are present, `podman` is not in the
tarball block's toolchain, and the retargeted marker test still sees v1.

- [ ] **Step 3: Delete the stale comment in the autotools block**

In `skills/repo-infra/assets/ci/ci-perl-autotools.yml`, replace the whole
`# Known limit: ...` paragraph under `Install the autotools host toolchain`
with:

```yaml
      # The fixed host toolchain: enough to bootstrap, configure, and drive a
      # container. It is the same for every autotools project, which is what
      # makes it infrastructure. Deliberately no package list (D16).
      #
      # These four commands serve both kinds of autotools repository unchanged.
      # A containerized one configures into driver mode (D18), so `make` builds
      # its image and `make test` runs the suite inside it -- and `configure`
      # never probes the project's own dependencies on this runner. One that
      # stayed native has no Containerfile, does not call REPO_INFRA_CONTAINER,
      # and runs plain autotools here.
```

Leave the four `run:` steps exactly as they are.

- [ ] **Step 4: Add podman to the tarball block and bump it**

In `skills/repo-infra/assets/publish/publish-source-tarball.yml`:

- Replace the `# Known limit: ...` comment with:

```yaml
      # `make dist` is a container call in a repository that converted to the
      # D18 driver, and a plain automake dist in one that did not. The same two
      # commands cover both, so long as the engine is here.
```

- Change the install line to:

```yaml
          sudo apt-get install -y autoconf automake gettext podman
```

In `skills/repo-infra/assets/manifest.json`, set
`publish_blocks["publish-source-tarball"]["version"]` to `2`.

- [ ] **Step 5: Run the suite**

Run: `python3 -m pytest -q tests`
Expected: PASS, two more tests than Task 5 left (one added to each of
`test_blocks.py` and `test_publish.py`; the marker test moved rather than grew).

- [ ] **Step 6: Re-render repo-infra's own `.github/`**

repo-infra gets no exemption from its own standard, and a test fails if the
assembler's output and the committed `.github/` diverge. Run the suite again
after any re-render, and if `tests/test_self_render.py` fails, follow whatever
regeneration command that test names rather than hand-editing `.github/`.

- [ ] **Step 7: Commit**

```bash
git add skills/repo-infra/assets tests/test_blocks.py tests/test_publish.py
git commit -m "Retire the bare-configure limit from the autotools and tarball blocks"
```

---

### Task 7: Changelog

**Files:**
- Modify: `CHANGES.md`

**Interfaces:**
- Consumes: everything above.
- Produces: nothing.

- [ ] **Step 1: Read the top of the file**

```bash
head -30 CHANGES.md
```

Match the existing heading style exactly. The section heading is `### New`,
never `### Added`, and new bullets go at the **top** of their section.

- [ ] **Step 2: Add the entries**

At the top of the unreleased `### New` section (create the section if there is
none, following the shape of the previous release's):

```markdown
- Autotools repositories can now build in a container end to end. `configure`
  and `make` outside the container drive podman; inside, they are plain
  autotools. A CI runner no longer probes a project's system dependencies.
- `make test-dev TARGET=t/foo.t` runs one test file against the live working
  tree, without rebuilding the image.
```

- [ ] **Step 3: Run the suite**

Run: `python3 -m pytest -q tests`
Expected: PASS, unchanged count.

- [ ] **Step 4: Lint**

Run: `uvx ruff check .`
Expected: clean. (`make lint` fails locally because `ruff` is not importable from
the sandboxed python here; that is expected and fine in CI.)

- [ ] **Step 5: Commit**

```bash
git add CHANGES.md
git commit -m "Note the container driver in the changelog"
```

---

## What this plan does not do

- **It does not convert SmokePing.** Task 7 of the previous plan is still
  user-reserved and unstarted, and it is the only real proof of this design:
  provenance is not verification, and `./configure && make && make test` has to
  run green on a runner holding no `librrd` before any of this is known to work.
- **It does not push, open a PR, or merge.** The branch is local-only and the
  integration decision is the user's.
- **It does not run anything in GitHub Actions.** Every test here is local, and
  nothing on this branch has ever executed on a runner.
- **It does not add a `check` item for a missing `VERSION` file.** That gap is
  logged in the previous handoff and is a separate feature.

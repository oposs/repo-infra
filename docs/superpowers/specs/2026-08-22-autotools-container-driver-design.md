# repo-infra — autotools in a dual role

Date: 2026-08-22
Extends: `2026-08-21-teach-and-build-containers-design.md` (D16–D17)

This document adds one decision, D18, and rewrites two assets around it. It
amends D17 the way D17 amended D15: the line between what repo-infra owns and
what the project owns moves again, and for the same reason — the coarser line
left a hole a real repository falls into.

## The hole

`ci-perl-autotools.yml` shipped with its own defect written into it:

> Known limit: only `make test` below can reach a container. `bootstrap`,
> `configure` and `make` still run on this bare runner, so a project that
> cannot configure without its own system packages has hit the D16 threshold
> here too.

The same warning is in `publish-source-tarball.yml`, which names the fix:
*"Containerizing the dist build is the next teach."* This document is that
teach.

The failure is not hypothetical. `oetiker/SmokePing` — the repository the
containerized contract was written for — has a `configure.ac` that calls
`exit 1` without `RRDs`. The rewritten block cannot build it. Containerizing
only the test step containerizes the wrong step.

## D18 — autotools plays two roles, and the default is the one you do not control

An autotools tree that has crossed the D16 threshold serves two callers:

| Caller | What `configure` and `make` mean |
|---|---|
| **Outside the container** — a stranger with a checkout, a CI runner, a developer | Verify podman works. Drive the container. Build nothing locally, probe no project dependency. |
| **Inside the container's build phase** — and a distro packager | Plain autotools. Configure, make, install, with every dependency present. |

**The default is the outside role, and the flag marks the inside one.** This is
the load-bearing choice and it is not symmetric with taste. The outside caller
is the one you do not control: someone clones the repository and types
`./configure && make` because that is what an autotools tree has meant for
thirty years. That must work on a machine holding none of the project's
dependencies, and it does, because the container carries them.

The inside caller is a call site you own — a `RUN` line in a Containerfile you
wrote, or a packager who has already read your build instructions. Putting the
flag there costs nothing.

### The flag names the semantics, not the location

The flag is `--disable-container`, meaning **"do the real build in this tree"**.
It is not `--enable-in-container`.

The distinction is not cosmetic. A Debian packager building SmokePing on a bare
build host wants exactly the in-container behaviour and is not in a container.
With `--disable-container` there is one concept and two callers. With a flag
that asserts a location, that packager must either pass something false or the
standard grows a third mode for them.

### Configure is opportunistic inside and minimal outside

The two roles justify different levels of paranoia, and the asymmetry is a
feature:

- **Inside**, the image's contents are known exactly. Configure can assume and
  fail hard rather than probe and degrade.
- **Outside**, configure probes almost nothing: a container engine exists and
  a `Containerfile` is present. Nothing else is knowable and nothing else is
  needed.

## The mode switch — `assets/m4/repo-infra-container.m4`

A new asset kind. repo-infra has shipped workflow YAML, GitHub JSON and an
automake fragment; it now ships an m4 macro.

```m4
AC_DEFUN([REPO_INFRA_CONTAINER], [
  AC_ARG_ENABLE([container],
    [AS_HELP_STRING([--disable-container],
       [build in this tree instead of driving a container])],
    [], [enable_container=yes])
  AS_IF([test "x$enable_container" = xyes], [
    AC_CHECK_PROGS([DOCKER], [podman docker])
    AS_IF([test -z "$DOCKER"],
      [AC_MSG_ERROR([no podman found; install it, or pass --disable-container])])
    AS_IF([test -f "$srcdir/Containerfile"], [],
      [AC_MSG_ERROR([no Containerfile; pass --disable-container])])
  ])
  AM_CONDITIONAL([REPO_INFRA_CONTAINER], [test "x$enable_container" = xyes])
])
```

The project wraps its own dependency checks in one conditional:

```m4
REPO_INFRA_CONTAINER
AS_IF([test "x$enable_container" = xno], [
  # librrd, RRDs, everything real -- never probed on the host
])
```

**Why a macro rather than a documented convention.** The flag must be spelled
identically in every repository or the shared CI block cannot call it. A
convention in prose is not checkable; an asset carries a version marker and
gets drift-checked, which is the same argument D17 used to put the fragments in
repo-infra instead of a sibling repository.

**Assets stay literal (D15).** The macro is a fixed file parameterized at
configure time, not at install time. No substitution tokens.

## The driver — `assets/build/container.mk`

Replaces `container-test.mk`, under the same `build_assets` selector.

**Outside the container, `make` drives podman and nothing else.** One rule, no
per-target table to learn:

| Target | Driver mode does |
|---|---|
| `all` | `podman build` — the image is the artifact |
| `test` | run the suite in the image |
| `dist` | run `make dist` in the image, copy the tarball out |
| `install` | run `make install` in the image against a mounted `DESTDIR` |
| `clean` | local clean, and remove the image |
| `container-base` | rebuild the image only if the `Containerfile` changed |
| `test-dev` | run one test file against the live working tree — see below |

The alternative — letting dependency-free targets like `dist` run natively on
the host — was rejected. It creates a rule a user has to learn, and worse, it
allows a host-built tarball and an image-built tarball to differ. **The mode
must never change what `make dist` ships**, and building it in one place is the
only version of that rule nobody has to enforce by hand.

### The fragment is conditional, and that is not optional

```make
if REPO_INFRA_CONTAINER
test: container
	$(DOCKER) run --rm $(CONTAINER_TAG) make -C /src test
...
else
# native mode -- the fragment defines nothing; the project's targets stand
endif
```

Without the conditional, `make test` **inside** the container would invoke
podman inside podman. This is what `AM_CONDITIONAL` in the macro exists for.

### The fragment shrinks

`container-test.mk` carried `TEST_RUNNER`, `TEST_DIR` and `SKIP_TESTS`, and
enumerated `.t` files on the host to pass in by name. All of that goes.

Inside the container the project runs **its own native `make test`**, so how the
suite is invoked, which files it holds and what it skips are the project's
business, expressed in its own `Makefile.am`. The fragment becomes pure
delegation. The empty-glob hazard the old fragment guarded against belongs to
the project's own test target now.

`DOCKER` also stops being a make variable the project sets. `AC_CHECK_PROGS`
finds the engine at configure time and substitutes it, so the fragment reads
`@DOCKER@` and a project with only `docker` installed needs to do nothing. The
old `DOCKER ?= podman` default goes with it.

## The dev loop — `make test-dev TARGET=t/foo.t`

`make test` is the trusted path: it rebuilds the image and tests exactly what
was built, and it is what CI runs. It is also the wrong tool for changing one
line in a script and re-running one test, because the `Containerfile` bakes the
source in — any edit invalidates that layer and the image rebuilds.

`test-dev` is the cheap loop, for the scripting case only. It mounts the live
working tree over the image's copy and runs **one** test file.

`hin-agw-common/automake/test-dev.mk` is the proven shape and this follows it:

```make
if REPO_INFRA_CONTAINER
TARGET ?=
test-dev: container-base
	@if [ -z "$(TARGET)" ]; then \
		echo "Error: TARGET is required"; \
		echo "Usage: make test-dev TARGET=t/foo.t"; \
		exit 1; \
	fi
	$(DOCKER) run --rm -it $(TEST_DEV_MOUNTS) $(CONTAINER_TAG) \
		make -C /src test TESTS=/src/$(TARGET)   # seam: see below
endif
```

Three properties, each load-bearing:

**`TARGET` is required.** `test-dev` runs one file. Running everything is what
`make test` is for, and it is the one that rebuilds first — so the fast target
can never be mistaken for the trustworthy one.

**It depends on `container-base`, not `container`.** `container-base` is a
stamp-file rule whose only prerequisite is the `Containerfile`. Editing a script
rebuilds nothing; editing the `Containerfile` rebuilds. Depending on `container`
would rebuild the image on every source edit and delete the entire point of the
target.

**`-it`.** The reference uses it and the reason is a debugger.

### The single-file seam is `TESTS=`

The reference invokes its own runner script with the file as an argument. D18
has no runner script — the contract is `make test` and nothing below it. So the
seam for one file is a variable, not an argument:

    make test TESTS=/src/t/foo.t

**Automake honours this for free.** `TESTS` is an ordinary make variable, and a
command-line assignment overrides the `Makefile.am` value, so a project whose
`test` target is `test: check` needs to do nothing at all. A project whose
`test` target drives `prove` itself must honour `TESTS` the same way — one line
in its own `Makefile.am`, and it is stated in the `conventions.md` contract
alongside `make test`.

This adds no knob to the fragment and no second seam to the standard. It does
rest on an autoconf behaviour that must be confirmed rather than assumed, so it
joins the spike below.

### The mounts are declared by the project

`TEST_DEV_MOUNTS` names the directories holding interpreted source and tests.
The fragment cannot know which those are, and the answer is project content —
the side of D17 it belongs on.

**This deviates from the reference deliberately.** In `hin-agw-common`,
`TEST_DEV_MOUNTS` is the complete raw `-v` argument string, because that repo's
in-image layout (`/app`) does not mirror its source tree and each mount needs
its own mapping. D18 fixes the tree at `/src` as a mirror of the source, so the
project can declare bare directory names and the fragment builds the flags:

```make
# project's Makefile.am, before the include
TEST_DEV_MOUNTS = lib t bin/plugins
```

### Why it does not overlay the whole tree

An autotools project generates files into its build tree — `bin/smokeping.dist`
becomes `bin/smokeping` with paths substituted in. Those exist in the image and
not on the host. A blanket `-v $(abs_top_srcdir):/src:ro` hides them, and the
suite then fails for a reason unrelated to the edit being tested. Overlaying
only the declared script directories leaves everything `configure` generated
visible.

### It never runs in CI

`test-dev` is a developer convenience. No CI block calls it, and none should:
what CI must verify is that the image builds and its contents pass, which is
`make test`.

## What CI becomes

**`ci-perl-autotools.yml` needs no change to its commands.** It already reads:

```yaml
- run: ./bootstrap
- run: ./configure --prefix=$HOME/test-install
- run: make
- run: make test
```

In driver mode that is: bootstrap, verify podman, build the image, test in the
image. `configure` never looks for `RRDs` on the runner. The only edit is
**deleting the known-limit comment**, because the limit is gone.

`publish-source-tarball.yml` needs `podman` added to its host toolchain and its
warning comment deleted. Nothing else: plain `./configure` is now driver mode,
so `make dist` delegates by itself.

**One shape serves both kinds of autotools repository.** A repository that has
not crossed the D16 threshold has no `Containerfile`, does not call the macro
and does not include the fragment, so the identical blocks run plain autotools
for it. There is no branch in the CI block and no flag for `apply` to decide.

## Ownership after D18

| repo-infra ships, versioned and drift-checked | The project owns |
|---|---|
| `m4/repo-infra-container.m4` — the flag and the conditional | Its `Containerfile` |
| `build/container.mk` — the driver targets | Its dependency checks, inside the conditional |
| The `test-dev` shape | `TEST_DEV_MOUNTS` — which directories hold scripts |
| The `make test` contract, unchanged | Its test suite and how it runs |

**The `Containerfile` is documented, not shipped.** It gains a contract, stated
in `conventions.md`:

1. The image carries `autoconf`, `automake` and `make`.
2. Its build phase runs `./configure --disable-container && make && make install`.
3. The build tree lands at a known path, `/src`.

Shipping a template was rejected. Every project must edit it to name its own
packages, so a drift checker could not tell an intended edit from a stale copy
— which is exactly the accommodation D15 forbids. Shipping an unchecked
one-time scaffold was also rejected: an asset with no version marker goes
silently stale as the contract moves.

## The known unknown — automake owns `dist`

`all`, `install`, `dist` and `check` are automake's targets. An included
fragment does not simply replace them: automake offers hooks (`all-local`,
`dist-hook`) that run *during* the real target rather than instead of it.
`test` is ours and costs nothing. `dist` is the hard case, and `dist` is what
the release depends on.

**The implementation plan opens with a throwaway spike** on a scratch autotools
tree, answering two questions:

1. Can an included fragment replace `dist` cleanly under an automake
   conditional, or does driver mode need a `Makefile.am` empty enough that the
   real targets do nothing and the work hangs on hooks?
2. Does `make test TESTS=<file>` on the command line actually override the
   `Makefile.am` value through automake's `check`? The single-file seam above
   depends on it.

The answers shape the fragment and nothing else should be written before they
land.

This is deliberately not guessed here. A plan containing complete code is
exactly as untested as anything else.

## Testing

- The manifest-pin test covers the two new assets automatically; a test must
  confirm both are selected by `build_assets`.
- `container.mk`'s conditional needs a test that the driver targets are absent
  in native mode — the podman-inside-podman failure is silent until it hangs.
- **Real proof is `oetiker/SmokePing`.** Provenance is not verification: the
  design is a hypothesis until `./configure && make && make test` runs green on
  a runner holding no `librrd`. That is the conversion this unblocks.

## Deliberately not now

- **Container fragments for other ecosystems.** Still autotools-shaped, still a
  teach when a real repository hits it.
- **A `--disable-container` equivalent for non-autotools ecosystems.** There is
  no `configure` to hang it on and no second repository asking yet.
- **Multi-stage Containerfile guidance.** Baking the source into the image means
  an edit invalidates the layer and rebuilds. `test-dev` answers that for the
  scripting case without touching the `Containerfile` at all, which is the
  cheaper answer. If a compiled project makes the rebuild cost real, that is a
  new question and a new teach.
- **A `test-dev` that runs more than one file.** The reference has run with
  exactly one required `TARGET` for two years. Widening it would blur the line
  between the fast target and the trustworthy one.

## Open questions

None outstanding. Three were resolved on 2026-08-22 and are folded into the text
above: which side of the container carries the flag (the inside), what the flag
means (build natively here, not "I am in a container"), how far the driver
delegates (everything real runs in the container), and how `test-dev` finds the
live source (the project declares the directories).

# repo-infra — the teach path and containerized builds

Date: 2026-08-21
Extends: `2026-08-17-repo-infra-design.md` (D1–D15, specs 1–4)

This document adds one subsystem and two cross-cutting decisions. It does not
replace the earlier design; D16 and D17 continue that document's D-series, and
D17 amends D15 rather than overturning it.

## Purpose

repo-infra carries the standard. **Claude, holding the plugin, does the
conversion.** The tool detects drift and installs versioned assets; it does not
mechanically transform a repository, and it was never meant to. Initial
conversions lean almost entirely on judgement — reading what a repository
actually does and deciding how it reaches the standard. Only later upgrades of
an already-conforming repo are mechanical.

That has a consequence the design did not previously state. When a conversion
meets a shape the standard has no answer for, there are three things that could
happen, and only one of them is acceptable:

| | |
|---|---|
| Patch the repository around the gap | Forbidden. This is accommodation, and it is what the tool exists to prevent. |
| Grow a variant asset for this repo | Forbidden by D15. |
| **Teach the standard, then convert** | The only correct move, and until now undocumented. |

Nothing in the plugin said so, and nothing told Claude what to do instead. That
omission is what this document closes.

## Evidence

Two repositories drove this, and neither is hypothetical.

**`oposs/mkp-builder`** — `check` reports `detected nothing` and then
`9 items need attention`. It is a Python script plus an `action.yml`, and
`action.yml` is not a detection signal for any ecosystem that exists. The report
reads as "this repository is broken" when the true statement is "the standard
does not know what this repository is."

**`oetiker/SmokePing`** — detection is correct (`perl-autotools`), but installing
the block would fail on the first pull request:

- The block runs `make test`. SmokePing has no `test` target; its tests are
  automake `TESTS` in `t/Makefile.am`, so `make check` runs them. One of the two
  has to move, and nothing in the tool or the skill said which — the first
  reading of this called the block wrong, which D16 and D17 below overturn.
- The block installs nothing. The build needs `librrds-perl`, `rrdtool` and
  `dma`, which SmokePing's own workflow installs and the standard has no way to
  express.
- The version-file writer expects a bracketed literal in `AC_INIT`. SmokePing
  has `AC_INIT([smokeping], m4_esyscmd([tr -d '\n' < VERSION]), ...)`, and the
  shipped regex matches nothing.

None of the three was findable by running the tool. All three came from reading
the repository. That is the detection model this document commits to.

**`hin-access-suite`** then answered the second one in a way that deleted the
question rather than solving it — see D16.

## The teach path

A third verb beside `check` and `apply`. It is a procedure Claude follows, not a
subcommand: consistent with the detection model below, it needs judgement, not
machinery.

### What triggers it

Two kinds of gap, found two different ways.

**Machine-visible.** `check` already sees these: no ecosystem matched
(`detected nothing`), or the detection signals are ambiguous. The tool reports
them; nothing new is required to find them.

**Judgement-visible.** During a conversion, Claude reads the repository's real
build, test and release setup against the standard it is about to install, and
finds either that the standard is **silent** about something the repository
needs, or that adopting the standard would **break something that currently
works**. This is the SmokePing case, and it is the common one.

Deliberately rejected: having each CI block declare its assumptions as
metadata, so a fit check could compare them mechanically. An assumption list
only catches what its author remembered to model — the same failure mode as the
mocked Checkmk API that cost this project a task. Reading the real repository
beats maintaining a summary of what the blocks believe about the world.

### What is and is not a question for the user

| Situation | Response |
|---|---|
| The standard is silent | Ask. The answer becomes the rule. |
| The standard conflicts with working behaviour | Ask. Either the repo migrates or the standard moves. |
| The repository merely differs from a settled decision | Do not ask. The repository migrates. |
| A settled decision conflicts *severely* | Ask, and say why this one is not routine. |

Settled decisions are D1 (`main`), D5 and D6 (`CHANGES.md` and its format), and
anything else already numbered. A first conversion must not become an
interrogation that relitigates the whole D-series per repository.

### The three stages

**1. Question.** Put the gap to the user as a scoped question: what the standard
does not cover, what this repository does instead, and what the options are.
Not "may I add X". The user answers; the answer is a ruling about the standard,
not about this repository.

**2. Prove.** Work the answer out in the repository's own tree and show it green
in CI. Nothing is upstreamed on reasoning alone. This project has already paid
for the general form of this lesson: provenance is not verification, and a thing
copied from a repository where it works is a hypothesis until it runs against a
real consumer.

**3. Upstream.** The proven answer becomes a pull request against repo-infra.
The repository's own conversion pull request merges **after** that has shipped
and the plugin has been updated — so no repository ever carries a shape the
standard does not have, and nothing is standardised that has not been shown to
run.

### Definition of done, scaled to the change

| Change | What must exist |
|---|---|
| A block fix (a wrong cache directory, a mistyped target) | Changed asset + a test. The fix is self-evident; no doc edit. |
| A new seam, a new ecosystem, a new rule | Numbered decision in a design document + asset + test. |

The scaling is deliberate. Requiring a numbered decision for a one-word
correction makes the D-series sprawl; requiring none for a new concept lets
concepts land undocumented.

### One report change

`check` currently prints `detected nothing` above the ordinary
`N items need attention` line, which reads as a broken repository. It is not:
the item list under an unrecognised repository is largely meaningless, because
no CI block can be selected at all.

When no ecosystem matches, the report says so as its own outcome — the standard
does not recognise this repository — and points at the teach path rather than at
`/repo-infra:apply`. The administration items (protection, label, permissions)
remain valid and are still reported; only the ecosystem-dependent conclusion
changes.

## D16 — the containerization threshold

A project builds natively while it needs nothing beyond the runner's default
image plus its ecosystem toolchain. **The moment it needs an additional system
package, the standard can no longer build it, and that is the signal to raise
the question with the human.**

**The threshold decides when to ask. It does not decide the answer.** Whether a
given repository goes to containers is a discussion, not a detection — this is
stage 1 of the teach path, not an automatic rewrite. Containerization is the
expected answer and the reason D17 exists, but the alternatives are real: the
project may drop the dependency, or the conversation may produce something the
standard does not have yet. What is *not* available is carrying on natively
while quietly installing packages from CI.

There is deliberately **no mechanism for declaring system packages to CI.**
Wanting one is the trigger, not a missing feature. Three shapes were considered
and rejected:

| Rejected | Why |
|---|---|
| `.github/apt-packages.txt`, installed if present | Solves a problem containerization deletes, and couples CI to whatever the runner image ships. |
| A `system_packages` field in `.github/repo-infra.json` | Same, plus it puts a build-toolchain fact in repo-infra's own config. |
| A project-owned `ci-setup.sh` | Arbitrary commands on the runner, and every repository solves the problem its own way. |

The rule is a property of the **project**, not of its language. Rust, Go and
Node ship hermetic toolchains and will usually stay below the threshold; a Perl
project linking `librrd` is over it on day one. Nothing is mandatory and no
ecosystem is exempt — the threshold decides when the question comes up.

**Why containers rather than a package list.** Building and testing inside a
container cuts the dependence on whatever a developer happens to have
installed, makes a local run and a CI run the same commands with the same
result, and isolates the project from the idiosyncrasies of whichever CI system
runs it. A package list achieves none of the three.

**The host toolchain stays unified and small.** A containerized job still needs
enough on the host to drive the build: `autoconf automake gettext podman` for
autotools. That list is the same for every project of that kind and lives in the
CI block — it is infrastructure, not a per-repo declaration.

**The timing is favourable and will not stay that way.** Almost nothing in the
estate has a container setup yet, so a single shape can be set before habits
diverge. `hin-agw-common` is the only worked example and was built as shared
infrastructure from the start.

## D17 — repo-infra owns the shape of the build environment; the project owns its content

This amends D15, which assigned build and test toolchains wholesale to the
project. D16 makes that boundary too coarse: if every repository that crosses
the threshold writes its own container test machinery, the estate acquires one
divergent implementation per repository, which is exactly the accommodation D15
exists to forbid.

The line moves to:

| repo-infra ships, versioned and drift-checked | The project owns |
|---|---|
| The automake fragments — container build, container test | Its `Dockerfile` |
| The `make test` contract | Which packages go in the image, what the tests do |

The seam is unchanged: a single `make test` in the CI block. What that target
does is now partly standard.

**This does not require substitution tokens, and that is why it works.**
`hin-agw-common/automake/test-container.mk` is a literal, generic file
parameterized by make variables the project sets in its own `Makefile.am`
(`SKIP_TESTS`, `PGDB`, `CONTAINER_PREFIX`, `APP_CONFIG_ENV`). That is runtime
parameterization, not install-time substitution, so D15's "assets are literal
files" holds without exception.

**Shipping from repo-infra rather than a sibling repository is the point.** A
fifth repository holding shared build machinery would sit outside the drift
checker, and nothing would report when a project's copy went stale. As a
repo-infra asset it carries a version marker like every other, so `check` says
"your container test fragment is two generations old" — which is the capability
this whole tool exists to provide.

## Consequences for spec 1

Three assets change. Each is a teach in the sense above, and each is already
answered.

1. **`assets/build/*.mk`** — the container test fragment, generalised from
   `hin-agw-common/automake/test-container.mk`, literal and marker-versioned.
   A project that the D16 conversation sends to containers installs it and
   writes its own `Dockerfile`.

2. **`ci-perl-autotools` rewritten** — install the fixed host toolchain, then
   `./bootstrap`, `./configure`, `make`, `make test`. No package list and no
   per-repo variance. `make test` is the contract; whether it runs natively or
   in a container is the project's business below the seam.

3. **The version-file writer reads `VERSION`** — `AC_INIT` with
   `m4_esyscmd([tr -d '\n' < VERSION])` is the house idiom in both autotools
   repositories examined (`SmokePing`, every project in `hin-access-suite`).
   The standard writes `VERSION` and stops trying to rewrite `configure.ac`.

## Deliberately not now

- **Container fragments for other ecosystems.** The fragments are
  autotools-shaped. A Rust or Node project that crosses the D16 threshold has no
  automake to hang them on and needs a different shape. That is a teach when a
  real repository hits it, not a thing to invent in advance.
- **A `ci-setup.sh` escape hatch** for PPAs and source builds. If a project needs
  one, that is a new gap and a new question — the path working as designed, not
  a design failure.
- **A `github-action` ecosystem** for `mkp-builder`. Still needed, still
  unbuilt; it is now the first candidate to go through the teach path rather
  than around it.

## Blocking dependency on spec 2 — the source tarball

**A source `.tar.gz` on the release is required, not optional.** It is the
classic distribution format for an autotools project and the estate wants it.
Spec 2's add-on list — crates.io, MKP, npm, nfpm deb/rpm/apk, Windows zip and
winget, ghcr containers — has no entry for it. That is an omission in the
earlier document, not a deliberate exclusion, and it makes the tarball add-on
spec 2's **first** item rather than one of eight.

The consequence is an ordering constraint on real work:

- `release-publish.yml` creates a draft release and `finalize` un-drafts it,
  with `finalize`'s `needs:` list generated by `apply` precisely so add-on jobs
  slot between the two. The seam exists and is built.
- Nothing attaches an artifact to it yet, so an autotools repository converted
  today would publish releases with no tarball. SmokePing publishes
  `smokeping-X.Y.Z.tar.gz` from `make dist` now, so converting it before the
  add-on lands is a regression its users would see immediately.
- Therefore: **the source tarball add-on ships before any autotools repository
  is converted.** SmokePing waits for it.

## Open questions

None outstanding. Two were resolved on 2026-08-21 and folded into the text
above: whether crossing the D16 threshold decides containerization (it does not
— it starts a conversation), and whether an autotools release must carry a
source tarball (it must).

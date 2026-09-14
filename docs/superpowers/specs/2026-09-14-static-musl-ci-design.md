# repo-infra — the static musl CI add-on

Date: 2026-09-14
Extends: `2026-08-17-repo-infra-design.md` (the D-series), D15's assembled `ci.yml`
Proved in: `oetiker/oxutrm` — the `musl:` job in `.github/workflows/ci.yml` and
`build-binaries:` in `.github/workflows/release.yml`, both green in production
since 2026-08-28

This document adds one decision, D22, one CI block, and one new seam: the first
CI block a repository **chooses** rather than one detection finds.

## The gap

The standard's Rust block builds and tests on the runner and stops there. A
project whose product is a Linux binary ships something the standard never
compiles: a statically linked musl build, cross-compiled for two architectures.

`oetiker/oxutrm` discovered the cost of leaving that out of CI. Its binary is
copied to whatever host the user sshes into. A dynamically linked build against
`GLIBC_2.39` refuses to start on an Ubuntu 22.04 host at 2.35 — for the sake of
two symbols — and that is what stopped a working end-to-end test on 2026-08-28.
The fix was a static musl build; the lesson was that it has to be compiled on
every pull request, not discovered at release time, because the release is the
worst possible place to learn that a cross-compile broke.

The standard was **silent**: it has no rule for cross-compilation at all, and no
way for a repository to say that it ships a binary.

## D22 — the static musl build is an opt-in CI block, and a required one

### Opt-in, not always-on

Every existing CI block is installed by detection: the ecosystem's files are
present, so its jobs go in. This one is not, and that is the new seam.

The reason is that `Cargo.toml` does not say what a Rust repository *is*. The
standard's own Rust consumers split cleanly in half:

| Repository | What it is | Wants a static musl build |
|---|---|---|
| `oetiker/oxutrm` | binary, copied to arbitrary hosts | yes — and it is why this exists |
| `oetiker/tvision-rs` | library + proc-macro crate, published to crates.io | no binary exists to link |
| `oetiker/mdmost` | published crate | n/a |
| `oposs/byonk`, `oposs/oxulnk` | binaries, not on crates.io | a decision, not a given |

Made always-on, this block gives `tvision-rs` two cross-compiles per pull
request — `cargo install cross` builds cross from source before either of them
starts — to assert nothing at all, because a library workspace has no binary to
link. That is not a rounding error on a repository that also runs check, test
and the workflow library.

Detection *could* be taught to look for `[[bin]]` or `src/main.rs`. It must not:
the presence of a binary is not the intent to ship one to hosts the project does
not control, and **D12 — the tool never guesses** is exactly this rule. The
standard already has the seam for a question detection cannot answer. A
repository names the block in its own `.github/repo-infra.json`:

    { "ci": ["ci-rust-musl"] }

This is the same shape as `publish` (D12/D21 — whether a repository attaches a
tarball or publishes to crates.io) and `build` (D16/D18 — whether it builds in a
container). `references/teaching-the-standard.md` states the rule those two
follow, and it holds here word for word: *"Nothing installs them automatically;
it is a decision, not a detection."*

### Required, not advisory

Once named, the block is not optional in any other sense. Its job joins
`ci-passed`'s generated `needs:` list like every detected block, so a broken
cross-compile blocks the pull request. The whole point is to move the discovery
of a broken musl build from the release to the pull request that caused it; a
job that can fail without blocking anything moves nothing.

D2 makes this free rather than a special case: the ruleset requires exactly one
context, `ci-passed`, and the assembler generates its `needs:` list from the
blocks that went into the file. An add-on block is a block.

### What the seam refuses

`.github/repo-infra.json` is hand-authored, and two mistakes in it are cheap to
make and expensive to read in a generated workflow. `ci_addon_blocks` renders
neither:

- **A block whose ecosystem this repository does not have.** Rendered, a Perl
  repository naming `ci-rust-musl` installs a required job that cannot pass, and
  every pull request in the repository blocks on it. The manifest entry carries
  `"requires": "rust"`, checked against the detected ecosystems.
- **A block detection already installs.** Two blocks declaring the same job id
  make `ci.yml` invalid YAML — so *no* job runs and the required check never
  reports at all, which is worse than a failure because it names YAML rather
  than the config line that caused it. Only entries marked `"optional": true`
  may be named.

Add-ons render **after** the detected blocks, so naming one never reorders the
jobs a repository already has.

## Which targets — fixed, not configurable

`x86_64-unknown-linux-musl` and `aarch64-unknown-linux-musl`, and no
configuration.

Both proven consumers build exactly this pair, and it is the pair that makes the
promise worth making: a binary that runs on any Linux host the user reaches,
whichever of the two architectures it is. A third target is a real but rare
want, and it does not justify a matrix in `.github/repo-infra.json` — one more
per-repository thing to get wrong, of the kind D20 and D21 both deleted rather
than managed.

The repository that needs a third target adds it to its own `ci.yml`, and the
standard is built for that: **D11** measures drift by marker, not content hash,
and `references/conventions.md` names *"an extra matrix target"* among the local
edits a repository is entitled to make. Such a repository stays a healthy `ok`.

## Locating the binary — derived, never named

oxutrm's proven job passes `--bin oxutrm`. The standard cannot carry a name, so
the block builds `--workspace` and asks cargo what it built:

    cargo metadata --format-version 1 --no-deps \
      | jq -r '.packages[].targets[] | select(.kind | index("bin")) | .name'

`--no-deps` resolves nothing and needs no network; the host toolchain
`dtolnay/rust-toolchain@stable` installed is enough. Three cases follow, and the
third is the one that makes the add-on safe for a mixed workspace:

1. **Binaries built.** Each is asserted static.
2. **Binaries declared, none built.** Failure. A build that silently produced
   nothing would otherwise report success by checking nothing, which is the
   exact failure mode the assertion exists to prevent.
3. **No binaries at all.** A notice and exit 0. A library workspace has nothing
   to link statically, and the build still proved the crate compiles for musl.
   A bin behind `required-features` is skipped the same way — it is not produced
   by a plain `--workspace` build, and case 2 still catches a build that
   produced none.

**Not a directory listing of `target/<triple>/release/`.** A cdylib member's
`.so` is a regular executable file too, and `file` calls it a shared object —
which would fail this check for a crate doing nothing wrong.

## The assertion, and why it is an assertion

`RUSTFLAGS="-C target-feature=+crt-static"` is a **hint the linker is free to
ignore**. A tarball that only works on the machine that built it is worse than
no tarball: it fails at the far end, in a session the user cannot see, and reads
as a network fault. So the result is checked, in two halves:

- `file "$BINARY" | grep -q static` — the primary assertion.
- `llvm-objdump -T "$BINARY" | grep GLIBC` must come back empty — the binary
  that is "static" and still reaches for glibc.

The second half is guarded by `command -v llvm-objdump`, so it **skips** where
the tool is absent rather than erroring. That guard is what makes the check
portable across runner images, and it is carried over from oxutrm deliberately.

## cross, not `cargo build --target`

`cargo install cross --version 0.2.5 --locked`, then
`cross build --release --workspace --target <triple>`.

`ring` needs the right assembler for the target and `zstd-sys` needs a C
compiler for it. cross's images carry both; a plain `cargo build --target` on
the runner carries neither, and fails on the first crate that needs either.

The version is pinned, not `main`, for the reason oxutrm records: *a
cross-compile is the thing least likely to be rehearsed locally*, so a break in
a moving dependency arrives in a pull request that is innocent of it.

`dtolnay/rust-toolchain@stable` carries no `targets:` here, unlike oxutrm's
release job. cross compiles inside its own image, which already has the musl std
for the target; the runner's toolchain only runs `cargo install` and
`cargo metadata`. And `@stable` stays a channel reference —
`references/conventions.md` explains why pinning it is the opposite of what the
line is for.

## The one deviation from ci-rust's pattern: no cache

`rust-check` and `rust-test` both carry an `actions/cache` step. This block does
not, and that is deliberate rather than an oversight.

cross writes `target/` from inside a container under its own uid mapping.
Restoring a cache into that path is not part of the recipe this block was proved
from, and `references/teaching-the-standard.md` is explicit that *"a thing
copied from a repository where it works is a hypothesis until it runs against a
real consumer."* Neither proven consumer caches this job.

The cost is real and should be named: `cargo install cross` builds cross from
source on every run of both matrix legs. The block carries a 45-minute timeout
for that reason. Adding a cache is a worthwhile follow-up — with its own proof
run, which this change does not have.

## What is not proved here

The block is assembled, its YAML is parsed, and its linkage assertion is
executed against stand-in `cargo`, `jq` and `file` for all four of its outcomes.
What has **not** run is a real `cross build` under the standard's own assembled
`ci.yml`. The recipe it is built from is in production in `oetiker/oxutrm`, but
per `references/teaching-the-standard.md` stage 2, a first consumer must run
this block as the standard renders it before the decision is settled. `oxutrm`
is the obvious candidate: it already runs the recipe, so converting it changes
the wrapper and not the build.

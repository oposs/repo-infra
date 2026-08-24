# repo-infra — the crates.io publish add-on

Date: 2026-08-24
Extends: `2026-08-17-repo-infra-design.md` (the D-series), Spec 2's add-on table
Proved in: *pending — `oetiker/tvision-rs`*

This document adds one decision, D21, and one publish add-on. It is the second
case worked through the teach path (`references/teaching-the-standard.md`), and
the first where the gap was found by *reading two existing consumers* rather
than by a `detected nothing` report.

## The gap

Spec 2's add-on table carries one line for crates.io:

> crates.io | `cargo publish --locked`; token via `CARGO_REGISTRY_TOKEN` env,
> not `--token` (deprecated)

There are exactly two repositories that actually publish to crates.io, and they
do not agree with each other. The line above describes one of them and predates
the mechanism the other uses.

|  | `oetiker/tvision-rs` | `oetiker/mdmost` |
|---|---|---|
| Auth | Trusted Publishing (OIDC) via `rust-lang/crates-io-auth-action@v1` — no secret | `CARGO_REGISTRY_TOKEN: ${{ secrets.CRATES_IO_TOKEN }}` |
| `--locked` | no | yes |
| Crates published | 2 — `tvision-rs-macros`, then `tvision-rs` | 1 |
| Index propagation | 6 attempts, 30 s backoff | not needed |

`byonk` and `oxulnk` are Rust, but neither is on crates.io; they are binaries.
So the consumer set is these two, and it contains both the single-crate and the
workspace case.

The standard was **silent** on the auth mechanism and on multi-crate ordering,
and in **conflict** with itself on `--locked` — which, as §"The lock file"
below shows, cannot work at all under repo-infra without a further ruling. Both
stage-1 questions were put to the user.

## The rulings

> lets do the teach case and yes lets use the Trusted Publishing aproach

and, on where the lock file gets reconciled, *in the crates.io block*.

## D21 — the standard publishes to crates.io without holding a credential

**Trusted Publishing, not a token.** The block exchanges the job's GitHub OIDC
identity for a short-lived crates.io token via `rust-lang/crates-io-auth-action@v1`.
No `CRATES_IO_TOKEN` secret exists in any repository.

This is the same reasoning Spec 2 already used to refuse hosting apt/yum
repositories: a long-lived credential, stored and rotated per organisation,
"would be the first credential this design introduces". A per-repo crates.io
token is exactly that cost, paid once per publishing repository instead of once
per organisation. Trusted Publishing pays none of it.

**The standard is what makes Trusted Publishing tractable.** crates.io pins a
Trusted Publisher to a *(repository, workflow filename)* pair. repo-infra
renders its publish workflow at one fixed path in every repository it converts:

    .github/workflows/release-publish.yml

So the filename half of the pin is a constant the standard guarantees. An
ad-hoc repository cannot promise that; a converted one gets it for free. This
is the same class of argument as D20's fixed `action-test.yml` path — the rule
deletes the question rather than managing it.

**One invocation for both consumers.** `cargo publish --workspace --locked`
publishes every publishable member in dependency order in a single command.
`xtask`-style helper crates opt out with `publish = false` in their own
manifest, which `tvision-rs` already sets. The standard therefore has no
per-crate list, no ordering configuration, and no hand-rolled retry loop:
`tvision-rs`'s two-step publish plus 6×30 s backoff is what one `--workspace`
invocation is for.

**No artifact is attached to the release.** Every other add-on uploads
something to the draft release. This one publishes to an external registry and
uploads nothing. That is fine and needs no seam change: the seam is `needs:
publish`, the `release_id != ''` guard, and membership in `finalize`'s
generated `needs:` list. The last of those is what matters here — a failed
crates.io publish leaves the GitHub release a **draft**, which is the correct
outcome. A version visible on GitHub but absent from crates.io is the
inconsistency worth preventing.

## The lock file — the ruling that was not obvious

Under repo-infra the release pull request bumps `version_files` by regex and
rolls `CHANGES.md`. It has no Rust toolchain and does not touch `Cargo.lock`.
So at the tagged commit `Cargo.lock` still carries the *previous* version of
the workspace's own crates, and `cargo publish --locked` fails — not
occasionally, but on every release, by construction.

Three places could fix it. The block was chosen.

- **`version_files`** would regex `Cargo.lock`. Rejected: it is a generated
  file whose format cargo does not promise, and `bumpFile` rewrites only the
  first match (`new RegExp(spec.pattern, 'm')` with a non-global `.replace`),
  so a workspace's second crate would silently never be bumped. A spec that
  cannot express the workspace case cannot serve `tvision-rs`.
- **A Rust step in `release-pr.yml`** would install a toolchain in the one
  asset every ecosystem shares, so a Perl repository would install Rust to roll
  its changelog. It also puts a build toolchain on repo-infra's side of the D15
  line, which is where the layering rule says it must not go.
- **The block** — chosen. It is the only job that legitimately has a Rust
  toolchain, because it is the Rust add-on. Nothing about `Cargo.lock` reaches
  `.github/repo-infra.json` or any shared asset.

The block runs `cargo update --workspace` and then `cargo publish --workspace
--locked`. This is `mdmost`'s own proven text, relocated. Its two comments
carry the reasons and must survive the move:

- **`--workspace`, so only the workspace's own entries move.** No dependency is
  re-resolved, which is what makes running it at publish time safe.
- **Not `--offline`.** This job checks out and edits `Cargo.toml` without ever
  fetching the registry; an offline resolve cannot find a single dependency and
  dies on the first one.
- **And no `|| true`.** Swallowing that step's failure is what turned a broken
  step into a broken release: `mdmost` v0.1.1 was tagged with `Cargo.toml` at
  0.1.1 and `Cargo.lock` still at 0.1.0, and the publish failed 6 minutes later.

`--locked` is kept, and it still earns its keep after the update: it guards
every *dependency* pin against drift between the tag and the publish. What it
no longer asserts is the workspace's own version, which is precisely the part
the release pull request is authoritative for.

## The migration hazard

**Converting a repository that already publishes breaks its Trusted Publisher.**
`tvision-rs`'s publisher is registered against `release.yml`. Conversion
replaces that workflow with `release-publish.yml`, and the pin does not follow.
Both crates need a new Trusted Publisher registered on crates.io, by hand,
before the first converted release.

This is manual, outward-facing, per-crate, and lives on crates.io. It belongs
in the conversion checklist for any repository whose `publish` list contains
`publish-crates-io`.

## Open question this creates

**`check` cannot see crates.io.** It queries GitHub. It cannot tell whether a
Trusted Publisher is registered for `release-publish.yml`, so a repository
converts green and fails at its first release — the same shape as the existing
open question about a declared `version_files` path that does not exist. No
mechanism is proposed here; it is recorded so it is not rediscovered.

## What must be proved before this upstreams

Stage 2 is not satisfied by reasoning. Against `oetiker/tvision-rs`, the
workspace consumer:

1. The block runs green with `cargo publish --workspace --locked --dry-run`,
   proving checkout, toolchain, the lock reconciliation, `--locked`, packaging
   and member ordering.
2. `rust-lang/crates-io-auth-action@v1` yields a usable token from a Trusted
   Publisher registered against `release-publish.yml`, proving the pin.
3. A real release publishes both crates in one invocation, proving that
   `--workspace` handles index propagation and that the hand-rolled retry loop
   is genuinely unnecessary.

Step 3 is irreversible: a crates.io version can be yanked but never unpublished.
It needs the user's explicit go, and it is the only step that actually settles
the retry-loop claim.

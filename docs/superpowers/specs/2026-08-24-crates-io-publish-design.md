# repo-infra — the crates.io publish add-on

Date: 2026-08-24
Extends: `2026-08-17-repo-infra-design.md` (the D-series), Spec 2's add-on table
Proved in: `oetiker/tvision-rs`, branch `repo-infra/proof-crates-io`,
[run 32758119138](https://github.com/oetiker/tvision-rs/actions/runs/32758119138)
— green; a real upload is the only step not exercised

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

- **`version_files`** would regex `Cargo.lock`. Rejected — but **not** for the
  reason first given when the question was put to the user, which was that
  `bumpFile` rewrites only the first match (`new RegExp(spec.pattern, 'm')`
  with a non-global `.replace`) and so could never bump a workspace's second
  crate. That is wrong: each spec carries its *own* pattern, and two specs over
  the same file apply in sequence, so one anchored on `name = "tvision-rs"` and
  another on `name = "tvision-rs-macros"` would each hit their own entry. The
  workspace case is expressible.

  The reasons that survive are weaker but real: `Cargo.lock` is a generated
  file whose layout cargo does not promise, and every Rust repository would
  hand-write two brittle multi-line regexes per publishable crate into its own
  `.github/repo-infra.json`. The ruling stands on those; the reader should know
  it was made on one argument that did not.
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
`workflow_filename` is a required part of the pin, so `tvision-rs`'s publisher
-- registered against `release.yml` -- stops matching the moment conversion
renames that workflow to `release-publish.yml`.

It is not a cutover, though. A crate may hold up to `MAX_CONFIGS_PER_CRATE` = 5
publishers, so the new one is *added* beside the old and both crates keep
releasing from `release.yml` until the conversion merges. Nothing has to be
deleted, and no window exists where neither works.

This is manual, outward-facing, per-crate, and lives on crates.io -- one more
config row per publishable crate. It belongs in the conversion checklist for
any repository whose `publish` list contains `publish-crates-io`.

## Open question this creates

**`check` cannot see crates.io.** It queries GitHub. It cannot tell whether a
Trusted Publisher is registered for `release-publish.yml`, so a repository
converts green and fails at its first release — the same shape as the existing
open question about a declared `version_files` path that does not exist. No
mechanism is proposed here; it is recorded so it is not rediscovered.

## What running it found — the defect no test had

The block above is the *second* version. The first one could never have
published anything, and 303 passing tests said it was fine.

`cargo update --workspace` rewrites `Cargo.lock`. `cargo publish` refuses to
package from a tree with uncommitted changes. So the two steps the ruling put
next to each other are in direct conflict, and the job fails **after**
packaging every crate:

    error: 1 files in the working directory contain changes that were not yet
    committed into git

Reproduced against `oetiker/tvision-rs` by constructing exactly the commit
repo-infra produces — `Cargo.toml` at the new version, `Cargo.lock` at the old
one — and running the two commands in order. `mdmost` and `tvision-rs` never
meet this because they reconcile the lock in a *version* job that then commits
and pushes it; repo-infra has no such job, and cannot push to a protected
`main` anyway.

The fix is a local commit of the reconciled lock: the runner is ephemeral,
nothing is pushed, and the commit exists only to make the tree clean. Its one
visible cost is that `.cargo_vcs_info.json` in the published crate names a
commit that exists nowhere but that runner.

**This is D19's lesson one layer further out.** Executing the assets was not
enough, and pointing the tool at a repository it did not author was not enough
either. The block had to be run *in the state the standard actually produces* —
a bumped manifest against an unbumped lock — which is a state no fixture and no
existing consumer ever contains.

The guard that now catches it is behavioural, not textual: the test runs the
step's own shell against a throwaway git tree with a stand-in `cargo` on PATH
and asserts the tree ends clean. A substring assertion cannot do this — `true;
git commit …` still contains every word it would look for, which is exactly how
the first fault injection for it passed while the defect was live.

## What proving it established

Against `oetiker/tvision-rs`, on the constructed release commit:

- `cargo publish --workspace --locked` fails immediately on the unbumped lock,
  before any build. The problem D21 exists to solve is real, not predicted.
- `cargo update --workspace` moved exactly the two workspace entries and left
  110 dependencies untouched, so the restriction that makes the step safe holds
  in practice.
- `cargo publish --workspace --locked --dry-run` then exits 0, packaging and
  building `tvision-rs-macros` first and `tvision-rs` against it. `--workspace`
  handles member ordering with no retry loop and no wait for the index.

One thing this surfaced and did **not** need to solve: an internal dependency
pin (`tvision-rs-macros = { path = …, version = "0.15.0" }`) is not touched by
an anchored `^version` spec, so it drifts behind the crate it pins. Caret
semantics keep it resolving, so it is a quality issue, not a failure — and it
is expressible as one more `version_files` spec in the repository's own config,
which is the right layer for a pattern that names a crate.

## What must still be proved before this upstreams

**D21's central claim is already proved in production.** `oetiker/tvision-rs`
has published every release since 0.15.0 through
`rust-lang/crates-io-auth-action`, with no `CRATES_IO_TOKEN` anywhere. The
mechanism is not a hypothesis; the decision only moves it under the standard.

Local simulation settled the cargo mechanics. What is left is narrower than it
first looked — **one field**.

Verified against crates.io's own source
(`crates/crates_io_api_types/src/trustpub.rs`, `NewGitHubConfig`), a GitHub
trusted publisher is `(crate, repository_owner, repository_name,
workflow_filename, environment?)`. `workflow_filename` is a required,
non-nullable column — "Name of the workflow file inside the repository that
will be used to publish the crate". `tvision-rs`'s own release workflow records
the same fact in a comment: *"Both crates must have a Trusted Publisher
configured on crates.io (repo oetiker/tvision-rs, workflow release.yml)"*.

So conversion breaks the existing pin, because it renames `release.yml` to
`release-publish.yml` — and nothing else about the mechanism changes.

The cutover is safe: `MAX_CONFIGS_PER_CRATE` is **5**
(`src/controllers/trustpub/github_configs/create.rs`), so a second publisher
for `release-publish.yml` sits alongside the existing one. Both crates keep
releasing from `release.yml` until the conversion lands, and no window exists
where neither works.

### The retry loop is provably unnecessary

The last design unknown was whether `--workspace` handles index propagation, or
whether `tvision-rs`'s 6×30 s backoff was carrying weight. Cargo's own source
(`src/cargo/ops/registry/cargo_publish.rs`) settles it — no publish required.

`publish()` builds a `PublishPlan`: a graph of the publishable packages where
"the weight of a package is the number of unpublished dependencies it has". It
then loops, and each round:

- refuses to start at all if `plan.has_cycles()`;
- takes only `packages_ready_to_publish()` — "have no outstanding dependencies";
- uploads those, then calls `wait_for_any_publish_confirmation`, which polls the
  index;
- marks the confirmed ones, unlocking their dependents for the next round.

So dependency ordering and the index wait are cargo's job, done properly. And on
timeout it does not fall through silently:

    unable to publish {failed_list} due to a timeout while waiting for
    published dependencies to be available.

That is strictly better than the hand-rolled loop, which retried a whole `cargo
publish` six times and could not tell "index not ready" from any other failure.
The same file also confirms the `publish = false` opt-out is deliberate: "the
intent is more like 'publish all publisable packages in this workspace', so skip
`publish=false` packages".

### The proof run — green

`oetiker/tvision-rs`, branch `repo-infra/proof-crates-io`. The branch carries
the fixture (`Cargo.toml` at 0.15.1, `Cargo.lock` left at 0.15.0 — exactly what
repo-infra's release pull request produces) and the shipped block **byte for
byte, one line changed**: `--dry-run` appended to the publish. A stub `publish`
job supplies the three outputs, so the block's `needs:`, its `release_id` guard
and its `tag` reference all ran as written.

What the log proves, step by step:

- **Trusted Publishing works from the new filename.** `Retrieving GitHub Actions
  JWT token with audience: crates.io` → `Retrieved JWT token successfully` →
  `Requesting token from: https://crates.io/api/v1/trusted_publishing/tokens` →
  `Retrieved token successfully`. crates.io accepted an OIDC claim naming
  `release-publish.yml`, which is the migration hazard above, closed. The
  action's post step revoked the token.
- **The reconcile is correctly narrow.** `Locking 2 packages`, both workspace
  members, `114 unchanged dependencies behind latest`.
- **The lock commit works on a runner.** Proven by absence: the publish step did
  *not* fail with "files in the working directory contain changes", which is
  exactly how it fails without the commit.
- **`--workspace` orders and verifies both crates.** `Packaging`/`Verifying`
  `tvision-rs-macros` first, then `tvision-rs` against it, then
  `aborting upload due to dry run` twice. Nothing was published.

One thing `--dry-run` cannot reach: the returned token is scoped to the crates
whose publisher configs matched, and a dry run never exercises that scope. If
only one of the two crates had a config, this run would look identical. The
first real release is what settles it — and it fails loudly rather than
silently, so the risk is a failed release, not a wrong one.

A real upload therefore remains the last unexercised step, but no design
question depends on it.

# Rust binaries: a caller chooses the targets

Date: 2026-10-14
Status: proving on the branch `feat/rust-binaries-targets` with oxutrm
Decision: D34 (the first piece input that drops a requirement; names the
pairing D32's "Exceptions" asks of it; changes nothing else in D32 or D33)

## Why

`ri-release-rust-binaries` builds the seven targets of `native-targets` in a
fixed matrix. oxutrm, a remote terminal, needs a pty, `fork`, `setsid` and Unix
sockets and does not build for Windows. With the fixed matrix both Windows legs
fail on every release, so oxutrm could not use the piece at all. The owner
ruled on 2026-10-14 that the standard learns to build fewer targets, instead of
oxutrm carrying a copy of the piece without the Windows legs.

## Decision

D34: `ri-release-rust-binaries` takes an optional input `targets`, a string of
target triples separated by blanks or newlines. Its default names all seven
targets, so a caller that leaves it out builds what it built before, and the
`v2` interface stays compatible. A job `plan` filters the piece's own table of
legs (os, cross, static, windows per target) down to the named targets and
hands the result to the `binaries` matrix; the legs it keeps are unchanged. A
name the table does not hold fails `plan` with one line,
`::error::targets names <names>, which this piece does not build; it builds
<the seven>`, and a value that names nothing fails with `::error::targets names
no target`; no leg starts in either case. The input drops a requirement of the
shape, so a caller that sets it must carry the paired exceptions in
`.github/repo-infra.json`:

| Left out | Exceptions it needs | Why |
|---|---|---|
| any target | `native-targets` | the release lacks an archive the rule requires |
| `x86_64-apple-darwin` or `aarch64-apple-darwin` | also `homebrew` | `ri-release-homebrew` bottles from both mac archives and refuses without them |
| `x86_64-unknown-linux-musl` or `aarch64-unknown-linux-musl` | also `homebrew` and `linux-packages` | the formula carries both musl archives, and `ri-release-nfpm` builds the amd64 and arm64 packages from them |

Leaving out `x86_64-unknown-illumos` or a Windows target needs only
`native-targets`. The exception for `homebrew` or `linux-packages` is more than
a record: the piece behind the rule cannot run without the archives, so the
repository does not call it.

## Who checks what

- The piece checks the names. It does not know the exceptions, which live in
  the calling repository.
- The script does not check the pairing: it does not know rule ids (D32), and
  reading `with:` values of a caller is not its job.
- The shape review checks it (`commands/check.md`, step 4): a call of
  `ri-release-rust-binaries` with `targets` is matched against the table above,
  and a missing exception is reported as an unpaired input. The reason recorded
  for `native-targets` should say which targets are left out and why.

## Rejected

- A list of targets to skip (`skip-targets`). It reads well for oxutrm, but a
  typo in a skip list silently builds everything, and the caller does not see
  the set it gets. A list of targets to build shows that set in the caller.
- An input per target family (`windows: false`). It grows one input per
  family, and the next program that cannot build for illumos needs a new one.
- A second piece without the Windows legs. It is the variant the standard does
  not grow (`references/teaching-the-standard.md`).

## Tests

`tests/test_release_rust_binaries.py` runs the step of `plan` with bash: the
default yields the seven legs, a chosen set yields exactly its legs unchanged
and in table order (blanks, newlines and repeats included), an unknown name
and a value naming nothing fail with the line above. The existing tests of the
build step run once per leg of the default.

## Proof

oxutrm calls the piece at `@feat/rust-binaries-targets` with
`targets: x86_64-unknown-linux-musl aarch64-unknown-linux-musl
x86_64-apple-darwin aarch64-apple-darwin x86_64-unknown-illumos`, with the
paired exceptions recorded, and its release build runs green for the legs it
keeps.

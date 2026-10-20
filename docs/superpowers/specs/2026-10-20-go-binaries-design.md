# Go binaries: the archives of a Go program

Date: 2026-10-20
Status: on the branch `feat/ri-release-go-binaries`; the proof run with
unspammer is open
Decision: D35 (a second binaries piece; extends `native-targets` of D32 to Go
programs and the pairing of D34 to its `targets`; changes nothing in
`ri-release-rust-binaries`)

## Why

unspammer (oposs/unspammer) is a Go program users install. `native-targets`
in `references/project-shape.md` covered a Rust program only, and said that a
program in another compiled language has no rule until a binaries piece exists
for it. Without one, a Go program had no release path in the standard: no
archives, so neither `ri-release-nfpm` nor `ri-release-homebrew` could run for
it. The owner ruled on 2026-10-20 that the standard gets a Go binaries piece.

## Decision

D35: `ri-release-go-binaries` builds the release archives of a Go program. Its
interface is the one of `ri-release-rust-binaries` (`version`, `ref`,
`repository`, `bin`, `targets`) plus two optional inputs:

- `package`: the main package to build, as `go build` takes it; default `.`.
  unspammer passes `./cmd`.
- `version_var`: a string variable the build sets to the version with
  `-ldflags "-X <version_var>=<version>"`, for example `main.version`; empty
  sets none.

The targets keep the Rust triples. They are the names of the archives, and
`ri-release-nfpm` (`archives`), `ri-release-homebrew` (the formula's `url`
lines) and mise's `github:` backend find the archives by them. The piece maps
each to a Go platform:

| Target | GOOS/GOARCH |
|---|---|
| `x86_64-unknown-linux-musl` | `linux/amd64` |
| `aarch64-unknown-linux-musl` | `linux/arm64` |
| `x86_64-unknown-illumos` | `illumos/amd64` |
| `x86_64-apple-darwin` | `darwin/amd64` |
| `aarch64-apple-darwin` | `darwin/arm64` |
| `x86_64-pc-windows-msvc` | `windows/amd64` |
| `aarch64-pc-windows-msvc` | `windows/arm64` |

Every binary is built with `CGO_ENABLED=0`, `-trimpath` and
`-buildvcs=false`. Without cgo the Linux binary links no C library at all, so
it is as static as the musl build of a Rust program, and the musl name
promises what the archive holds. Without cgo `go build` also cross-compiles
to every target, so every leg runs on `ubuntu-latest`; the toolchain is the one
`go.mod` names, through `actions/setup-go` as in `ri-ci-go`.

The `man` job, the archive layout, the artifact names `release-asset-<target>`
and the `plan` job with its two error messages are those of
`ri-release-rust-binaries`. The Windows `.zip` is packed with `zip` on Linux,
with the same folder layout, `<bin>.exe` and no `man/`.

`targets` drops a requirement exactly as in D34, and a call that sets it needs
the same exceptions. The shape review checks the pairing for both pieces.

`ri-release-nfpm` and `ri-release-homebrew` read the archives of either piece.
Their header now names `Pieces: ri-release-rust-binaries or
ri-release-go-binaries`: an entry of `Pieces:` that joins names with `or` is
one requirement that either piece meets. For a build file, `check` reports
such a requirement missing only when every piece it names is absent. A
workflow piece's `Pieces:` was and stays a description; `check` does not
compare it with the jobs of the callers.

## Rejected

- Go platform names (`linux-amd64`) for the archives. `ri-release-nfpm`,
  `ri-release-homebrew`, the formula template and mise all read the Rust
  triples; a second naming scheme would need a second variant of each.
- A cgo build. It needs a C cross toolchain per target and a mac runner for
  darwin, and a Linux binary that links glibc would carry the musl name
  falsely. A Go program that needs cgo is a gap for stage 1.
- One piece for both languages with a `language` input. The two share the
  plan job and the packing but nothing of the build, and every step would
  branch on the input.

## Tests

`tests/test_release_go_binaries.py` runs the step of `plan` with bash and
compares its error output with the one of `ri-release-rust-binaries` for the
same input, checks the target to GOOS/GOARCH table, runs the build step with a
stub `go` for every leg with and without `version_var`, builds a tiny module
with `./cmd` for every leg with the local `go` (skipped without one) and reads
back the platform, `CGO_ENABLED=0`, `-trimpath` and the absence of VCS data
from `go version -m`, and runs the packing step for every leg, the tar.gz and
the zip. `tests/test_check.py` and `tests/test_piece_model.py` cover the `or`
in `Pieces:`.

## Proof

Open: unspammer's release build against `@feat/ri-release-go-binaries`.

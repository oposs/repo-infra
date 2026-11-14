# ri-release-homebrew: the formula names the platforms (#150)

## Intent

lectover ships one mac archive, `aarch64-apple-darwin`, and Linux through
`ri-release-distro-packages`. `ri-release-homebrew` refuses any formula that
lacks one of the four markers `# mac-arm`, `# mac-x86`, `# linux-x86` and
`# linux-arm`, so lectover could only meet `homebrew` with an exception. The
piece should bottle and rewrite a formula for the platforms the project
ships, and keep catching a formula that has lost a platform by mistake.

## Goals

- A formula with only `on_macos` and `on_arm` releases with an arm64 bottle.
- A formula with all four markers behaves as today (mtuspy, mdmost).
- An archive that was built but whose marker is missing from the formula
  still fails the release, as a deleted marker does today.

## Non-goals

- A formula without `# mac-arm`. The bottle is built on `macos-latest`
  (arm64), so `# mac-arm` stays required.
- Glibc Linux archives in the formula. Linux goes through
  `ri-release-distro-packages` or the musl archives.
- Where the archives come from. The piece already reads any artifact named
  `release-asset-*`, so lectover's own `release-build-local.yml` already works.

## Approaches

1. **The formula and the archives agree (chosen).** For each of the four
   targets, the marker is in the formula exactly when the archive
   `<bin>-<version>-<target>.tar.gz` was built. A marker without its archive
   fails ("was not built"); an archive without its marker fails ("the marker
   is gone"). No new input.
2. **The formula alone decides.** Missing markers are skipped and extra
   archives ignored. Simpler, but a marker deleted by mistake goes unnoticed
   and Linux arm users lose the formula with no error.
3. **A `targets` input.** A second place that names the platforms, which can
   drift from the formula. Rejected: the formula already says it.

## Design

- `lib/homebrew.js`: the markers present in the formula are the platforms.
  `# mac-arm` is required. For each of the four targets, marker present and
  archive present must match; both directions fail with the target named.
- Bottle leg (`pointAtArchives`): points only the mac markers present at
  their archives; `# mac-x86` absent means no Intel archive is needed.
- Formula job (`releaseFormula`): rewrites the sha256 of each marker present.
- `references/project-shape.md`: the formula template says a block may be
  left out with its archive; the exceptions table no longer asks `homebrew`
  for a `targets` call that leaves out `x86_64-apple-darwin` or the musl
  targets, only for one that leaves out `aarch64-apple-darwin`.
- `CHANGES.md`: one `### New` entry (#150).

## Left to the builder

- Error message wording, test layout, and whether the agreement check sits
  in one shared function used by both steps.

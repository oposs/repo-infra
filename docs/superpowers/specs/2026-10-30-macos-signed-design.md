# macOS signed: a .pkg or .dmg signed, notarized and stapled

Date: 2026-10-30
Status: on the branch `feat/ri-release-macos-signed`; proven with Mountwell
(run 41058475865) before the review changes, which need a second proof run
Decision: D36 (a release build piece for macOS installers and the rule
`macos-signed` in the project shape)

## Why

Mountwell (moetiker/mountwell) is a Mac app users install from a `.pkg`. No
piece builds for macOS, so its release build was a workflow of its own:
import the Developer ID certificates into a keychain, build, notarize, staple,
check. Up to 0.3.0 its releases shipped unsigned, and every Mac blocked the
download until the user found "Open Anyway" in System Settings. Signing and
notarizing is the same job for every Mac project, and the parts that went
wrong were the same infrastructure, not Mountwell's build:

- `security import` stopped with "MAC verification failed during PKCS12 import
  (wrong password?)": the password secret held a mistyped value. The build had
  already run.
- `notarytool submit` stopped with "HTTP status code: 401. Unauthenticated"
  after a ten-minute build: the key ID and the issuer did not belong to the key.
- Both were fixed by re-running the failed job (`gh run rerun <id> --failed`).
  Dispatching Create release PR again would have collided with the
  `release/vX` branch the failed run left behind.

Mountwell's owner asked on 2026-10-30 for a signing piece, with Mountwell as
its proof; the ruling for the standard is open in the pull request.

## Decision

D36: `ri-release-macos-signed` runs on `macos-26`, checks out `ref`, and:

1. imports the `.p12` of `MACOS_CERTS_P12` with `MACOS_CERTS_PASSWORD` into a
   keychain under `RUNNER_TEMP`, adds it to the search list, writes
   `NOTARY_KEY_P8` to a file and runs `notarytool history` with it, so a wrong
   value fails in seconds and the message names the secret;
   when `assets` names a `.pkg`, it also requires a Developer ID Installer
   identity of the same team, which `find-identity` lists only under `-p basic`;
2. runs the command `build` with `VERSION` and `MACOS_TEAM_ID` in the
   environment;
3. copies the files `assets` names, each a `.pkg` or a `.dmg`;
4. submits every file to the notary service first and then waits for each
   (`notarytool wait`), so their time in the queue overlaps; it fails with the
   service's log when a file is not `Accepted`, and staples the ticket;
5. checks each as a Mac does on download: a `.pkg` with `pkgutil
   --check-signature` (a Developer ID Installer of the team) and `spctl
   --assess --type install`, a `.dmg` with `codesign --verify` (the team) and
   `spctl --assess --type open --context context:primary-signature`, both with
   `stapler validate`;
6. removes the keychain and the key, also after a failure;
7. uploads the files as the artifact `release-asset-macos`.

The build signs and the piece notarizes. Signing has to happen inside the
build: an app goes into a `.pkg` or `.dmg` already signed, with the hardened
runtime, and nested helpers are signed before the bundle. The project knows
that order and the piece does not. Notarization is the same for every file,
so the build needs no notary credentials and no retry logic of its own. The
build finds the identities with `security find-identity`, as it does on a
developer's Mac with the certificates in the login keychain.

The secrets are required, and the piece has no unsigned mode. The first
version had one, switched off by a repository variable
`REQUIRE_SIGNED_RELEASES=1`; unset, a lost secret shipped an unsigned release,
and an app whose updater checks the team ID refuses that package, so every
installed copy stops updating. The shape rule required the variable anyway, so
the review removed the question: a project that cannot sign yet records the
`macos-signed` exception in `.github/repo-infra.json` and does not call the
piece.

The secret names are fixed by the piece (D33: a call passes each secret under
the name of the repository secret it reads). One `.p12` carries both
certificates, Application and Installer, because `security import` takes one
file and the export from Keychain Access writes them together.

The shape gets the rule `macos-signed` (trigger: is installed by users),
which applies only to a program delivered as a `.pkg` or `.dmg`.

## Rejected

- Signing after the build, with `productsign` on a finished `.pkg`. The app
  inside stays unsigned, and notarization refuses a package whose code is not
  signed with the hardened runtime.
- A composite action for the keychain steps, called from the project's own
  workflow. The standard ships reusable workflows; an action would be a second
  kind of piece with its own versioning, and the project would still copy the
  notarize and check steps.
- `.zip` assets. A zip cannot carry a stapled ticket, so a Mac without network
  access rejects what it holds. A command line tool that ships as a zip is a
  gap for stage 1, together with signing the darwin archives of
  `ri-release-rust-binaries` and `ri-release-go-binaries`.
- An unsigned mode behind a repository variable (see Decision).
- An input for the runner. Xcode and the SDK come with the image, and a
  project that needs an older one is a gap for stage 1.

## Traps

- `security set-key-partition-list` must run after the import, or `codesign`
  asks for the keychain password in a dialog and the job hangs to its timeout.
- The keychain must be on the user search list, or `codesign` and
  `productbuild` do not find the identities; the list is extended, not
  replaced, so the login keychain stays reachable.
- Before `gh secret set`, test each value where it will be used: `security
  import` into a scratch keychain for the `.p12` and its password, `xcrun
  notarytool history --key` for the API key, key ID and issuer, and pipe that
  same value into `gh secret set`. A value typed twice is the one that fails.
- A failed release build is re-run with `gh run rerun <id> --failed`, never
  dispatched again.

- `notarytool submit` and `notarytool wait` run with `|| true` and the step
  reads their JSON: under `set -e` a failed call in an assignment ends the step
  before the error line and the service's log are printed.
- `codesign -dv` is read into a variable before `grep`: with `pipefail`,
  `grep -q` closing the pipe early can kill `codesign` with SIGPIPE and fail a
  correctly signed image.
- `nullglob` drops a glob without a match but keeps a plain path, so a plain
  path is checked with `-e`.

## Tests

`tests/test_release_macos_signed.py` runs the import, collect, notarize and
check steps with bash against stubs of `security`, `xcrun`, `pkgutil`, `spctl`
and `codesign` that log their arguments and fail on demand. It covers missing
and partial secrets, a `.p12` that is not base64, a wrong password, a `.p12`
without the Application identity, a `.pkg` without an Installer identity of the
team, a rejected notary key, private key files, the keychain and the team ID,
the asset patterns, a plain path without a file, two assets of one name and a
`.zip`, the submit-then-wait order, a failed submit, an `Invalid` submission
with its log, and a package and an image of another team. It checks that no input is spliced into a script and that the
cleanup runs `always()` before the upload.

## Proof

Mountwell's release build against `@feat/ri-release-macos-signed`, with
`./build.sh` as `build` and `build/Mountwell-*.pkg` as `assets`, replacing its
own `release-build-local.yml`: run
https://github.com/moetiker/mountwell/actions/runs/41058475865.
`Mountwell-0.3.1.pkg` was signed by a Developer ID Installer of team
X52UCY22QK, notarized and stapled (`The staple and validate action worked!`),
and `spctl` reported `accepted`, `source=Notarized Developer ID`.

Open: a second run after the review changes (required secrets, the Installer
check, submit then wait).

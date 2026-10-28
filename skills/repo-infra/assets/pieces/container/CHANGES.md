# container

Upgrade notes, newest first. Each section says what a caller or
.github/repo-infra.json must change to take that version.

## v4

`make check` runs the tests in the container, and driver mode no longer
defines `make test` (#100). In `Makefile.am`, remove the project's own
`test: check` rule and the `if !CONTAINER_DRIVER` and `endif` lines around it.
Scripts and documentation that call `make test` call `make check` instead, as
`ri-ci-perl-autotools` does. `make test-dev TARGET=t/foo.t` is unchanged.

## v3

No change for the repository. The file gained the header block.

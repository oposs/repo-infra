# man

Upgrade notes, newest first. Each section says what a caller or
.github/repo-infra.json must change to take that version.

## v5

No change for a repository with a plain Makefile. An autotools repository
can now include the file from its top-level Makefile.am:

    MAN_NAME = mytool
    include $(top_srcdir)/build/man.mk
    EXTRA_DIST = docs/manual.md build/man.mk build/man-deflist.lua

Replace an `-include` used as a workaround with `include`. A project that
runs automake with `-Werror` adds `-Wno-portability`.

## v4

No change for the repository. The file gained the header block.

#!/bin/sh
# Rebuilds the packages next to this file with nfpm 2.47.0 (the pin in
# .github/workflows/ri-release-nfpm.yml). Usage: NFPM=/path/to/nfpm ./build.sh
# Each package holds one tiny file; the version forms are the ones
# ri-release-distro-packages sets (deb <v>~<codename>, rpm release 1.<dist>,
# apk release 0 with the alpine<major.minor> part in the file name).
set -eu
here=$(cd "$(dirname "$0")" && pwd)
work=$(mktemp -d "${TMPDIR:-/scratch/oetiker/claude-tmp}/gitea-routing.XXXXXX")
echo hi > "$work/hello.txt"
make_one() { # packager version release outname
  cat > "$work/nfpm.yaml" <<YAML
name: tool
arch: amd64
platform: linux
version: "$2"
version_schema: none
release: "$3"
mtime: "2026-01-01T00:00:00Z"
maintainer: Test <test@example.com>
license: MIT
description: fixture
contents:
  - src: $work/hello.txt
    dst: /usr/share/tool/hello.txt
YAML
  "$NFPM" package -f "$work/nfpm.yaml" -p "$1" -t "$here/$4"
}
make_one deb '1.4.0~trixie' 1 tool_1.4.0~trixie-1_amd64.deb
make_one rpm '1.4.0' '1.el9' tool-1.4.0-1.el9.x86_64.rpm
make_one apk '1.4.0' 0 tool-1.4.0-r0-alpine3.24-x86_64.apk
rm -r "$work"

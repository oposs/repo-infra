#!/bin/sh
# facts.sh <package> <directory>: the comparable facts of one .deb or .rpm,
# written as three text files: files (mode and path), control (the fields a
# user sees) and postinst. Sizes, dates and the version are left out, so a
# cargo-deb package of 0.1.3 and an nfpm package of 0.0.0 compare.
set -eu
export LC_ALL=C
package=$1
out=$2
mkdir -p "$out"
case $package in
*.deb)
  dpkg-deb --fsys-tarfile "$package" | tar -tvf - \
    | awk '$1 !~ /^d/ { path = $NF; sub(/^\./, "", path); print $1, path }' | sort > "$out/files"
  dpkg-deb --field "$package" Package Architecture Section Priority Maintainer \
    Depends Recommends Description > "$out/control"
  # A package without a postinst (edaptor v1.8.0) records an empty one.
  if dpkg-deb --ctrl-tarfile "$package" | tar -tf - | grep -qx './postinst'; then
    dpkg-deb --ctrl-tarfile "$package" | tar -xOf - ./postinst > "$out/postinst"
  else
    : > "$out/postinst"
  fi
  ;;
*.rpm)
  rpm -qp --queryformat '[%{FILEMODES:perms} %{FILENAMES}\n]' "$package" | sort > "$out/files"
  rpm -qp --queryformat 'Name: %{NAME}\nArch: %{ARCH}\nLicense: %{LICENSE}\nSummary: %{SUMMARY}\n' \
    "$package" > "$out/control"
  rpm -qp --recommends "$package" | sed 's/^/Recommends: /' >> "$out/control"
  rpm -qp --requires "$package" | sed -n '/^rpmlib(/!s/^/Requires: /p' >> "$out/control"
  rpm -qp --queryformat '%{POSTIN}\n' "$package" > "$out/postinst"
  ;;
*)
  echo "facts.sh: $package is neither .deb nor .rpm" >&2
  exit 1
  ;;
esac

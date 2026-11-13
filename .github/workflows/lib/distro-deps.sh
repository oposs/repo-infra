#!/bin/sh
# distro-deps.sh <family> <stage-dir>
#
# The shared-library dependencies of the ELF files under <stage-dir>, one per
# line, sorted and unique, in the notation of <family> (deb, rpm or apk). Runs
# in the build container of ri-release-distro-packages (D38), whose tools
# stage installs dpkg-dev, rpm-build or pax-utils. POSIX sh: Alpine has no
# bash.
set -eu
# sort -u orders by bytes, so the list is the same in every locale.
export LC_ALL=C

if [ $# -ne 2 ]; then
    echo "usage: distro-deps.sh <deb|rpm|apk> <stage-dir>" >&2
    exit 2
fi
family=$1
stage=$2
case $family in
    deb|rpm|apk) ;;
    *) echo "distro-deps.sh: unknown family $family, expected deb, rpm or apk" >&2; exit 2 ;;
esac
if [ ! -d "$stage" ]; then
    echo "distro-deps.sh: $stage is not a directory" >&2
    exit 2
fi
stage=$(cd "$stage" && pwd)

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

# ELF files by their first four bytes: minimal images have no `file`.
find "$stage" -type f | while IFS= read -r f; do
    if [ "$(od -A n -t x1 -N 4 "$f" | tr -d ' \n')" = 7f454c46 ]; then
        printf '%s\n' "$f"
    fi
done > "$work/elf"

[ -s "$work/elf" ] || exit 0

# The ELF files as arguments; no file name in a stage holds a newline.
set --
while IFS= read -r f; do set -- "$@" "$f"; done < "$work/elf"

# Each tool writes to a file rather than into a pipe: sh has no pipefail, and
# a failing dpkg-shlibdeps must fail the build, not yield an empty list.
case $family in
deb)
    # dpkg-shlibdeps reads debian/control in its working directory, even
    # though -O only prints the result, and warns "binaries to analyze should
    # already be installed in their package's directory" for every file not
    # under a directory holding DEBIAN/. The stage's top entries are linked
    # into such a directory, so the stage itself gets no DEBIAN/.
    root=$work/deb/debian/distro-deps
    mkdir -p "$root/DEBIAN"
    printf 'Source: distro-deps\n\nPackage: distro-deps\nArchitecture: any\n' \
        > "$work/deb/debian/control"
    for entry in "$stage"/* "$stage"/.[!.]*; do
        if [ -e "$entry" ]; then ln -s "$entry" "$root/"; fi
    done
    for f; do
        shift
        set -- "$@" "debian/distro-deps/${f#"$stage"/}"
    done
    (cd "$work/deb" && dpkg-shlibdeps -O "$@") > "$work/out"
    sed -n 's/^shlibs:Depends=//p' "$work/out" | sed 's/, /\n/g' > "$work/deps"
    ;;
rpm)
    /usr/lib/rpm/rpmdeps --requires "$@" > "$work/out"
    # A library the stage ships itself is the package's own. rpmbuild would
    # add the matching Provides; nfpm adds none, so dnf would refuse a
    # package that requires it.
    /usr/lib/rpm/rpmdeps --provides "$@" > "$work/provided"
    grep -v '^rpmlib(' "$work/out" | grep -vxF -f "$work/provided" > "$work/deps" || true
    ;;
apk)
    # #F keeps the file name off each line, which scanelf appends when it
    # reads more than one file.
    scanelf --soname --nobanner --format '%S#F' "$@" > "$work/provided"
    scanelf --needed --nobanner --format '%n#F' "$@" > "$work/out"
    tr ',' '\n' < "$work/out" | sed '/^$/d' > "$work/needed"
    # A soname the stage ships itself is the package's own, not a dependency.
    grep -vxF -f "$work/provided" "$work/needed" | sed 's/^/so:/' > "$work/deps" || true
    ;;
esac

# An XS module is built against the image's perl and works only with that
# perl's API, so the package depends on it as dh_perl makes a deb do.
if grep '/perl.*\.so$' "$work/elf" > /dev/null; then
    if ! command -v perl > /dev/null 2>&1; then
        echo "distro-deps.sh: the stage holds a Perl XS object but the image has no perl" >&2
        exit 1
    fi
    version=$(perl -MConfig -e 'print $Config{version}')
    case $family in
    deb) echo "perlapi-$version" ;;
    rpm) echo "perl(:MODULE_COMPAT_$version)" ;;
    apk) echo "perl~$(echo "$version" | cut -d. -f1,2)" ;;
    esac >> "$work/deps"
fi

sed '/^$/d' "$work/deps" | sort -u

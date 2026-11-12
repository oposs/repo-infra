#!/bin/sh
# distro-dynamic.sh <stage-dir>
#
# Prints true when a file under <stage-dir> is a dynamically linked ELF file:
# one with an interpreter (PT_INTERP) or with a DT_NEEDED entry in its dynamic
# section. Prints false otherwise. distro-leg.sh hands the answer to pack as
# HAS_ELF: such a package must declare dependencies, a static program has
# none. A static PIE, Debian's ldconfig for one, has a dynamic section but
# needs nothing, so the plain ELF magic is not enough.
#
# Reads the headers with od, which every release image has; readelf comes
# with binutils, which the Alpine tools stage lacks. POSIX sh: Alpine has no
# bash.
set -eu

if [ $# -ne 1 ] || [ ! -d "$1" ]; then
    echo "usage: distro-dynamic.sh <stage-dir>" >&2
    exit 2
fi

# The unsigned little-endian integer of $3 bytes at offset $2 of file $1.
le() {
    v=0
    i=0
    for b in $(od -A n -t u1 -j "$2" -N "$3" "$1"); do
        v=$((v + (b << (8 * i))))
        i=$((i + 1))
    done
    echo "$v"
}

# Status 0 when file $1 is a dynamically linked ELF file.
dynamic() {
    [ "$(od -A n -t x1 -N 4 "$1" | tr -d ' \n')" = 7f454c46 ] || return 1
    # Both architectures of the piece are little endian. Any other ELF counts
    # as dynamic, so a package holding one keeps the dependency check.
    [ "$(le "$1" 5 1)" = 1 ] || return 0
    case $(le "$1" 4 1) in
        1) w=4; phoff=$(le "$1" 28 4); phent=$(le "$1" 42 2); phnum=$(le "$1" 44 2)
           off_at=4; size_at=16 ;;
        2) w=8; phoff=$(le "$1" 32 8); phent=$(le "$1" 54 2); phnum=$(le "$1" 56 2)
           off_at=8; size_at=32 ;;
        *) return 0 ;;
    esac
    n=0
    while [ "$n" -lt "$phnum" ]; do
        ph=$((phoff + n * phent))
        case $(le "$1" "$ph" 4) in
            3) return 0 ;;  # PT_INTERP
            2)              # PT_DYNAMIC: entries of tag and value, w bytes each
                dyn=$(le "$1" $((ph + off_at)) "$w")
                end=$((dyn + $(le "$1" $((ph + size_at)) "$w")))
                while [ "$dyn" -lt "$end" ]; do
                    case $(le "$1" "$dyn" "$w") in
                        0) break ;;      # DT_NULL
                        1) return 0 ;;   # DT_NEEDED
                    esac
                    dyn=$((dyn + 2 * w))
                done ;;
        esac
        n=$((n + 1))
    done
    return 1
}

# A file to read from rather than a pipe: sh has no pipefail, and a failing
# find must fail the script. No file name in a stage holds a newline.
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
find "$1" -type f > "$work/files"
while IFS= read -r f; do
    if dynamic "$f"; then echo true; exit 0; fi
done < "$work/files"
echo false

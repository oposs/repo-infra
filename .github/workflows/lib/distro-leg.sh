#!/bin/sh
# distro-leg.sh: one leg of ri-release-distro-packages (D38), one release on
# one architecture, from the release image to a package installed in a clean
# container of that release. Runs on the runner in the project's checkout and
# writes packages/<one file>.
#
# Environment:
#   ENGINE     docker or podman
#   IMAGE      the release image, for example docker.io/library/debian:13
#   DISTRO     the release name in lib/distro.js, for example debian-13
#   ARCH       amd64 or arm64, the architecture of this runner
#   VERSION    the version being released
#   DIRECTORY  the folder with Containerfile, Makefile and the nfpm config (default .)
#   CONFIG     the nfpm config in DIRECTORY (default nfpm.yaml)
#   PACKAGERS  per-family nfpm variables as JSON (default none)
#   LIB        the repo-infra lib folder holding this script
#
# nfpm, node and the read-back tools (dpkg-deb, rpm, tar) come from the runner.
set -eu

die() { echo "distro-leg.sh: $*" >&2; exit 1; }

for name in ENGINE IMAGE DISTRO ARCH VERSION LIB; do
    eval "value=\${$name:-}"
    [ -n "$value" ] || die "$name is empty"
done
DIRECTORY=${DIRECTORY:-.}
CONFIG=${CONFIG:-nfpm.yaml}
PACKAGERS=${PACKAGERS:-}
case $ENGINE in
    docker|podman) ;;
    *) die "ENGINE is $ENGINE: use docker or podman" ;;
esac

family=$(node -e '
const release = require(process.argv[1]).byDistro(process.argv[2]);
if (release) console.log(release.family);' "$LIB/distro.js" "$DISTRO")
[ -n "$family" ] || die "DISTRO $DISTRO is not a release this piece builds"

checkout=$(pwd -P)
[ -f "$checkout/$DIRECTORY/Containerfile" ] || die "no Containerfile in $DIRECTORY"

# The stage is a host folder rather than a volume: nfpm runs on the runner
# and reads the files from there.
work=$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/distro-leg.XXXXXX")
trap 'rm -rf "$work"' EXIT
mkdir "$work/stage" "$work/out"

# Every image is built with no context, as container-make builds it: the
# project's Containerfile names packages and nothing else, and its later
# stages (a D18 project's COPY of the tree and build) are skipped by
# --target build-deps.
tag=localhost/repo-infra-distro-leg-$DISTRO-$ARCH
for stage in repos tools; do
    "$ENGINE" build --build-arg "IMAGE=$IMAGE" --target "$stage" -t "$tag-$stage" - \
        < "$LIB/distro-base.Containerfile" || die "building the $stage stage on $IMAGE failed"
done
"$ENGINE" build --build-arg "BASE=$tag-tools" --target build-deps -t "$tag-build" - \
    < "$checkout/$DIRECTORY/Containerfile" || die "building build-deps of $DIRECTORY/Containerfile failed"

# Runs as root in the build image with the checkout at /src. The mount is
# owned by the runner's user, so git refuses the repository ("detected
# dubious ownership") without the safe entry, and the files root writes are
# handed back to that user afterwards, as build/container-make.mk does; the
# runner could not remove them otherwise. REPO_INFRA_USE_CONTAINER=no keeps a
# container-make project's `make check` from starting a container of its own.
build='set -u
fail() { echo "distro-leg.sh: $*" >&2; exit 1; }
owner=$(stat -c %u /src) && group=$(stat -c %g /src) || fail "cannot stat the checkout at /src"
handback() { find /src /stage /out ! -user "$owner" -exec chown -h "$owner:$group" {} + 2>/dev/null || :; }
trap handback EXIT
printf "[safe]\n\tdirectory = *\n" >> /etc/gitconfig 2>/dev/null || :
if [ -f configure.ac ]; then
    ./bootstrap || fail "./bootstrap failed"
    ./configure --disable-container || fail "./configure --disable-container failed"
fi
make || fail "make failed"
make check || fail "make check failed"
make install DESTDIR=/stage || fail "make install DESTDIR=/stage failed"
[ -n "$(ls -A /stage)" ] || fail "make install wrote nothing under /stage"
sh /ri/distro-deps.sh "$1" /stage > /out/depends || fail "distro-deps.sh found no answer"
# ELF files by their first four bytes, as distro-deps.sh finds them.
find /stage -type f | while IFS= read -r f; do
    if [ "$(od -A n -t x1 -N 4 "$f" | tr -d " \n")" = 7f454c46 ]; then echo true; break; fi
done > /out/has-elf
[ -s /out/has-elf ] || echo false > /out/has-elf
cp /etc/os-release /out/os-release
if [ "$1" = rpm ]; then rpm --eval "%{dist}" > /out/rpm-dist; fi'
"$ENGINE" run --rm --security-opt label=disable -e REPO_INFRA_USE_CONTAINER=no \
    -v "$checkout:/src" -v "$work/stage:/stage" -v "$work/out:/out" -v "$LIB:/ri:ro" \
    -w "/src/$DIRECTORY" "$tag-build" sh -c "$build" sh "$family"

rpm_dist=
if [ "$family" = rpm ]; then rpm_dist=$(cat "$work/out/rpm-dist"); fi
# nfpm's lines go to the log even when pack refuses the package.
status=0
STAGE=$work/stage OS_RELEASE=$work/out/os-release DEPENDS_FILE=$work/out/depends \
    HAS_ELF=$(cat "$work/out/has-elf") RPM_DIST=$rpm_dist CONFIG=$DIRECTORY/$CONFIG \
    PACKAGERS=$PACKAGERS node -e '
const { pack } = require(process.argv[1]);
try {
  for (const line of pack(process.env)) console.log(line);
} catch (error) {
  console.error(`distro-leg.sh: ${error.message}`);
  process.exitCode = 1;
}' "$LIB/distro-pack.js" > "$work/out/pack" || status=$?
cat "$work/out/pack"
[ "$status" -eq 0 ] || exit "$status"
# pack prints "<file>: version <v>, <n> files" for the one file it wrote;
# the lines before it are nfpm's.
file=$(sed -n 's/^\([^ ]*\): version .*/\1/p' "$work/out/pack")

# The repos image has the release's repositories and none of the build
# dependencies, so the install proves the detected dependencies resolve there.
case $family in
    deb) install='apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y "/pkg/$1"' ;;
    rpm) install='dnf install -y "/pkg/$1"' ;;
    apk) install='apk add --allow-untrusted "/pkg/$1"' ;;
esac
"$ENGINE" run --rm --security-opt label=disable -v "$checkout/packages:/pkg:ro" \
    "$tag-repos" sh -ec "$install" sh "$file" || die "installing $file on $DISTRO failed"
echo "distro-leg.sh: installed $file on $DISTRO"

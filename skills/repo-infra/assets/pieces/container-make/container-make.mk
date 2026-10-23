# repo-infra: container-make v1
#
# Purpose: Run `make check` in the image the project's Containerfile builds, for a project without autotools (#94).
# Choose: The tests need tools or root beyond the runner image (D16) and the build is not autotools.
# Supplies: A Containerfile (contract in references/conventions.md) and a Makefile that includes this file first and guards its own `check:` with `ifeq ($(CONTAINER_DRIVER),no)`.
#
# `make check` builds the image from the Containerfile and runs the project's
# own `make check` in it, with the checkout mounted at /src. Every other target
# stays on the host. Inside the container REPO_INFRA_USE_CONTAINER is `no`, the
# driver defines nothing, and the project's own `check:` stands.
#
# Include the file before the project's first rule and guard the project's
# `check:`:
#
#     include build/container-make.mk
#
#     ifeq ($(CONTAINER_DRIVER),no)
#     check:
#             ...
#     endif
#
# The project may set, before or after the include:
#
#   CONTAINER_ENGINE   podman or docker      (default: podman if found, else docker)
#   CONTAINER_TAG      tag of the built image (default: <top-level name>-ci:local)
#   CONTAINER_DEVICES  host devices to pass in, skipped when absent (default: none)
#   CONTAINER_OPTS     extra engine options  (default: none)
#
# Environment:
#
#   REPO_INFRA_USE_CONTAINER   `no` runs the project's check on this machine.
#                              Empty or `yes` drives the container.
#
# The recipes compute every value in the shell at run time. A $(shell ...) at
# parse time would run git and look up the engine on every `make`, `make all`
# included, and break a host that has neither.

ifeq ($(REPO_INFRA_USE_CONTAINER),)
CONTAINER_DRIVER := yes
else ifeq ($(REPO_INFRA_USE_CONTAINER),yes)
CONTAINER_DRIVER := yes
else ifeq ($(REPO_INFRA_USE_CONTAINER),no)
CONTAINER_DRIVER := no
else
$(error REPO_INFRA_USE_CONTAINER is "$(REPO_INFRA_USE_CONTAINER)": use "yes" to run in the container or "no" to run here)
endif

ifeq ($(CONTAINER_DRIVER),yes)

# The rule below would become the default goal when this file is included
# first, and a bare `make` would then run the container instead of the
# project's `all`.
_repo_infra_cm_goal := $(.DEFAULT_GOAL)

CONTAINER_ENGINE ?=
CONTAINER_DEVICES ?=
CONTAINER_OPTS ?=

# Shell functions shared by both recipes. The image tag and the volume name
# depend on whether the project set CONTAINER_TAG; that is passed in as
# REPO_INFRA_CM_TAG, empty when the project left it to the default.
define _repo_infra_cm_lib
set -eu
note() { printf 'container-make: %s\n' "$$*" >&2; }
die() { note "$$*"; exit 1; }
clean() {
	printf '%s' "$$1" | LC_ALL=C tr '[:upper:]' '[:lower:]' \
	  | LC_ALL=C sed -e 's/[^a-z0-9._-]/-/g' -e 's/[._-]\{2,\}/-/g' -e 's/^[._-]*//' -e 's/[._-]*$$//' \
	  | { read -r n || :; echo "$${n:-project}"; }
}
pick_engine() {
	engine=$$REPO_INFRA_CM_ENGINE
	if [ -n "$$engine" ]; then
		case $$engine in
		podman|docker) ;;
		*) die "CONTAINER_ENGINE is $$engine: use podman or docker" ;;
		esac
	elif command -v podman >/dev/null 2>&1; then
		engine=podman
	elif command -v docker >/dev/null 2>&1; then
		engine=docker
	else
		die "no container engine found (podman or docker). Install one, or run the checks on this machine with REPO_INFRA_USE_CONTAINER=no"
	fi
}
locate() {
	top=$$(git rev-parse --show-toplevel 2>/dev/null || pwd -P)
	common=$$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null || :)
	case $$REPO_INFRA_CM_CURDIR in
	"$$top") rel= ;;
	"$$top"/*) rel=$${REPO_INFRA_CM_CURDIR#"$$top"/} ;;
	*) die "$$REPO_INFRA_CM_CURDIR is not below $$top" ;;
	esac
	# A worktree keeps its git directory in the main checkout. Without that
	# directory inside the container, every git command there fails.
	mount_common=
	if [ -n "$$common" ]; then
		case $$common in
		"$$top"/*) ;;
		*) mount_common=$$common ;;
		esac
	fi
	if [ -n "$$REPO_INFRA_CM_TAG" ]; then
		tag=$$REPO_INFRA_CM_TAG
		volume=$$(printf '%s' "$$tag" | sed -e 's/[:/]/-/g')
	else
		tag=$$(clean "$$(basename "$$top")")-ci:local
		if [ -n "$$common" ]; then
			volume=$$(clean "$$(basename "$$(dirname "$$common")")")
		else
			volume=$$(clean "$$(basename "$$top")")
		fi
	fi
	volume=$$volume-ci-home
}
endef

define _repo_infra_cm_check
$(_repo_infra_cm_lib)
pick_engine
case " $$REPO_INFRA_CM_OPTS " in
*--group-add*) die "CONTAINER_OPTS holds --group-add: the driver sets the groups itself" ;;
esac
locate
[ -f "$$REPO_INFRA_CM_CURDIR/Containerfile" ] || die "no Containerfile at $$REPO_INFRA_CM_CURDIR/Containerfile"
if [ "$$engine" = podman ]; then
	"$$engine" build --pull=newer -t "$$tag" - < "$$REPO_INFRA_CM_CURDIR/Containerfile"
elif ! "$$engine" build --pull -t "$$tag" - < "$$REPO_INFRA_CM_CURDIR/Containerfile"; then
	note "pulling the base image failed, building again on the local copy"
	"$$engine" build -t "$$tag" - < "$$REPO_INFRA_CM_CURDIR/Containerfile"
fi
set -- run --rm --init --security-opt label=disable
if [ -t 0 ]; then
	set -- "$$@" -i -t
fi
have_device=
for d in $$REPO_INFRA_CM_DEVICES; do
	if [ -e "$$d" ]; then
		note "device $$d: $$(ls -ld "$$d")"
		set -- "$$@" --device "$$d"
		have_device=yes
	else
		note "device $$d is absent, skipped"
	fi
done
if [ -n "$$have_device" ] && [ "$$engine" = podman ]; then
	info=$$(podman info --format '{{.Host.ServiceIsRemote}} {{.Host.OCIRuntime.Name}}')
	if [ "$$info" = "false crun" ]; then
		set -- "$$@" --group-add keep-groups
	else
		note "podman reports \"$$info\": keep-groups needs a local podman with crun, so the device may be unreadable in the container"
	fi
fi
set -f
set -- "$$@" $$REPO_INFRA_CM_OPTS
set +f
set -- "$$@" -e REPO_INFRA_USE_CONTAINER=no
if [ -n "$$REPO_INFRA_CM_OVERRIDES" ]; then
	set -- "$$@" -e "MAKEFLAGS=-- $$REPO_INFRA_CM_OVERRIDES"
fi
if [ -n "$${CARGO_BUILD_JOBS+x}" ]; then
	set -- "$$@" -e CARGO_BUILD_JOBS
fi
if [ -n "$${RUST_TEST_THREADS+x}" ]; then
	set -- "$$@" -e RUST_TEST_THREADS
fi
set -- "$$@" -v "$$top:/src"
if [ -n "$$mount_common" ]; then
	set -- "$$@" -v "$$mount_common:$$mount_common"
fi
set -- "$$@" -v "$$volume:/root" -w "/src$${rel:+/$$rel}" "$$tag" sh -c "$$REPO_INFRA_WRAPPER" sh /src
if [ -n "$$mount_common" ]; then
	set -- "$$@" "$$mount_common"
fi
rc=0
"$$engine" "$$@" || rc=$$?
case $$rc in
125|126|127)
	note "the engine could not start the container (status $$rc). Podman needs catatonit for --init; install it, or check that the image has a shell"
	;;
esac
exit "$$rc"
endef

define _repo_infra_cm_clean
$(_repo_infra_cm_lib)
pick_engine
locate
if "$$engine" volume inspect "$$volume" >/dev/null 2>&1; then
	"$$engine" volume rm "$$volume"
else
	note "no volume $$volume, nothing to remove"
fi
endef

.PHONY: check container-clean

# The scripts and their inputs reach the shell through the environment, so no
# project value is ever parsed as shell text.
check container-clean: export REPO_INFRA_CM_ENGINE = $(CONTAINER_ENGINE)
check container-clean: export REPO_INFRA_CM_TAG = $(CONTAINER_TAG)
check container-clean: export REPO_INFRA_CM_CURDIR = $(CURDIR)
check: export REPO_INFRA_CM_DEVICES = $(CONTAINER_DEVICES)
check: export REPO_INFRA_CM_OPTS = $(CONTAINER_OPTS)
check: export REPO_INFRA_CM_OVERRIDES = $(filter-out REPO_INFRA_USE_CONTAINER=%,$(MAKEOVERRIDES))
check: export REPO_INFRA_CM_SCRIPT = $(_repo_infra_cm_check)
check: export REPO_INFRA_WRAPPER = make check
container-clean: export REPO_INFRA_CM_SCRIPT = $(_repo_infra_cm_clean)

check:
	@sh -c "$$REPO_INFRA_CM_SCRIPT"

container-clean:
	@sh -c "$$REPO_INFRA_CM_SCRIPT"

.DEFAULT_GOAL := $(_repo_infra_cm_goal)

endif

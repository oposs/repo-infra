# repo-infra: container v1
#
# Autotools as a container driver (D18).
#
# Outside the container this file is the whole build: `make` builds the image,
# and every other target runs in it. Inside the container -- where configure ran
# with --disable-container -- the CONTAINER_DRIVER conditional is false and this
# file defines nothing at all, so the project's own targets stand.
#
# repo-infra owns this file. The project owns its Containerfile and what goes in
# it. Include it from Makefile.am, after calling REPO_INFRA_CONTAINER in
# configure.ac:
#
#     include $(top_srcdir)/build/container.mk
#
# The project may set, before the include:
#
#   CONTAINERFILE     path to the container definition  (default: Containerfile)
#   CONTAINER_TAG     tag to build and run              (default: $(PACKAGE)-build:local)
#   TEST_DEV_MOUNTS   dirs holding interpreted source   (default: none)
#
# There is deliberately no way to declare host packages. Needing one is what
# sent this project to containers in the first place (D16).
#
# In driver mode, every `make` invocation prints two GNU Make warnings:
#
#     Makefile:NNN: warning: overriding recipe for target 'dist'
#     Makefile:NNN: warning: ignoring old recipe for target 'dist'
#
# (and the same pair for `install`). These come from GNU Make itself parsing
# the generated Makefile -- not from automake, so `AUTOMAKE_OPTIONS =
# -Wno-override` does not silence them and must not be added. They are the
# expected sound of this fragment replacing automake's own recipes; they are
# not a sign anything is broken.

CONTAINERFILE ?= Containerfile
CONTAINER_TAG ?= $(PACKAGE)-build:local
TEST_DEV_MOUNTS ?=
TARGET ?=

if CONTAINER_DRIVER

.PHONY: container container-base test test-dev

# The full image. Its build phase runs ./configure --disable-container && make
# && make install, so building the image IS building the project. Always runs:
# podman's layer cache makes a no-change rebuild cheap, and `make test` must
# never test a stale image.
container:
	$(DOCKER) build -t $(CONTAINER_TAG) -f $(top_srcdir)/$(CONTAINERFILE) $(top_srcdir)

# Same image, narrower prerequisite: rebuild only when the container definition
# changes. This is what the dev loop hangs off, so editing a script rebuilds
# nothing.
container-base: .stamp-container-base
.stamp-container-base: $(top_srcdir)/$(CONTAINERFILE)
	$(DOCKER) build -t $(CONTAINER_TAG) -f $(top_srcdir)/$(CONTAINERFILE) $(top_srcdir)
	touch $@

all-local: container

# The seam (D15). Inside the image this is the project's own native test target.
test: container
	$(DOCKER) run --rm $(CONTAINER_TAG) make -C /src test

# The dev loop: one test file, run against the live working tree. Never used by
# CI -- what CI must verify is that the image builds and its contents pass,
# which is `make test`.
test-dev: container-base
	@if [ -z "$(TARGET)" ]; then \
		echo "Error: TARGET is required"; \
		echo "Usage: make test-dev TARGET=t/foo.t"; \
		exit 1; \
	fi
	$(DOCKER) run --rm -it \
		$(foreach d,$(TEST_DEV_MOUNTS),-v $(abs_top_srcdir)/$(d):/src/$(d):ro) \
		$(CONTAINER_TAG) make -C /src test TESTS=/src/$(TARGET)

# The tarball is built by the same toolchain every time. Building it on the host
# instead would let a host-built and an image-built tarball differ, and nobody
# would notice until a user unpacked the wrong one.
dist: container
	$(DOCKER) run --rm -v $(abs_top_builddir):/out $(CONTAINER_TAG) \
		sh -c 'make -C /src dist && cp /src/*.tar.gz /out/'

install: container
	$(DOCKER) run --rm -v $(DESTDIR)$(prefix):/dest $(CONTAINER_TAG) \
		make -C /src install DESTDIR=/dest

clean-local:
	-rm -f .stamp-container-base
	-$(DOCKER) rmi $(CONTAINER_TAG)

endif

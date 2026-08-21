# repo-infra: container-test v1
#
# Run the test suite inside the project's own container image (D16, D17).
#
# repo-infra owns this file. The project owns its Containerfile and what goes
# in it -- which packages, which base image, what the tests do. Include this
# from Makefile.am:
#
#     include $(top_srcdir)/build/container-test.mk
#
# The project may set, before the include:
#
#   CONTAINERFILE  path to the container definition   (default: Containerfile)
#   CONTAINER_TAG  tag to build and test              (default: $(PACKAGE)-test:local)
#   TEST_RUNNER    command run inside the container   (default: prove -v)
#   TEST_DIR       directory holding the .t files     (default: t)
#   SKIP_TESTS     .t file names to exclude           (default: none)
#   DOCKER         container engine                   (default: podman)
#
# There is deliberately no way to declare host packages. Needing one is what
# sent this project to containers in the first place.

DOCKER ?= podman
CONTAINERFILE ?= Containerfile
CONTAINER_TAG ?= $(PACKAGE)-test:local
TEST_RUNNER ?= prove -v
TEST_DIR ?= t
SKIP_TESTS ?=

.PHONY: container test

container:
	$(DOCKER) build -t $(CONTAINER_TAG) -f $(top_srcdir)/$(CONTAINERFILE) $(top_srcdir)

# The test files are enumerated on the host and passed in by name rather than
# globbed inside the container: a glob that matches nothing expands to nothing,
# the runner exits 0, and a suite that ran no tests reports success.
test: container
	@set -eu; \
	skip=""; \
	for s in $(SKIP_TESTS); do skip="$$skip ! -name $$s"; done; \
	files=$$(cd $(top_srcdir)/$(TEST_DIR) && find . -name '*.t' $$skip | sed 's|^\./|/src/$(TEST_DIR)/|' | sort); \
	if [ -z "$$files" ]; then \
		echo "container-test: no test files in $(TEST_DIR)" >&2; \
		exit 1; \
	fi; \
	echo "container-test: $(TEST_RUNNER) on $$(echo $$files | wc -w) files"; \
	$(DOCKER) run --rm \
		-v $(abs_top_srcdir):/src:ro \
		-w /src \
		$(CONTAINER_TAG) \
		$(TEST_RUNNER) $$files

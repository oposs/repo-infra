# No TEST_EXTENSIONS on purpose (D19). Without it automake emits literal
# per-test rules (t/basic.t.log: t/basic.t) instead of a permissive `.t.log:`
# suffix rule. The strict shape is the only one that catches a TESTS= override
# whose path does not match -- the D18 bug where test-dev passed an absolute
# /src/... path and silently ran nothing.
ACLOCAL_AMFLAGS = -I m4
TESTS = t/basic.t
EXTRA_DIST = t/basic.t Containerfile
TEST_DEV_MOUNTS = t
if !CONTAINER_DRIVER
test: check
endif
include $(top_srcdir)/build/container.mk

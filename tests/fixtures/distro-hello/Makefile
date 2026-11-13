# The program the D38 tests build in each distribution container. It links
# zlib, so the dependency detector has a library besides libc to report.
CC ?= cc
# CHECK_FAIL=1 makes `make check` fail, for the test of a leg whose check fails.
CHECK_FAIL ?=

all: hello

hello: hello.c
	$(CC) -O2 -o $@ hello.c -lz

check: hello
	./hello
	test "$(CHECK_FAIL)" != 1

install: hello
	install -d $(DESTDIR)/usr/bin
	install -m 0755 hello $(DESTDIR)/usr/bin/hello

.PHONY: all check install

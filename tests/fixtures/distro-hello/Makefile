# The program the D38 tests build in each distribution container. It links
# zlib, so the dependency detector has a library besides libc to report.
CC ?= cc

all: hello

hello: hello.c
	$(CC) -O2 -o $@ hello.c -lz

check: hello
	./hello

install: hello
	install -d $(DESTDIR)/usr/bin
	install -m 0755 hello $(DESTDIR)/usr/bin/hello

.PHONY: all check install

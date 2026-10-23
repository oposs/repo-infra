# Fixture for the real-engine tests of container-make. The knobs, given on the
# make command line:
#   TEST    text that check writes to check-ran.txt
#   SLEEP   seconds to sleep at the end of check, after printing "fixture: sleeping"
#   FAIL    any value makes check exit 3
#   CACHE   `write` puts /root/marker, `read` fails unless it exists
CONTAINER_DEVICES = /dev/kvm

include build/container-make.mk

all:
	@echo "fixture: all runs on the host"

ifeq ($(CONTAINER_DRIVER),no)
check:
	@test "$$(id -u)" = 0 || { echo "fixture: check did not run as root" >&2; exit 1; }
	@printf '%s\n' "$(TEST)" > check-ran.txt
	@mkdir -p out/sub && echo made > out/sub/file
	@if [ -e /dev/kvm ]; then \
	  sh -c 'exec 3<> /dev/kvm' && echo "fixture: /dev/kvm opens"; \
	else \
	  echo "fixture: no /dev/kvm"; \
	fi
	@git status --short >/dev/null
	@echo "fixture: check ran as root"
	@if [ "$(CACHE)" = write ]; then echo kept > /root/marker; fi
	@if [ "$(CACHE)" = read ]; then test -e /root/marker || { echo "fixture: /root/marker is gone" >&2; exit 1; }; fi
	@if [ -n "$(SLEEP)" ]; then \
	  mkdir -p "interrupted-$(TEST)" && touch "interrupted-$(TEST)/made-by-root"; \
	  echo "fixture: sleeping"; \
	  sleep "$(SLEEP)"; \
	fi
	@if [ -n "$(FAIL)" ]; then exit 3; fi
endif

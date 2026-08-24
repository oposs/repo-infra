.PHONY: test lint check test-container

test:
	python3 -m pytest -q tests

lint:
	python3 -m ruff check skills/repo-infra/scripts tests

check: lint test

# D19: builds a real container and runs the shipped build/container.mk and
# m4/repo-infra-container.m4 against it -- needs podman and takes minutes, so
# it stays out of `test`/`check` and off the sub-second local gate. Run this
# after changing either asset, instead of finding out on the required CI job.
test-container:
	python3 -m pytest -m container -v tests

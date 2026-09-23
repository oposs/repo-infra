.PHONY: test lint check test-container

# `-m` here overrides pytest.ini's addopts, so the pandoc-marked tests run
# locally. The plain `python3 -m pytest` that ci-python runs deselects them,
# since that job installs no pandoc; repo-infra-man runs them on GitHub.
test:
	python3 -m pytest -q -m "not container" tests

lint:
	python3 -m ruff check skills/repo-infra/scripts tests

check: lint test

# D19: builds a real container and runs the shipped build/container.mk and
# m4/repo-infra-container.m4 against it -- needs podman and takes minutes, so
# it stays out of `test`/`check` and off the sub-second local gate. Run this
# after changing either asset, instead of finding out on the required CI job.
test-container:
	python3 -m pytest -m container -v tests

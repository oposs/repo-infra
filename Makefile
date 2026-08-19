.PHONY: test lint check

test:
	python3 -m pytest -q tests

lint:
	python3 -m ruff check skills/repo-infra/scripts tests

check: lint test

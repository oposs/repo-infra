#!/bin/sh
# Automake's default driver judges a test by its EXIT STATUS, not by TAP text.
# The self-test proves the live mount by replacing this with `exit 1`.
echo "1..1"
echo "ok 1"

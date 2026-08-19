# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
except that the first subsection is called `New` rather than `Added`. The release
workflow matches on `### New`; renaming it silently drops the section from the
release notes.

This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### New

- `changes.js`: parse, roll and extract release notes from `CHANGES.md`, with the
  roller validating the file's shape before it writes. The previous implementations
  were single regexes that produced nothing at all on an unexpected shape, and
  "nothing" is indistinguishable from "no changes to release".
- `bump.js`: the generic version-file writer. Every write is located, rewritten and
  then read back and asserted, so a bump that does not take fails the release
  rather than tagging a repository whose files disagree with each other.

### Changed

### Fixed

# Changelog

All notable changes to Vepol will be documented in this file.

This project follows [Semantic Versioning](https://semver.org/) (`MAJOR.MINOR.PATCH`):

- **MAJOR** — incompatible API changes (after 1.0)
- **MINOR** — backwards-compatible feature additions; **may be breaking in 0.x series**
- **PATCH** — backwards-compatible bug fixes

While in `0.x`, expect that any minor version bump may include breaking changes
to scripts, manifest format, or directory layout. Read this changelog before
upgrading.

## [Unreleased]

### Added
- (initial documentation set: README, LICENSE, COMMERCIAL.md, SECURITY.md,
  LICENSE-FUTURE.md, CHANGELOG.md, FUNDING.yml)

### Notes
- This is the initial public release of Vepol. Source code is being migrated
  from the private maintainer staging area in stages — see
  [the spec](https://github.com/nahornyi-ai-lab/vepol/blob/main/concepts/vepol-product.md)
  (when published) for the full plan.

## [0.1.0] — TBD (April 2026)

Initial public release. Includes:

- Core CLI scripts (`bin/`)
- Project template (`_template/`)
- Global Claude Code methodology (`claude/CLAUDE.md`)
- Privacy-aware install / upgrade / uninstall lifecycle
- Demo wiki to see value before learning methodology
- 7 methodology concept pages
- 4-layer leak prevention for maintainers (regex / whitelist / structural / semantic LLM)

### License
- FSL-1.1-MIT — source-available; converts to MIT on the second anniversary
  of this release date.

[Unreleased]: https://github.com/nahornyi-ai-lab/vepol/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/nahornyi-ai-lab/vepol/releases/tag/v0.1.0

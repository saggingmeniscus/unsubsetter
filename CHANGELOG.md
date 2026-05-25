# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-05-25

First public release.

### Added
- Inspect mode (default): reports a per-font plan without writing any files.
- `--fix` mode: writes `*.unsubset.pdf` with full (non-subset) fonts re-embedded.
- CID TrueType (`CIDFontType2`) unsubsetting.
- CID CFF (`CIDFontType0`) unsubsetting, with a glyph-correspondence validation
  pass that aborts the run (exit code 4) if the disk font doesn't match the
  embedded subset.
- `--only` / `--exclude` filters for narrowing which fonts are touched.
- `--verify-visual N` renders N random pages from the input and output and
  pixel-diffs them as a sanity check.
- `--font-path DIR` adds an extra search root for resolving fonts on disk.
- Exit codes: `0` on success or no changes, `4` on CFF glyph-correspondence
  mismatch in the validate phase.

[0.1.0]: https://github.com/saggingmeniscus/unsubsetter/releases/tag/v0.1.0

# Unsubsetter — Design Spec

**Date:** 2026-05-21
**Status:** Draft (awaiting user review)

## Background

Amazon KDP rejected the interior PDF of *The Coast of Everything* with a "font not embedded" complaint against the font `Preciosa`. The font is in fact embedded; the rejection is almost certainly triggered by the font being *subsetted* (a six-letter `ABCDEF+` prefix on the PostScript name marks subset fonts, and KDP's preflight checker is known to flag these as non-embedded). KDP accepts non-subsetted embedded fonts and outlined fonts as alternatives.

The PDF is produced by XeLaTeX and contains 14 embedded fonts; XeLaTeX subsets all of them by default. Ghostscript-based unsubsetting (e.g., `-dSubsetFonts=false`) fails because gs cannot locate the original font files on disk. Outlining the entire PDF produces an unacceptably large file. Acrobat Pro is not available.

## Goal

Build a Python CLI tool, `unsubsetter`, that re-embeds full (non-subset) versions of selected fonts into a PDF, so the output passes KDP's preflight check. The tool must include automated structural verification of its output and a test suite. The immediate target is shipping `the_coast_of_everything.pdf`; the longer-term goal is a reusable utility.

V1 scope is **CID TrueType fonts only**. CFF (Type 0C) and Type 1C fonts are out of scope for V1 and will be reported but skipped.

## Non-goals (V1)

- Outlining glyphs as a fallback. (May come in V2; see "Future work.")
- Handling CFF-based subset fonts (`CIDFontType0`). Out of scope for V1.
- Handling simple (non-composite) Type 1 / Type 1C fonts. Out of scope for V1.
- Working on PDFs not produced by XeLaTeX. Probably works; not a stated requirement.
- A GUI.
- A KDP-style preflight checker. We rely on `pdffonts`-equivalent structural checks as our proxy.

## Constraints and assumptions

- macOS environment (`~/Library/Fonts`, `/Library/Fonts`, `/System/Library/Fonts/`, and TeX Live trees are the font search roots).
- Python 3.11+ (matches the convention of adjacent projects in `~/git/dev/`).
- Dependencies: `pikepdf` (PDF object surgery), `fontTools` (font parsing and width extraction), `click` (CLI). External tool: `pdftoppm` for opt-in visual verification (already installed via Homebrew).
- The CID TrueType fonts in scope are subsetted by XeLaTeX, which preserves original GIDs in the subset font program. This is what makes `CIDToGIDMap = /Identity` a valid replacement choice.

## Architecture

Three-phase pipeline: **Plan → Apply → Verify.** Each phase is independently testable. The plan is the immutable contract between inspection and modification; the applier executes the plan without making decisions; the verifier checks the result against the plan.

### Components

```
src/unsubsetter/
├── __init__.py
├── cli.py          # click entry point
├── font_index.py   # scan font search paths, build name→path map
├── inspector.py    # walk PDF, enumerate font records
├── planner.py      # combine inspection + index + filters → action list
├── applier.py      # execute Replace actions on a pikepdf doc
├── verifier.py     # structural (+ optional visual) post-conditions
└── errors.py       # domain-specific exceptions
```

#### `font_index.py`

- Scans configured search paths once per invocation; default paths: `~/Library/Fonts`, `/Library/Fonts`, `/System/Library/Fonts/Supplemental`, `/System/Library/Fonts`, TeX Live `texmf-dist/fonts/{opentype,truetype}` trees if present.
- Recognizes `.ttf`, `.otf`, `.ttc` files. For `.ttc` (TrueType Collection), each face is indexed separately with its face index.
- For each face, indexes by **three name keys** (all normalized to lowercase with whitespace/punctuation removed):
  1. PostScript name (name table ID 6) — primary key
  2. Full font name (ID 4)
  3. Family name (ID 1) + subfamily (ID 2) concatenated
- Returns `FontIndexEntry(path: Path, ttc_face: int | None, ps_name: str, full_name: str, family_subfamily: str)`.
- Cached on disk to `~/.cache/unsubsetter/font_index.json` keyed on `(path, mtime)` tuples; invalidation is automatic when any indexed file's mtime changes.
- `--verbose` dumps the resolved index entries that match a given query.

Naming note: PDF PostScript names may contain spaces (e.g., `ZILMPO+Horst Regular`) where the disk font's PostScript name lacks them. The normalization step (lowercase + strip non-alphanumeric) handles this.

#### `inspector.py`

- Input: an open `pikepdf.Pdf` object.
- Walks the document's font objects (via `Pdf.objects` or `Page.resources.Font` traversal — both paths exist; the global object traversal is more reliable for catching fonts that appear via inheritance).
- For each font dict, extracts a `FontRecord`:
  ```python
  @dataclass(frozen=True)
  class FontRecord:
      font_obj: pikepdf.Object          # handle to the font dict in the Pdf
      base_font: str                    # raw /BaseFont value
      subset_prefix: str | None         # six-letter prefix without the '+', or None
      ps_name: str                      # base_font with prefix stripped
      subtype: str                      # 'Type0', 'TrueType', 'Type1', etc.
      descendant_subtype: str | None    # 'CIDFontType2', 'CIDFontType0', or None for non-Type0
      encoding: str                     # raw or named encoding identifier
      has_font_file: bool               # True if FontDescriptor has FontFile/FontFile2/FontFile3
      font_file_kind: str | None        # 'FontFile2', 'FontFile3', etc.
      used_cids: frozenset[int]         # all CIDs referenced in content streams for this font
  ```
- Idempotency: if the font is already non-subset (`subset_prefix is None`), it is still reported but the planner will skip it.
- `used_cids` is populated by scanning each page's content stream once during inspection, tracking the current font via `Tf` operators and accumulating string-operator (`Tj`, `TJ`, `'`, `"`) argument bytes — which under Identity-H are 2-byte CIDs.

#### `planner.py`

- Input: `[FontRecord, ...]`, `FontIndex`, filter options (`only`, `exclude`, `all_types`).
- Output: `Plan` = `list[Action]` where `Action = Replace | Skip`.
- A font becomes a `Replace` action iff:
  - It has a `subset_prefix` (i.e., it's actually subsetted), AND
  - Its `subtype == 'Type0'` and `descendant_subtype == 'CIDFontType2'` (the CID TrueType case), AND
  - It is not excluded by `--only` / `--exclude` filters, AND
  - `font_index.resolve(ps_name)` returns a hit.
- Otherwise it becomes a `Skip` action with a structured reason:
  - `"not subsetted"`
  - `"unsupported type: CIDFontType0 (CFF)"`
  - `"unsupported type: Type1"`
  - `"excluded by --exclude"`
  - `"not selected by --only"`
  - `"font not found on disk: <ps_name>"`
- The planner has no side effects.
- `Plan.render()` produces the human-readable `--check` report.

```python
@dataclass(frozen=True)
class Replace:
    record: FontRecord
    source_path: Path
    ttc_face: int | None

@dataclass(frozen=True)
class Skip:
    record: FontRecord
    reason: str
```

#### `applier.py`

- Input: an open `pikepdf.Pdf`, a `Plan`.
- For each `Replace` action:
  1. Load the full font binary from `source_path` (selecting TTC face if applicable, via `fontTools.ttLib.TTFont(path, fontNumber=ttc_face)` and re-emitting to bytes — needed so the embedded stream is a standalone TTF, not a TTC).
  2. Open the font object dict and its descendant CIDFont dict.
  3. Read existing CIDs referenced in the document for this font (collected once during inspection, passed in via the action) — needed for the width-array rebuild.
  4. Replace the `FontFile2` stream payload with the full font binary; preserve dict keys like `/Length1`.
  5. Strip the `XXXXXX+` prefix from `BaseFont` on both the Type0 dict and the descendant CIDFont dict.
  6. Set `descendant.CIDToGIDMap = pikepdf.Name('/Identity')`. (Justification: XeLaTeX-generated TrueType subsets preserve original GIDs, so CID == GID in the full font.)
  7. Rebuild the `/W` (widths) array from the full font's `hmtx` table. Conservatively emit widths for every CID referenced in the existing content streams plus any in the original `/W`; format as ranges where consecutive CIDs share a width.
  8. Update FontDescriptor metrics — `Ascent`, `Descent`, `CapHeight`, `XHeight`, `ItalicAngle`, `StemV`, `FontBBox`, `Flags` — from the full font's `OS/2`, `hhea`, and `post` tables. (Stale subset metrics may differ slightly and are a known cause of subtle rendering drift.)
- Output is written atomically: pikepdf serializes to a tempfile in the target directory, then `os.replace()` to the final path.

**CID collection:** the inspector populates `FontRecord.used_cids` (see above) before the planner runs, so each `Replace` action carries the CID set the applier needs for width-array sizing. Implementation via `pikepdf.parse_content_stream` or page-level content stream iteration; tracks the current font via `Tf` operators and accumulates 2-byte CIDs from `Tj`/`TJ`/`'`/`"` string operands while that font is current.

#### `verifier.py`

- Input: original PDF path, modified PDF path, the `Plan` that was applied.
- Structural checks (always run after `--fix`):
  1. Both PDFs open without warnings via pikepdf.
  2. Page count matches.
  3. For each page, MediaBox matches.
  4. For each `Replace` action: in the modified PDF, the corresponding font object has no subset prefix, `CIDToGIDMap == /Identity`, `FontFile2.Length1 > original.FontFile2.Length1` (the full font is larger than the subset), and the descendant `/W` array exists.
  5. For each `Skip` action: the font object is bit-for-bit unchanged (same `/BaseFont`, same `FontFile2` stream length, same `/W`).
- Optional visual checks (`--verify-visual=N`):
  - Pick N random page indices.
  - Render each via `subprocess.run(['pdftoppm', '-r', '150', '-f', str(p), '-l', str(p), input_pdf, prefix])` from both PDFs.
  - Compare pixel-by-pixel with a tolerance (default: max per-pixel diff ≤ 3/255, total differing pixels ≤ 0.1% of image area).
  - Report any page that exceeds tolerance with its page number.
- Returns `VerificationReport(passed: bool, checks: list[CheckResult])`.

#### `cli.py`

Click entry point:

```
unsubsetter [OPTIONS] INPUT_PDF

Options:
  --fix                     Write output. Without this, runs in inspect-only mode.
  --output PATH             Output path (default: INPUT.unsubset.pdf)
  --force                   Allow overwriting INPUT_PDF
  --only NAMES              Comma-separated PostScript names to include (case-insensitive,
                            matched with or without subset prefix)
  --exclude NAMES           Comma-separated PostScript names to skip
  --font-path PATH          Additional font search dir (may be repeated)
  --verify-visual N         After fix, render N random pages from input and output
                            and pixel-diff them (requires pdftoppm)
  -v, --verbose             Verbose logging (dumps resolved font index entries)
  --version
  --help
```

Default behavior (no `--fix`) prints the plan and exits 0.

## Data flow

```
INPUT.pdf ── pikepdf.open ──► Pdf
                                │
                                ▼
                          inspector ──► [FontRecord, ...]
                                              │
font search paths ──► font_index ─────────────┤
                                              ▼
filter flags ────────────────────────────► planner ──► Plan = [Action, ...]
                                                          │
                                                          ├─ default mode ──► render to stdout, exit 0
                                                          │
                                                          └─ --fix mode ──► applier ──► OUTPUT.pdf (atomic)
                                                                                  │
                                                                                  ▼
                                                                              verifier
                                                                                  │
                                                                                  ▼
                                                                          report → stdout
                                                                          exit 0 if passed, 2 if failed
```

## Error handling

| Situation | Behavior |
|---|---|
| Input file missing | Exit 1, error to stderr |
| Input not a PDF | Exit 1, error to stderr |
| Font not found on disk | `Skip` action with reason; `--check` shows it, `--fix` proceeds with other fonts |
| Unsupported font type (CFF/Type1) | `Skip` action with reason |
| TTC file found but PS name doesn't match any face | `Skip` action with reason |
| Apply step raises mid-PDF | Tempfile discarded; output file not written; exit 2 with traceback only in `--verbose` |
| Verification fails (structural) | Output file kept; failing checks printed; exit 2 |
| Verification fails (visual diff exceeds tolerance) | Output file kept; failing page numbers printed; exit 3 (different code to distinguish from structural failure) |

The applier writes to a tempfile in the output directory and uses `os.replace` for atomicity, so a crashed run can never leave a corrupt PDF at the target path.

## Testing strategy

### Unit tests (`tests/unit/`)

- `test_font_index.py` — populate a `tmp_path` with synthetic TTF/OTF/TTC files (built via fontTools at test setup time, never committed), assert resolution by PostScript name, full name, family+subfamily, with normalization (case, whitespace, punctuation).
- `test_inspector.py` — read a committed tiny fixture PDF, assert `FontRecord` fields including subset prefix detection, `used_cids` collection.
- `test_planner.py` — given hand-constructed `FontRecord` lists + a stub `FontIndex`, assert correct `Action` lists under every filter combination and every `Skip` reason.
- `test_verifier.py` — synthetic before/after pikepdf docs; assert structural checks catch missing-prefix-strip, missing-CIDToGIDMap-update, page count mismatch, MediaBox mismatch.

### Integration tests (`tests/integration/`)

- `test_pipeline.py` — fixture: `tests/fixtures/tiny_book.pdf` (committed binary, generated from `tests/fixtures/tiny_book.tex` which is also committed). The .tex uses one CID TrueType font we know we have on disk (e.g., a font we ship in the test data, or a TeX-distributed one like Junicode).
  - Run `--check` on it, assert plan shape.
  - Run `--fix`, assert output PDF parses, fonts are no longer subset, verifier passes.
  - Idempotency: run `--fix` on the output, assert plan contains only `Skip(reason="not subsetted")`.
  - Filter behavior: `--only`, `--exclude` produce expected plan shapes.
- `test_visual_verify.py` — run `--fix --verify-visual=1` and assert it produces no diffs above tolerance.

### Acceptance procedure (manual, documented in README)

Not in CI, but the README will document this as the pre-upload gate:

1. `unsubsetter ~/git/books/the_coast_of_everything/the_coast_of_everything.pdf` (check mode) — verify plan covers Preciosa and the other CID TrueType fonts, report any `Skip` reasons that are surprising.
2. `unsubsetter --fix --verify-visual=10 ~/git/books/the_coast_of_everything/the_coast_of_everything.pdf` — produces `the_coast_of_everything.unsubset.pdf`; visual diff samples 10 random pages.
3. Manually run `pdffonts the_coast_of_everything.unsubset.pdf` and confirm `sub=no` on Preciosa and the other targeted fonts.
4. Manually spot-check 5 pages in a PDF viewer (drop-cap pages, math pages with CMSY7, ornaments).
5. Upload to KDP.

## Project layout

```
unsubsetter/
├── pyproject.toml          # uv-managed, src layout, [project.scripts] entry
├── README.md
├── docs/
│   └── superpowers/specs/2026-05-21-unsubsetter-design.md  # this file
├── src/
│   └── unsubsetter/
│       ├── __init__.py
│       ├── cli.py
│       ├── font_index.py
│       ├── inspector.py
│       ├── planner.py
│       ├── applier.py
│       ├── verifier.py
│       └── errors.py
└── tests/
    ├── conftest.py
    ├── fixtures/
    │   ├── tiny_book.tex
    │   ├── tiny_book.pdf
    │   └── README.md         # how to regenerate fixtures
    ├── unit/
    │   ├── test_font_index.py
    │   ├── test_inspector.py
    │   ├── test_planner.py
    │   └── test_verifier.py
    └── integration/
        ├── test_pipeline.py
        └── test_visual_verify.py
```

Adjacent project convention (matches `~/git/dev/asterism_utils`): `uv`-managed, `src/` layout, `click` for CLI, `[project.scripts]` entry, `pytest` for tests, hatch as the build backend.

## Future work (post-V1)

- **CFF (`CIDFontType0`) unsubsetting.** Harder because CFF subsetting renumbers glyphs. Approach: rebuild the CMap to map original CIDs to full-font GIDs after subsetting is removed. The two affected fonts in `the_coast_of_everything.pdf` (`P22PreissigCalligraphic-Reg`, `BradleyInitials`) are drop caps, so for V1 the user will either accept them as-is or apply the page-splice/outline workaround for those specific pages.
- **Outline-glyphs fallback.** When the full font cannot be found on disk, an `Outline` action converts the subset's glyphs to vector paths inline in the content stream. Implemented via fontTools' `Pen` API plus pikepdf content-stream rewriting, or as a subprocess to `gs -dNoOutputFonts` scoped to specific pages.
- **Simple Type 1 unsubsetting.** Requires handling builtin encoding and Type 1 charstrings — structurally different from the Type 0 case.
- **Linux font search paths** (`/usr/share/fonts`, `~/.fonts`, fontconfig).
- **Selective outline mode**: `unsubsetter --outline FONT,FONT2 book.pdf` outlines only specific fonts on the pages that use them.

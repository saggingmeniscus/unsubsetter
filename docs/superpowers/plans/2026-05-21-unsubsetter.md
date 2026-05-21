# Unsubsetter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python CLI tool, `unsubsetter`, that re-embeds full (non-subset) versions of CID TrueType fonts in PDFs so Amazon KDP's preflight check accepts them. V1 ships in time to unblock *The Coast of Everything*.

**Architecture:** Three-phase pipeline — **Plan** (inspect PDF + resolve fonts on disk + filter → action list) → **Apply** (execute Replace actions on a pikepdf doc) → **Verify** (structural + optional visual checks). Each phase is independently testable. The plan is the immutable contract between inspection and modification.

**Tech Stack:** Python 3.11+, `uv` for env management, `pikepdf` (PDF object surgery), `fontTools` (font parsing + emit), `click` (CLI), `pytest` (tests), `Pillow` (pixel diff for visual verifier), `pdftoppm` (Poppler, external; opt-in visual verification).

**Spec:** `docs/superpowers/specs/2026-05-21-unsubsetter-design.md`

**Repo state:** Spec committed at `8ebd8f4`. No source code yet.

**Deliberate deferrals from the spec:** The spec mentions caching the font index to `~/.cache/unsubsetter/font_index.json`. This plan does *not* implement the disk cache. Rationale: indexing the user's font directories takes ~1–3 seconds and only runs once per invocation; disk caching adds a moving part (mtime-keyed invalidation) for marginal user-visible benefit. The `FontIndex.build` API is structured so a `from_cache` / `to_cache` pair can be slotted in later without changing the rest of the system.

---

## Background reading for the implementer

You probably haven't worked with embedded PDF fonts before. The 90-second tour:

- **A PDF font dict** has `/Subtype` (`Type0` for composite, `Type1`/`TrueType` for simple), `/BaseFont` (PostScript name), `/Encoding`, and a `/FontDescriptor`. For Type 0 fonts there's also `/DescendantFonts` (a one-element array pointing to the CIDFont).
- **A subsetted font** has a six-uppercase-letter prefix and a `+` on `/BaseFont`, e.g. `ABCDEF+Preciosa`. The same prefix appears on the descendant CIDFont's `/BaseFont`. The font program lives in `/FontDescriptor/FontFile2` (for TrueType) as a binary stream.
- **CID TrueType** = `/Subtype Type0` + `/DescendantFonts[0]/Subtype CIDFontType2`. Identity-H encoding means content-stream strings are raw 2-byte big-endian CIDs, and the descendant CIDFont's `/CIDToGIDMap` (a stream or `/Identity`) maps those CIDs to glyph indices in the TTF.
- **The XeLaTeX TrueType subsetter preserves original GIDs.** So in a subset font, CID `N` maps to GID `N` in the original full font. That's why we can set `CIDToGIDMap = /Identity` when we swap in the full font.
- **`pikepdf` is the Python binding to qpdf.** `pikepdf.Pdf.open(path)` gives you a `Pdf` object. `pdf.objects` iterates all objects; you can read/write dict entries with attribute access (`obj.BaseFont`) or `obj['/BaseFont']`. Streams are `pikepdf.Stream` — read via `.read_bytes()`, write via `.write(new_bytes)`.
- **`fontTools.ttLib.TTFont(path)`** parses a TTF/OTF. For a `.ttc` collection, pass `fontNumber=N`. Tables include `name` (font names), `hmtx` (horizontal metrics, including widths), `OS/2` (cross-platform metrics), `hhea` (ascender/descender), `head` (bounding box). After parsing, `tt.save(BytesIO)` writes a flat TTF.

When in doubt, write a small smoke script in `tmp/` to poke at a real PDF or font and inspect what you get. Don't guess at API shapes — verify.

---

## File structure

```
unsubsetter/
├── pyproject.toml
├── README.md
├── .gitignore                  # already exists
├── docs/                       # already exists
├── src/
│   └── unsubsetter/
│       ├── __init__.py
│       ├── cli.py
│       ├── errors.py
│       ├── font_index.py
│       ├── inspector.py
│       ├── planner.py
│       ├── applier.py
│       └── verifier.py
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── fixtures/
    │   ├── README.md
    │   ├── tiny_book.tex
    │   └── tiny_book.pdf       # committed binary
    ├── unit/
    │   ├── __init__.py
    │   ├── test_font_index.py
    │   ├── test_inspector.py
    │   ├── test_planner.py
    │   ├── test_applier.py
    │   └── test_verifier.py
    └── integration/
        ├── __init__.py
        ├── test_pipeline.py
        └── test_visual_verify.py
```

**Test approach:** unit tests synthesize TTF/PDF fixtures in `tmp_path` via `fontTools.fontBuilder` and `pikepdf` directly — no shipped binary fixtures except `tiny_book.pdf`. Integration tests run the full pipeline against `tiny_book.pdf`.

---

## Task 1: Project setup

**Files:**
- Create: `pyproject.toml`
- Create: `src/unsubsetter/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/unit/__init__.py`
- Create: `tests/integration/__init__.py`
- Create: `tests/conftest.py`
- Create: `README.md`

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "unsubsetter"
version = "0.1.0"
description = "Re-embed full (non-subset) fonts in PDFs."
authors = [{name = "Jacob Smullyan", email = "smulloni@smullyan.org"}]
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
    "pikepdf>=9.0",
    "fonttools>=4.50",
    "click>=8.1",
]

[project.scripts]
unsubsetter = "unsubsetter.cli:cli"

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-cov>=5.0",
    "ruff>=0.4",
    "pillow>=10.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/unsubsetter"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra"

[tool.ruff]
line-length = 100
target-version = "py311"
```

- [ ] **Step 2: Create package and test skeleton**

`src/unsubsetter/__init__.py`:
```python
"""Re-embed full (non-subset) fonts in PDFs."""
__version__ = "0.1.0"
```

`tests/__init__.py`, `tests/unit/__init__.py`, `tests/integration/__init__.py`: empty files.

`tests/conftest.py`:
```python
"""Shared pytest fixtures."""
```

`README.md`:
```markdown
# unsubsetter

Re-embed full (non-subset) fonts in PDFs so Amazon KDP's preflight check accepts them.

See `docs/superpowers/specs/2026-05-21-unsubsetter-design.md` for design.

## Install

    uv sync --extra dev

## Run

    uv run unsubsetter --help

## Tests

    uv run pytest
```

- [ ] **Step 3: Install everything**

```bash
uv sync --extra dev
```

Expected: virtual env at `.venv/`, `uv.lock` generated, `pikepdf`/`fonttools`/`click`/`pytest` installed.

- [ ] **Step 4: Verify pytest runs**

```bash
uv run pytest -q
```

Expected: `no tests ran in 0.0?s` (exit 5 — fine; just confirming pytest is wired).

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/ tests/ README.md uv.lock
git commit -m "Bootstrap unsubsetter project (uv, pikepdf, fontTools, click)"
```

---

## Task 2: Tiny fixture PDF for integration tests

**Files:**
- Create: `tests/fixtures/tiny_book.tex`
- Create: `tests/fixtures/tiny_book.pdf` (committed)
- Create: `tests/fixtures/README.md`

- [ ] **Step 1: Write the LaTeX source**

`tests/fixtures/tiny_book.tex`:
```latex
\documentclass[11pt]{article}
\usepackage{fontspec}
\setmainfont{EB Garamond}
\pagestyle{empty}
\begin{document}
\section*{Hello}
This is a tiny test document with embedded fonts.
The quick brown fox jumps over the lazy dog.
Pack my box with five dozen liquor jugs.
\end{document}
```

- [ ] **Step 2: Generate the PDF**

```bash
cd tests/fixtures && xelatex -interaction=nonstopmode tiny_book.tex && rm -f tiny_book.aux tiny_book.log tiny_book.out && cd -
```

Expected: `tests/fixtures/tiny_book.pdf` exists, ~30KB.

- [ ] **Step 3: Verify the fixture has a subsetted CID TrueType font**

```bash
pdffonts tests/fixtures/tiny_book.pdf
```

Expected output includes a line like:
```
XXXXXX+EBGaramond-Regular   CID TrueType  Identity-H  yes  yes  yes  ...
```

The six-letter prefix will vary. If `sub=no`, the document is too small to trigger subsetting — add more text and regenerate.

- [ ] **Step 4: Write the fixture README**

`tests/fixtures/README.md`:
```markdown
# Test fixtures

## tiny_book.pdf

A minimal XeLaTeX-generated PDF with one subsetted CID TrueType font, used by
integration tests in `tests/integration/test_pipeline.py`.

Regenerate from `tiny_book.tex`:

    cd tests/fixtures
    xelatex tiny_book.tex
    rm -f tiny_book.aux tiny_book.log tiny_book.out

Requirements to regenerate: XeLaTeX (TeX Live) and the `EB Garamond` font
installed system-wide (the user has `~/Library/Fonts/EBGaramond-Regular.ttf`).
If you substitute a different font, update the `EXPECTED_SUBSET_FONT_PS_NAME`
constant in `tests/integration/test_pipeline.py`.
```

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/
git commit -m "Add tiny_book.pdf XeLaTeX fixture for integration tests"
```

---

## Task 3: `errors.py` — domain exception types

**Files:**
- Create: `src/unsubsetter/errors.py`

No tests for this — pure exception type declarations.

- [ ] **Step 1: Write the module**

`src/unsubsetter/errors.py`:
```python
"""Domain-specific exception types for unsubsetter."""


class UnsubsetterError(Exception):
    """Base class for all unsubsetter errors."""


class FontNotFoundError(UnsubsetterError):
    """A font referenced in the PDF could not be located on disk."""


class UnsupportedFontError(UnsubsetterError):
    """A font is of a type V1 doesn't handle (CFF, simple Type 1, etc.)."""


class VerificationError(UnsubsetterError):
    """Post-write verification of the output PDF failed."""
```

- [ ] **Step 2: Commit**

```bash
git add src/unsubsetter/errors.py
git commit -m "Add domain exception types"
```

---

## Task 4: `font_index.normalize_name`

**Files:**
- Create: `src/unsubsetter/font_index.py`
- Create: `tests/unit/test_font_index.py`

- [ ] **Step 1: Write failing tests**

`tests/unit/test_font_index.py`:
```python
from unsubsetter.font_index import normalize_name


def test_normalize_name_lowercases():
    assert normalize_name("Preciosa") == "preciosa"


def test_normalize_name_strips_spaces():
    assert normalize_name("Horst Regular") == "horstregular"


def test_normalize_name_strips_punctuation_and_underscores():
    assert normalize_name("EB-Garamond_Regular") == "ebgaramondregular"


def test_normalize_name_does_not_strip_subset_prefix():
    # Subset prefix stripping is the inspector's job, not normalize_name's,
    # so the rule lives in one place.
    assert normalize_name("ABCDEF+Preciosa") == "abcdefpreciosa"
```

- [ ] **Step 2: Run, verify fail**

```bash
uv run pytest tests/unit/test_font_index.py -v
```

Expected: ImportError or "cannot import name 'normalize_name'".

- [ ] **Step 3: Implement**

`src/unsubsetter/font_index.py`:
```python
"""Font index: scans font search paths and resolves font names to disk files."""
from __future__ import annotations
import re

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize_name(name: str) -> str:
    """Normalize a font name for indexing: lowercase + strip non-alphanumeric."""
    return _NON_ALNUM.sub("", name.lower())
```

- [ ] **Step 4: Run, verify pass**

```bash
uv run pytest tests/unit/test_font_index.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/unsubsetter/font_index.py tests/unit/test_font_index.py
git commit -m "Add normalize_name for font lookup keys"
```

---

## Task 5: `tests/conftest.py` — synthetic font builder

To unit-test the index without depending on installed system fonts, we need to build tiny TTFs in `tmp_path`. fontTools' `fontBuilder` is the right tool.

**Files:**
- Modify: `tests/conftest.py`

- [ ] **Step 1: Add the builder fixture**

Replace `tests/conftest.py` with:

```python
"""Shared pytest fixtures."""
from __future__ import annotations
from io import BytesIO
from pathlib import Path

import pytest
from fontTools.fontBuilder import FontBuilder


def _build_minimal_ttf(
    ps_name: str,
    family: str = "TestFamily",
    subfamily: str = "Regular",
    full_name: str | None = None,
) -> bytes:
    """Build a minimal but valid TTF with the given names. Returns binary bytes."""
    fb = FontBuilder(1024, isTTF=True)
    # We need a tiny set of glyphs: .notdef + space + A.
    glyph_names = [".notdef", "space", "A"]
    fb.setupGlyphOrder(glyph_names)
    fb.setupCharacterMap({0x20: "space", 0x41: "A"})
    # Empty glyph outlines (zero-contour). Still valid TTF.
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    pen = TTGlyphPen(None)
    empty = pen.glyph()
    fb.setupGlyf({name: empty for name in glyph_names})
    fb.setupHorizontalMetrics({".notdef": (500, 0), "space": (250, 0), "A": (600, 0)})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({
        "familyName": family,
        "styleName": subfamily,
        "fullName": full_name or f"{family} {subfamily}",
        "psName": ps_name,
    })
    fb.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200)
    fb.setupPost()
    buf = BytesIO()
    fb.save(buf)
    return buf.getvalue()


@pytest.fixture
def make_ttf(tmp_path: Path):
    """Factory: writes a tiny TTF to tmp_path and returns its path."""
    def _make(filename: str, ps_name: str, **kwargs) -> Path:
        path = tmp_path / filename
        path.write_bytes(_build_minimal_ttf(ps_name, **kwargs))
        return path
    return _make


@pytest.fixture
def make_ttc(tmp_path: Path):
    """Factory: writes a TTC bundling multiple faces. Returns the .ttc path."""
    from fontTools.ttLib import TTFont, TTCollection

    def _make(filename: str, faces: list[dict]) -> Path:
        """faces is a list of kwargs dicts passed to _build_minimal_ttf."""
        ttfonts = []
        for face in faces:
            ttf_bytes = _build_minimal_ttf(**face)
            ttfonts.append(TTFont(BytesIO(ttf_bytes)))
        coll = TTCollection()
        coll.fonts = ttfonts
        path = tmp_path / filename
        coll.save(str(path))
        return path
    return _make
```

- [ ] **Step 2: Smoke-test the fixture works**

Add a temporary smoke test at the end of `tests/unit/test_font_index.py`:
```python
def test_make_ttf_fixture_produces_valid_ttf(make_ttf):
    from fontTools.ttLib import TTFont
    path = make_ttf("test.ttf", ps_name="TestPSName")
    tt = TTFont(str(path))
    assert tt["name"].getDebugName(6) == "TestPSName"
```

Run: `uv run pytest tests/unit/test_font_index.py::test_make_ttf_fixture_produces_valid_ttf -v`

Expected: passes.

- [ ] **Step 3: Commit**

```bash
git add tests/conftest.py tests/unit/test_font_index.py
git commit -m "Add synthetic font builder fixtures for tests"
```

---

## Task 6: `font_index` — face metadata extraction

**Files:**
- Modify: `src/unsubsetter/font_index.py`
- Modify: `tests/unit/test_font_index.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/test_font_index.py`:

```python
from pathlib import Path

from unsubsetter.font_index import FontIndexEntry, read_font_entries


def test_read_font_entries_single_ttf(make_ttf):
    path = make_ttf("foo.ttf", ps_name="MyFontPS", family="MyFamily", subfamily="Bold")
    entries = read_font_entries(path)
    assert len(entries) == 1
    e = entries[0]
    assert isinstance(e, FontIndexEntry)
    assert e.path == path
    assert e.ttc_face is None
    assert e.ps_name == "MyFontPS"
    assert e.family == "MyFamily"
    assert e.subfamily == "Bold"


def test_read_font_entries_ttc_yields_one_per_face(make_ttc):
    path = make_ttc("bundle.ttc", faces=[
        {"ps_name": "FaceA", "family": "F", "subfamily": "Regular"},
        {"ps_name": "FaceB", "family": "F", "subfamily": "Bold"},
    ])
    entries = read_font_entries(path)
    assert len(entries) == 2
    assert {e.ps_name for e in entries} == {"FaceA", "FaceB"}
    assert {e.ttc_face for e in entries} == {0, 1}
```

- [ ] **Step 2: Run, verify fail**

```bash
uv run pytest tests/unit/test_font_index.py -v
```

Expected: ImportError for `FontIndexEntry` / `read_font_entries`.

- [ ] **Step 3: Implement**

Append to `src/unsubsetter/font_index.py`:

```python
from dataclasses import dataclass
from pathlib import Path

from fontTools.ttLib import TTFont, TTCollection


@dataclass(frozen=True)
class FontIndexEntry:
    path: Path
    ttc_face: int | None     # None for plain .ttf/.otf; integer for .ttc faces
    ps_name: str             # name table ID 6
    full_name: str           # name table ID 4
    family: str              # name table ID 1
    subfamily: str           # name table ID 2


def _entry_from_ttfont(tt: TTFont, path: Path, ttc_face: int | None) -> FontIndexEntry:
    name = tt["name"]
    return FontIndexEntry(
        path=path,
        ttc_face=ttc_face,
        ps_name=name.getDebugName(6) or "",
        full_name=name.getDebugName(4) or "",
        family=name.getDebugName(1) or "",
        subfamily=name.getDebugName(2) or "",
    )


def read_font_entries(path: Path) -> list[FontIndexEntry]:
    """Parse a font file and return one FontIndexEntry per contained face."""
    suffix = path.suffix.lower()
    if suffix == ".ttc":
        coll = TTCollection(str(path))
        return [_entry_from_ttfont(tt, path, i) for i, tt in enumerate(coll.fonts)]
    if suffix in (".ttf", ".otf"):
        tt = TTFont(str(path))
        return [_entry_from_ttfont(tt, path, None)]
    return []
```

- [ ] **Step 4: Run, verify pass**

```bash
uv run pytest tests/unit/test_font_index.py -v
```

Expected: 7 passed (4 from Task 4 + 1 smoke test from Task 5 + 2 new).

- [ ] **Step 5: Commit**

```bash
git add src/unsubsetter/font_index.py tests/unit/test_font_index.py
git commit -m "Add font face metadata extraction (read_font_entries)"
```

---

## Task 7: `FontIndex` — directory scan + lookup

**Files:**
- Modify: `src/unsubsetter/font_index.py`
- Modify: `tests/unit/test_font_index.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/test_font_index.py`:

```python
from unsubsetter.font_index import FontIndex


def test_font_index_scans_directory(make_ttf, tmp_path):
    make_ttf("a.ttf", ps_name="FontA", family="F", subfamily="Regular")
    make_ttf("b.otf", ps_name="FontB", family="F", subfamily="Italic")
    idx = FontIndex.build([tmp_path])
    assert idx.lookup("FontA") is not None
    assert idx.lookup("FontB") is not None
    assert idx.lookup("FontC") is None


def test_font_index_lookup_is_case_and_punctuation_insensitive(make_ttf, tmp_path):
    make_ttf("h.ttf", ps_name="Horst", family="Horst", subfamily="Regular")
    idx = FontIndex.build([tmp_path])
    # The PDF often says "Horst Regular" while the disk has "Horst";
    # we look up by family+subfamily concat too.
    assert idx.lookup("HORST") is not None
    assert idx.lookup("horst regular") is not None  # family + subfamily


def test_font_index_returns_first_match_with_face_index(make_ttc, tmp_path):
    path = make_ttc("bundle.ttc", faces=[
        {"ps_name": "FaceA", "family": "F", "subfamily": "Regular"},
        {"ps_name": "FaceB", "family": "F", "subfamily": "Bold"},
    ])
    idx = FontIndex.build([tmp_path])
    entry = idx.lookup("FaceB")
    assert entry is not None
    assert entry.path == path
    assert entry.ttc_face == 1


def test_font_index_ignores_non_font_files(tmp_path):
    (tmp_path / "readme.txt").write_text("hi")
    (tmp_path / "subdir").mkdir()
    idx = FontIndex.build([tmp_path])
    assert idx.lookup("anything") is None


def test_font_index_recurses_into_subdirectories(make_ttf, tmp_path):
    # Build a TTF at the tmp_path root, then move it into a nested subdir so
    # the only copy on disk is below the root we hand to FontIndex.build.
    src = make_ttf("nested_font.ttf", ps_name="NestedFont")
    subdir = tmp_path / "deep" / "nested"
    subdir.mkdir(parents=True)
    src.rename(subdir / src.name)
    idx = FontIndex.build([tmp_path])
    assert idx.lookup("NestedFont") is not None
```

- [ ] **Step 2: Run, verify fail**

```bash
uv run pytest tests/unit/test_font_index.py -v
```

Expected: ImportError for `FontIndex`.

- [ ] **Step 3: Implement**

Append to `src/unsubsetter/font_index.py`:

```python
from collections.abc import Iterable


class FontIndex:
    """A lookup table from normalized font names to FontIndexEntry."""

    _FONT_EXTS = {".ttf", ".otf", ".ttc"}

    def __init__(self, entries_by_key: dict[str, FontIndexEntry]):
        self._by_key = entries_by_key

    @classmethod
    def build(cls, search_paths: Iterable[Path]) -> "FontIndex":
        by_key: dict[str, FontIndexEntry] = {}
        for root in search_paths:
            root = Path(root)
            if not root.exists():
                continue
            for path in root.rglob("*"):
                if path.suffix.lower() not in cls._FONT_EXTS:
                    continue
                try:
                    entries = read_font_entries(path)
                except Exception:
                    # A corrupt font file shouldn't break the index build.
                    continue
                for e in entries:
                    for key in cls._keys_for(e):
                        by_key.setdefault(key, e)
        return cls(by_key)

    @staticmethod
    def _keys_for(e: FontIndexEntry) -> list[str]:
        keys = []
        for raw in (e.ps_name, e.full_name, f"{e.family} {e.subfamily}".strip()):
            n = normalize_name(raw)
            if n:
                keys.append(n)
        return keys

    def lookup(self, name: str) -> FontIndexEntry | None:
        return self._by_key.get(normalize_name(name))

    def __len__(self) -> int:
        return len({id(e) for e in self._by_key.values()})
```

- [ ] **Step 4: Run, verify pass**

```bash
uv run pytest tests/unit/test_font_index.py -v
```

Expected: 12 passed (previous 7 + 5 new).

- [ ] **Step 5: Commit**

```bash
git add src/unsubsetter/font_index.py tests/unit/test_font_index.py
git commit -m "Add FontIndex with multi-key lookup over search paths"
```

---

## Task 8: Default font search paths

**Files:**
- Modify: `src/unsubsetter/font_index.py`

- [ ] **Step 1: Add `default_search_paths` and minimal test**

Append to `src/unsubsetter/font_index.py`:

```python
def default_search_paths() -> list[Path]:
    """Standard font locations on macOS, plus TeX Live trees if present."""
    home = Path.home()
    candidates = [
        home / "Library/Fonts",
        Path("/Library/Fonts"),
        Path("/System/Library/Fonts/Supplemental"),
        Path("/System/Library/Fonts"),
    ]
    # Add discovered TeX Live font roots
    for tl_root in sorted(Path("/usr/local/texlive").glob("*/texmf-dist/fonts")):
        for sub in ("opentype", "truetype"):
            p = tl_root / sub
            if p.exists():
                candidates.append(p)
    return [p for p in candidates if p.exists()]
```

Add a test in `tests/unit/test_font_index.py`:

```python
from unsubsetter.font_index import default_search_paths


def test_default_search_paths_returns_existing_dirs():
    # Smoke test: at least one path exists on this dev machine (macOS).
    paths = default_search_paths()
    assert all(p.exists() for p in paths)
```

- [ ] **Step 2: Run, verify pass**

```bash
uv run pytest tests/unit/test_font_index.py -v
```

Expected: 13 passed.

- [ ] **Step 3: Commit**

```bash
git add src/unsubsetter/font_index.py tests/unit/test_font_index.py
git commit -m "Add default font search paths for macOS + TeX Live"
```

---

## Task 9: `inspector` — subset prefix detection

**Files:**
- Create: `src/unsubsetter/inspector.py`
- Create: `tests/unit/test_inspector.py`

- [ ] **Step 1: Write failing tests**

`tests/unit/test_inspector.py`:
```python
from unsubsetter.inspector import split_subset_prefix


def test_split_subset_prefix_present():
    assert split_subset_prefix("ABCDEF+Preciosa") == ("ABCDEF", "Preciosa")


def test_split_subset_prefix_absent():
    assert split_subset_prefix("Preciosa") == (None, "Preciosa")


def test_split_subset_prefix_wrong_length_is_not_a_prefix():
    # 5 letters + '+' is not a valid subset prefix.
    assert split_subset_prefix("ABCDE+Preciosa") == (None, "ABCDE+Preciosa")


def test_split_subset_prefix_must_be_uppercase():
    # lowercase prefix is not a valid subset prefix per PDF spec.
    assert split_subset_prefix("abcdef+Preciosa") == (None, "abcdef+Preciosa")


def test_split_subset_prefix_with_spaces_in_name():
    assert split_subset_prefix("ZILMPO+Horst Regular") == ("ZILMPO", "Horst Regular")
```

- [ ] **Step 2: Run, verify fail**

```bash
uv run pytest tests/unit/test_inspector.py -v
```

Expected: ImportError for `split_subset_prefix`.

- [ ] **Step 3: Implement**

`src/unsubsetter/inspector.py`:
```python
"""PDF inspector: enumerate font records from a pikepdf Pdf."""
from __future__ import annotations
import re

_SUBSET_PREFIX_RE = re.compile(r"^([A-Z]{6})\+(.+)$")


def split_subset_prefix(base_font: str) -> tuple[str | None, str]:
    """Split a PostScript name into (subset_prefix, base_name).

    Returns (None, base_font) if no valid subset prefix is present.
    """
    m = _SUBSET_PREFIX_RE.match(base_font)
    if m:
        return m.group(1), m.group(2)
    return None, base_font
```

- [ ] **Step 4: Run, verify pass**

```bash
uv run pytest tests/unit/test_inspector.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/unsubsetter/inspector.py tests/unit/test_inspector.py
git commit -m "Add subset prefix detection"
```

---

## Task 10: `inspector.inspect_pdf` — FontRecord extraction

This is the first real PDF surgery. Use the committed `tiny_book.pdf` fixture for integration-style testing of the inspector itself.

**Files:**
- Modify: `src/unsubsetter/inspector.py`
- Modify: `tests/unit/test_inspector.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/test_inspector.py`:

```python
from pathlib import Path

import pikepdf

from unsubsetter.inspector import FontRecord, inspect_pdf


TINY_BOOK = Path(__file__).parent.parent / "fixtures" / "tiny_book.pdf"


def test_inspect_pdf_finds_subset_font():
    with pikepdf.open(TINY_BOOK) as pdf:
        records = inspect_pdf(pdf)
    assert len(records) >= 1
    # tiny_book.pdf uses EB Garamond, which XeLaTeX subsets.
    eb = next(
        (r for r in records if r.ps_name.lower().startswith("ebgaramond")),
        None,
    )
    assert eb is not None, f"EBGaramond not found in {[r.ps_name for r in records]}"
    assert eb.subset_prefix is not None
    assert len(eb.subset_prefix) == 6
    assert eb.subtype == "Type0"
    assert eb.descendant_subtype == "CIDFontType2"
    assert eb.has_font_file is True
    assert eb.font_file_kind == "FontFile2"


def test_inspect_pdf_used_cids_nonempty_for_text_font():
    with pikepdf.open(TINY_BOOK) as pdf:
        records = inspect_pdf(pdf)
    eb = next(r for r in records if r.ps_name.lower().startswith("ebgaramond"))
    # The fixture document has English text so we expect CIDs to be present.
    assert len(eb.used_cids) > 0
```

- [ ] **Step 2: Run, verify fail**

```bash
uv run pytest tests/unit/test_inspector.py -v
```

Expected: ImportError for `FontRecord` / `inspect_pdf`.

- [ ] **Step 3: Implement**

Append to `src/unsubsetter/inspector.py`:

```python
from dataclasses import dataclass
from collections import defaultdict

import pikepdf


@dataclass(frozen=True)
class FontRecord:
    font_obj: pikepdf.Object            # the /Font dict
    base_font: str                       # raw /BaseFont value (with subset prefix if present)
    subset_prefix: str | None
    ps_name: str                         # base_font minus subset prefix
    subtype: str                         # 'Type0', 'TrueType', 'Type1', ...
    descendant_subtype: str | None       # 'CIDFontType2', 'CIDFontType0', or None
    encoding: str                        # raw or named encoding
    has_font_file: bool
    font_file_kind: str | None           # 'FontFile', 'FontFile2', 'FontFile3', or None
    used_cids: frozenset[int]


def _stringify_name(value: pikepdf.Object | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value).lstrip("/")


def _font_file_kind(descriptor: pikepdf.Object) -> str | None:
    for key in ("/FontFile", "/FontFile2", "/FontFile3"):
        if key in descriptor:
            return key.lstrip("/")
    return None


def _collect_used_cids(pdf: pikepdf.Pdf) -> dict[int, set[int]]:
    """Walk every page's content stream, return {font_obj_objgen: set(cids)}.

    Each page has a /Resources/Font dict mapping resource name (e.g. /F12) to
    a font object. Content streams say "/F12 12 Tf" (set font to F12) then
    "(...) Tj" with bytes that are 2-byte big-endian CIDs under Identity-H.
    """
    result: dict[int, set[int]] = defaultdict(set)
    for page in pdf.pages:
        try:
            instructions = list(pikepdf.parse_content_stream(page))
        except Exception:
            continue
        # Build {resource_name -> font_obj} for this page.
        resources = page.get("/Resources", pikepdf.Dictionary())
        fonts = resources.get("/Font", pikepdf.Dictionary())
        current_font_obj: pikepdf.Object | None = None
        for operands, op in instructions:
            op_str = str(op)
            if op_str == "Tf":
                name = operands[0]
                current_font_obj = fonts.get(name)
            elif op_str in ("Tj", "'", '"') and current_font_obj is not None:
                # Last operand is the string for Tj/'; for " it's also last.
                s = operands[-1]
                _accumulate_cids(s, result[current_font_obj.objgen[0]])
            elif op_str == "TJ" and current_font_obj is not None:
                # operands[0] is an array of strings and numbers.
                for item in operands[0]:
                    if isinstance(item, (pikepdf.String, bytes)):
                        _accumulate_cids(item, result[current_font_obj.objgen[0]])
    return result


def _accumulate_cids(s, bucket: set[int]) -> None:
    raw = bytes(s) if not isinstance(s, bytes) else s
    # Identity-H uses 2-byte big-endian CIDs. Pad if odd-length (shouldn't happen).
    for i in range(0, len(raw) - 1, 2):
        bucket.add((raw[i] << 8) | raw[i + 1])


def inspect_pdf(pdf: pikepdf.Pdf) -> list[FontRecord]:
    """Enumerate all font objects in the PDF and return one FontRecord each."""
    cid_map = _collect_used_cids(pdf)
    records: list[FontRecord] = []
    seen: set[tuple[int, int]] = set()
    for obj in pdf.objects:
        if not isinstance(obj, pikepdf.Dictionary):
            continue
        if obj.get("/Type") != pikepdf.Name("/Font"):
            continue
        key = obj.objgen
        if key in seen:
            continue
        seen.add(key)

        base_font = _stringify_name(obj.get("/BaseFont"))
        subset_prefix, ps_name = split_subset_prefix(base_font)
        subtype = _stringify_name(obj.get("/Subtype"))
        encoding_obj = obj.get("/Encoding")
        encoding = _stringify_name(encoding_obj) if encoding_obj is not None else ""

        descendant_subtype = None
        descriptor = obj.get("/FontDescriptor")
        if subtype == "Type0":
            descendants = obj.get("/DescendantFonts")
            if descendants is not None and len(descendants) > 0:
                desc = descendants[0]
                descendant_subtype = _stringify_name(desc.get("/Subtype"))
                # The actual FontDescriptor for Type 0 lives on the descendant.
                descriptor = desc.get("/FontDescriptor")

        has_font_file = False
        font_file_kind = None
        if descriptor is not None:
            font_file_kind = _font_file_kind(descriptor)
            has_font_file = font_file_kind is not None

        records.append(FontRecord(
            font_obj=obj,
            base_font=base_font,
            subset_prefix=subset_prefix,
            ps_name=ps_name,
            subtype=subtype,
            descendant_subtype=descendant_subtype,
            encoding=encoding,
            has_font_file=has_font_file,
            font_file_kind=font_file_kind,
            used_cids=frozenset(cid_map.get(key[0], set())),
        ))
    return records
```

- [ ] **Step 4: Run, verify pass**

```bash
uv run pytest tests/unit/test_inspector.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Sanity check against the real book**

This is a one-off ad hoc check, not a committed test. Run:

```bash
uv run python -c "
import pikepdf
from unsubsetter.inspector import inspect_pdf
with pikepdf.open('/Users/smulloni/git/books/the_coast_of_everything/the_coast_of_everything.pdf') as pdf:
    for r in inspect_pdf(pdf):
        print(f'{r.ps_name:40} {r.subtype:10} {r.descendant_subtype or \"-\":15} sub={r.subset_prefix or \"-\":7} cids={len(r.used_cids)}')
"
```

Expected: 14 records matching the `pdffonts` output, with non-zero `used_cids` for fonts that appear in body text.

- [ ] **Step 6: Commit**

```bash
git add src/unsubsetter/inspector.py tests/unit/test_inspector.py
git commit -m "Add inspect_pdf to enumerate FontRecord entries"
```

---

## Task 11: `planner` — Action types

**Files:**
- Create: `src/unsubsetter/planner.py`
- Create: `tests/unit/test_planner.py`

- [ ] **Step 1: Write failing tests**

`tests/unit/test_planner.py`:
```python
from pathlib import Path

from unsubsetter.planner import Replace, Skip, Plan


def test_replace_action_has_required_fields():
    r = Replace(record=None, source_path=Path("/x.ttf"), ttc_face=None)
    assert r.source_path == Path("/x.ttf")
    assert r.ttc_face is None


def test_skip_action_has_reason():
    s = Skip(record=None, reason="not subsetted")
    assert s.reason == "not subsetted"


def test_plan_render_lists_actions():
    plan = Plan(actions=[
        Skip(record=_fake_record("Foo", subset_prefix=None), reason="not subsetted"),
    ])
    text = plan.render()
    assert "Foo" in text
    assert "not subsetted" in text


def _fake_record(ps_name: str, subset_prefix: str | None):
    from unsubsetter.inspector import FontRecord
    return FontRecord(
        font_obj=None, base_font=ps_name, subset_prefix=subset_prefix,
        ps_name=ps_name, subtype="Type0", descendant_subtype="CIDFontType2",
        encoding="Identity-H", has_font_file=True, font_file_kind="FontFile2",
        used_cids=frozenset(),
    )
```

- [ ] **Step 2: Run, verify fail**

```bash
uv run pytest tests/unit/test_planner.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement**

`src/unsubsetter/planner.py`:
```python
"""Planner: combines inspection + font index + filters into a list of actions."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Union

from unsubsetter.inspector import FontRecord


@dataclass(frozen=True)
class Replace:
    record: FontRecord
    source_path: Path
    ttc_face: int | None


@dataclass(frozen=True)
class Skip:
    record: FontRecord
    reason: str


Action = Union[Replace, Skip]


@dataclass(frozen=True)
class Plan:
    actions: list[Action]

    def replaces(self) -> list[Replace]:
        return [a for a in self.actions if isinstance(a, Replace)]

    def skips(self) -> list[Skip]:
        return [a for a in self.actions if isinstance(a, Skip)]

    def render(self) -> str:
        lines = []
        for a in self.actions:
            r = a.record
            base = r.ps_name if r is not None else "?"
            if isinstance(a, Replace):
                face = f" (face {a.ttc_face})" if a.ttc_face is not None else ""
                lines.append(f"  REPLACE  {base:40}  → {a.source_path}{face}")
            else:
                lines.append(f"  SKIP     {base:40}  ({a.reason})")
        replaces = len(self.replaces())
        skips = len(self.skips())
        header = f"Plan: {replaces} replace, {skips} skip"
        return header + "\n" + "\n".join(lines)
```

- [ ] **Step 4: Run, verify pass**

```bash
uv run pytest tests/unit/test_planner.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/unsubsetter/planner.py tests/unit/test_planner.py
git commit -m "Add planner Action types and Plan.render"
```

---

## Task 12: `planner.build_plan` — combine records + index + filters

**Files:**
- Modify: `src/unsubsetter/planner.py`
- Modify: `tests/unit/test_planner.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/test_planner.py`:

```python
from unittest.mock import MagicMock

from unsubsetter.planner import build_plan
from unsubsetter.font_index import FontIndex, FontIndexEntry


def _idx_with(ps_name: str, path: str = "/disk/x.ttf", ttc_face=None) -> FontIndex:
    e = FontIndexEntry(
        path=Path(path), ttc_face=ttc_face,
        ps_name=ps_name, full_name=ps_name, family=ps_name, subfamily="",
    )
    return FontIndex({_norm(ps_name): e})


def _norm(s):
    from unsubsetter.font_index import normalize_name
    return normalize_name(s)


def test_build_plan_replaces_resolvable_cid_truetype():
    rec = _fake_record("Preciosa", subset_prefix="ABCDEF")
    idx = _idx_with("Preciosa")
    plan = build_plan([rec], idx)
    assert len(plan.replaces()) == 1
    assert plan.replaces()[0].source_path == Path("/disk/x.ttf")


def test_build_plan_skips_non_subset_font():
    rec = _fake_record("Preciosa", subset_prefix=None)
    plan = build_plan([rec], _idx_with("Preciosa"))
    assert plan.skips()[0].reason == "not subsetted"


def test_build_plan_skips_cff_font():
    rec = _fake_record_cff("BradleyInitials", subset_prefix="ABCDEF")
    plan = build_plan([rec], _idx_with("BradleyInitials"))
    assert "CFF" in plan.skips()[0].reason


def test_build_plan_skips_type1_font():
    rec = _fake_record_type1("CMSY7", subset_prefix="ABCDEF")
    plan = build_plan([rec], _idx_with("CMSY7"))
    assert "Type1" in plan.skips()[0].reason or "Type 1" in plan.skips()[0].reason


def test_build_plan_skips_unresolvable_font():
    rec = _fake_record("MysteryFont", subset_prefix="ABCDEF")
    plan = build_plan([rec], FontIndex({}))
    assert "not found" in plan.skips()[0].reason.lower()


def test_build_plan_respects_only_filter():
    rec_a = _fake_record("FontA", subset_prefix="ABCDEF")
    rec_b = _fake_record("FontB", subset_prefix="ABCDEF")
    idx = FontIndex({_norm("FontA"): _entry("FontA"), _norm("FontB"): _entry("FontB")})
    plan = build_plan([rec_a, rec_b], idx, only={"FontA"})
    names = [a.record.ps_name for a in plan.replaces()]
    assert names == ["FontA"]
    assert any(a.reason == "not selected by --only" for a in plan.skips())


def test_build_plan_respects_exclude_filter():
    rec = _fake_record("FontA", subset_prefix="ABCDEF")
    plan = build_plan([rec], _idx_with("FontA"), exclude={"FontA"})
    assert plan.skips()[0].reason == "excluded by --exclude"


def _entry(name):
    return FontIndexEntry(path=Path("/x"), ttc_face=None,
                          ps_name=name, full_name=name, family=name, subfamily="")


def _fake_record_cff(ps_name, subset_prefix):
    from unsubsetter.inspector import FontRecord
    return FontRecord(
        font_obj=None, base_font=ps_name, subset_prefix=subset_prefix,
        ps_name=ps_name, subtype="Type0", descendant_subtype="CIDFontType0",
        encoding="Identity-H", has_font_file=True, font_file_kind="FontFile3",
        used_cids=frozenset(),
    )


def _fake_record_type1(ps_name, subset_prefix):
    from unsubsetter.inspector import FontRecord
    return FontRecord(
        font_obj=None, base_font=ps_name, subset_prefix=subset_prefix,
        ps_name=ps_name, subtype="Type1", descendant_subtype=None,
        encoding="Builtin", has_font_file=True, font_file_kind="FontFile",
        used_cids=frozenset(),
    )
```

- [ ] **Step 2: Run, verify fail**

```bash
uv run pytest tests/unit/test_planner.py -v
```

Expected: ImportError for `build_plan`.

- [ ] **Step 3: Implement**

Append to `src/unsubsetter/planner.py`:

```python
from unsubsetter.font_index import FontIndex, normalize_name


def build_plan(
    records: list[FontRecord],
    index: FontIndex,
    only: set[str] | None = None,
    exclude: set[str] | None = None,
) -> Plan:
    only_norm = {normalize_name(n) for n in (only or set())}
    exclude_norm = {normalize_name(n) for n in (exclude or set())}

    actions: list[Action] = []
    for rec in records:
        ps_norm = normalize_name(rec.ps_name)

        if rec.subset_prefix is None:
            actions.append(Skip(rec, "not subsetted"))
            continue
        if only_norm and ps_norm not in only_norm:
            actions.append(Skip(rec, "not selected by --only"))
            continue
        if ps_norm in exclude_norm:
            actions.append(Skip(rec, "excluded by --exclude"))
            continue
        if rec.subtype == "Type1":
            actions.append(Skip(rec, "unsupported type: Type1 (V1 handles CID TrueType only)"))
            continue
        if rec.subtype != "Type0" or rec.descendant_subtype != "CIDFontType2":
            actions.append(Skip(
                rec,
                f"unsupported type: {rec.subtype}/{rec.descendant_subtype or '-'}"
                f" (CFF or non-composite — V1 handles CID TrueType only)",
            ))
            continue

        entry = index.lookup(rec.ps_name)
        if entry is None:
            actions.append(Skip(rec, f"font not found on disk: {rec.ps_name}"))
            continue
        actions.append(Replace(rec, entry.path, entry.ttc_face))

    return Plan(actions=actions)
```

- [ ] **Step 4: Run, verify pass**

```bash
uv run pytest tests/unit/test_planner.py -v
```

Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add src/unsubsetter/planner.py tests/unit/test_planner.py
git commit -m "Add build_plan with Type/filter/index resolution logic"
```

---

## Task 13: `applier` — load font binary (TTC face selection)

The applier needs to load a full font as raw TTF bytes. For TTC files it must extract the specific face. Build this as a small standalone helper first.

**Files:**
- Create: `src/unsubsetter/applier.py`
- Create: `tests/unit/test_applier.py`

- [ ] **Step 1: Write failing tests**

`tests/unit/test_applier.py`:
```python
from io import BytesIO
from pathlib import Path

from fontTools.ttLib import TTFont

from unsubsetter.applier import load_full_font_bytes


def test_load_full_font_bytes_from_ttf(make_ttf):
    path = make_ttf("a.ttf", ps_name="A")
    data = load_full_font_bytes(path, ttc_face=None)
    # Should be a parseable standalone TTF.
    tt = TTFont(BytesIO(data))
    assert tt["name"].getDebugName(6) == "A"


def test_load_full_font_bytes_from_ttc_face(make_ttc):
    path = make_ttc("bundle.ttc", faces=[
        {"ps_name": "FaceA"},
        {"ps_name": "FaceB"},
    ])
    data_b = load_full_font_bytes(path, ttc_face=1)
    tt = TTFont(BytesIO(data_b))
    assert tt["name"].getDebugName(6) == "FaceB"
```

- [ ] **Step 2: Run, verify fail**

```bash
uv run pytest tests/unit/test_applier.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement**

`src/unsubsetter/applier.py`:
```python
"""Applier: executes a Plan on a pikepdf Pdf."""
from __future__ import annotations
from io import BytesIO
from pathlib import Path

from fontTools.ttLib import TTFont


def load_full_font_bytes(path: Path, ttc_face: int | None) -> bytes:
    """Load a font from disk and return its TTF binary.

    For TTC inputs, extract only the requested face as a standalone TTF.
    """
    kwargs = {"fontNumber": ttc_face} if ttc_face is not None else {}
    tt = TTFont(str(path), **kwargs)
    buf = BytesIO()
    tt.save(buf)
    return buf.getvalue()
```

- [ ] **Step 4: Run, verify pass**

```bash
uv run pytest tests/unit/test_applier.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/unsubsetter/applier.py tests/unit/test_applier.py
git commit -m "Add load_full_font_bytes for TTF and TTC face extraction"
```

---

## Task 14: `applier.apply_replace` — full Replace action execution

This is the heart of the tool. One action does five mutations on a pikepdf font object:

1. Replace `FontFile2` stream
2. Strip subset prefix from `BaseFont` (on both Type0 dict and descendant CIDFont)
3. Set descendant `CIDToGIDMap = /Identity`
4. Rebuild descendant `/W` array
5. Update descendant `FontDescriptor` metrics

We'll write one big test that exercises all five and then implement the function.

**Files:**
- Modify: `src/unsubsetter/applier.py`
- Modify: `tests/unit/test_applier.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_applier.py`:

```python
import pikepdf
from pathlib import Path

from unsubsetter.applier import apply_replace
from unsubsetter.inspector import inspect_pdf
from unsubsetter.planner import Replace


TINY_BOOK = Path(__file__).parent.parent / "fixtures" / "tiny_book.pdf"


def _ebgaramond_path() -> Path:
    candidates = [
        Path.home() / "Library/Fonts/EBGaramond-Regular.ttf",
    ]
    for c in candidates:
        if c.exists():
            return c
    import pytest
    pytest.skip(f"EBGaramond-Regular.ttf not found in {candidates}")


def test_apply_replace_on_tiny_book():
    eb_path = _ebgaramond_path()
    with pikepdf.open(TINY_BOOK) as pdf:
        records = inspect_pdf(pdf)
        eb = next(r for r in records if r.ps_name.lower().startswith("ebgaramond"))
        original_filefile_len = len(
            eb.font_obj["/DescendantFonts"][0]["/FontDescriptor"]["/FontFile2"]
            .read_bytes()
        )
        action = Replace(record=eb, source_path=eb_path, ttc_face=None)
        apply_replace(pdf, action)

        # 1. BaseFont prefix stripped on both Type0 and descendant.
        assert "+" not in str(eb.font_obj["/BaseFont"])
        desc = eb.font_obj["/DescendantFonts"][0]
        assert "+" not in str(desc["/BaseFont"])

        # 2. CIDToGIDMap is Identity.
        assert str(desc["/CIDToGIDMap"]) == "/Identity"

        # 3. FontFile2 stream is now larger (full font > subset).
        new_filefile_len = len(desc["/FontDescriptor"]["/FontFile2"].read_bytes())
        assert new_filefile_len > original_filefile_len

        # 4. /W array exists and covers at least the used CIDs.
        assert "/W" in desc

        # 5. FontDescriptor has /Ascent, /Descent (sanity).
        fd = desc["/FontDescriptor"]
        assert "/Ascent" in fd
        assert "/Descent" in fd
```

- [ ] **Step 2: Run, verify fail**

```bash
uv run pytest tests/unit/test_applier.py::test_apply_replace_on_tiny_book -v
```

Expected: ImportError for `apply_replace`.

- [ ] **Step 3: Implement**

Append to `src/unsubsetter/applier.py`:

```python
import pikepdf

from unsubsetter.planner import Replace


def apply_replace(pdf: pikepdf.Pdf, action: Replace) -> None:
    """Execute a single Replace action against the open pikepdf.Pdf in place."""
    full_bytes = load_full_font_bytes(action.source_path, action.ttc_face)
    full_tt = TTFont(BytesIO(full_bytes))

    font_obj = action.record.font_obj
    descendant = font_obj["/DescendantFonts"][0]
    descriptor = descendant["/FontDescriptor"]

    # 1. Replace FontFile2 stream.
    descriptor["/FontFile2"] = pdf.make_stream(full_bytes)
    descriptor["/FontFile2"]["/Length1"] = len(full_bytes)

    # 2. Strip subset prefix from BaseFont on both dicts.
    _strip_subset_prefix(font_obj, "/BaseFont")
    _strip_subset_prefix(descendant, "/BaseFont")
    _strip_subset_prefix(descriptor, "/FontName")

    # 3. CIDToGIDMap = /Identity (XeLaTeX TrueType subsets preserve GIDs).
    descendant["/CIDToGIDMap"] = pikepdf.Name("/Identity")

    # 4. Rebuild /W array covering all used CIDs (plus original /W keys).
    widths = _build_widths_array(full_tt, action.record.used_cids)
    descendant["/W"] = widths
    # /DW (default width) — set from .notdef or 1000 as conventional default.
    descendant["/DW"] = _default_width(full_tt)

    # 5. Update FontDescriptor metrics.
    _update_descriptor_metrics(descriptor, full_tt)


def _strip_subset_prefix(obj: pikepdf.Object, key: str) -> None:
    raw = str(obj[key]).lstrip("/")
    if len(raw) > 7 and raw[6] == "+" and raw[:6].isupper() and raw[:6].isalpha():
        obj[key] = pikepdf.Name("/" + raw[7:])


def _build_widths_array(tt: TTFont, used_cids: frozenset[int]) -> pikepdf.Array:
    """Build a PDF /W array covering the used CIDs.

    Format: [CID [w1 w2 ...]] runs — we use the simplest form, one entry per
    consecutive run of CIDs. Widths come from the full font's hmtx in font
    design units (units-per-em = 1000 conventional, scaled from tt.upem).
    """
    hmtx = tt["hmtx"]
    glyph_order = tt.getGlyphOrder()
    upem = tt["head"].unitsPerEm
    # PDF widths are in 1/1000 em.
    def width_for(gid: int) -> int:
        if gid >= len(glyph_order):
            return 0
        gname = glyph_order[gid]
        adv = hmtx.metrics.get(gname, (0, 0))[0]
        return round(adv * 1000 / upem)

    if not used_cids:
        return pikepdf.Array([])

    sorted_cids = sorted(used_cids)
    result: list = []
    run_start = sorted_cids[0]
    run_widths = [width_for(run_start)]
    for cid in sorted_cids[1:]:
        if cid == run_start + len(run_widths):
            run_widths.append(width_for(cid))
        else:
            result.extend([run_start, pikepdf.Array(run_widths)])
            run_start = cid
            run_widths = [width_for(cid)]
    result.extend([run_start, pikepdf.Array(run_widths)])
    return pikepdf.Array(result)


def _default_width(tt: TTFont) -> int:
    hmtx = tt["hmtx"]
    upem = tt["head"].unitsPerEm
    notdef_adv = hmtx.metrics.get(".notdef", (1000, 0))[0]
    return round(notdef_adv * 1000 / upem)


def _update_descriptor_metrics(descriptor: pikepdf.Object, tt: TTFont) -> None:
    """Update Ascent, Descent, CapHeight, ItalicAngle, FontBBox, etc. from full font."""
    upem = tt["head"].unitsPerEm
    def scale(value: int) -> int:
        return round(value * 1000 / upem)

    os2 = tt["OS/2"]
    hhea = tt["hhea"]
    head = tt["head"]
    post = tt["post"]

    descriptor["/Ascent"] = scale(os2.sTypoAscender if hasattr(os2, "sTypoAscender") else hhea.ascent)
    descriptor["/Descent"] = scale(os2.sTypoDescender if hasattr(os2, "sTypoDescender") else hhea.descent)
    descriptor["/CapHeight"] = scale(getattr(os2, "sCapHeight", os2.sTypoAscender))
    descriptor["/XHeight"] = scale(getattr(os2, "sxHeight", 0) or 0)
    descriptor["/ItalicAngle"] = float(post.italicAngle)
    descriptor["/FontBBox"] = pikepdf.Array([
        scale(head.xMin), scale(head.yMin), scale(head.xMax), scale(head.yMax),
    ])
    # StemV is hard to compute exactly; PDF readers don't strictly require it.
    # 80 is a conventional placeholder for regular weight, 120 for bold.
    descriptor["/StemV"] = 80
```

- [ ] **Step 4: Run, verify pass**

```bash
uv run pytest tests/unit/test_applier.py::test_apply_replace_on_tiny_book -v
```

Expected: passes. If a font asset is missing, the test skips.

- [ ] **Step 5: Visual sanity check**

After applying, save the PDF and eyeball it:

```bash
uv run python -c "
import shutil, pikepdf
from pathlib import Path
from unsubsetter.inspector import inspect_pdf
from unsubsetter.applier import apply_replace
from unsubsetter.planner import Replace

src = Path('tests/fixtures/tiny_book.pdf')
dst = Path('tmp/tiny_book.out.pdf')
dst.parent.mkdir(exist_ok=True)
shutil.copy(src, dst)
with pikepdf.open(dst, allow_overwriting_input=True) as pdf:
    records = inspect_pdf(pdf)
    eb = next(r for r in records if r.ps_name.lower().startswith('ebgaramond'))
    apply_replace(pdf, Replace(eb, Path.home()/'Library/Fonts/EBGaramond-Regular.ttf', None))
    pdf.save(dst)
"
pdffonts tmp/tiny_book.out.pdf
open tmp/tiny_book.out.pdf
```

Expected: `pdffonts` shows `sub=no` for EBGaramond; the rendered PDF looks identical to the original.

- [ ] **Step 6: Commit**

```bash
git add src/unsubsetter/applier.py tests/unit/test_applier.py
git commit -m "Add apply_replace: swap font program, strip prefix, rebuild /W and metrics"
```

---

## Task 15: `applier.run_plan` — orchestrate Replace and Skip actions with atomic write

**Files:**
- Modify: `src/unsubsetter/applier.py`
- Modify: `tests/unit/test_applier.py`

- [ ] **Step 1: Write failing test**

Append to `tests/unit/test_applier.py`:

```python
def test_run_plan_writes_output_atomically(tmp_path):
    eb_path = _ebgaramond_path()
    out = tmp_path / "out.pdf"
    from unsubsetter.applier import run_plan
    from unsubsetter.planner import Plan, Replace
    with pikepdf.open(TINY_BOOK) as pdf:
        records = inspect_pdf(pdf)
        eb = next(r for r in records if r.ps_name.lower().startswith("ebgaramond"))
        plan = Plan(actions=[Replace(eb, eb_path, None)])
        run_plan(pdf, plan, out)
    assert out.exists()
    # Re-open and verify the change persisted.
    with pikepdf.open(out) as pdf2:
        records2 = inspect_pdf(pdf2)
        eb2 = next(r for r in records2 if r.ps_name.lower().startswith("ebgaramond"))
        assert eb2.subset_prefix is None
```

- [ ] **Step 2: Run, verify fail**

```bash
uv run pytest tests/unit/test_applier.py::test_run_plan_writes_output_atomically -v
```

Expected: ImportError for `run_plan`.

- [ ] **Step 3: Implement**

Append to `src/unsubsetter/applier.py`:

```python
import os
import tempfile

from unsubsetter.planner import Plan


def run_plan(pdf: pikepdf.Pdf, plan: Plan, output_path: Path) -> None:
    """Apply every Replace action in the plan, then write the PDF atomically."""
    for action in plan.actions:
        if isinstance(action, Replace):
            apply_replace(pdf, action)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=output_path.stem + ".",
        suffix=".tmp.pdf",
        dir=str(output_path.parent),
    )
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        pdf.save(str(tmp_path))
        os.replace(tmp_path, output_path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise
```

- [ ] **Step 4: Run, verify pass**

```bash
uv run pytest tests/unit/test_applier.py -v
```

Expected: all passing.

- [ ] **Step 5: Commit**

```bash
git add src/unsubsetter/applier.py tests/unit/test_applier.py
git commit -m "Add run_plan with atomic tempfile-then-rename output"
```

---

## Task 16: `verifier` — structural checks

**Files:**
- Create: `src/unsubsetter/verifier.py`
- Create: `tests/unit/test_verifier.py`

- [ ] **Step 1: Write failing tests**

`tests/unit/test_verifier.py`:
```python
import shutil
from pathlib import Path

import pikepdf
import pytest

from unsubsetter.applier import run_plan
from unsubsetter.inspector import inspect_pdf
from unsubsetter.planner import Plan, Replace, Skip
from unsubsetter.verifier import verify_structural, VerificationReport


TINY_BOOK = Path(__file__).parent.parent / "fixtures" / "tiny_book.pdf"


def _ebgaramond_path() -> Path:
    p = Path.home() / "Library/Fonts/EBGaramond-Regular.ttf"
    if not p.exists():
        pytest.skip("EBGaramond-Regular.ttf not found")
    return p


def test_verify_structural_pass(tmp_path):
    out = tmp_path / "out.pdf"
    with pikepdf.open(TINY_BOOK) as pdf:
        records = inspect_pdf(pdf)
        eb = next(r for r in records if r.ps_name.lower().startswith("ebgaramond"))
        plan = Plan(actions=[Replace(eb, _ebgaramond_path(), None)])
        run_plan(pdf, plan, out)
    report = verify_structural(TINY_BOOK, out, plan)
    assert report.passed, report.failures()


def test_verify_structural_detects_page_count_mismatch(tmp_path):
    out = tmp_path / "out.pdf"
    # Copy as a no-op then remove a page.
    shutil.copy(TINY_BOOK, out)
    with pikepdf.open(out, allow_overwriting_input=True) as pdf:
        if len(pdf.pages) > 1:
            del pdf.pages[-1]
        else:
            # Duplicate a page so we can delete one and still have a mismatch.
            pdf.pages.append(pdf.pages[0])
            pdf.save(out)
            with pikepdf.open(out, allow_overwriting_input=True) as pdf2:
                del pdf2.pages[-1]
                pdf2.save(out)
    plan = Plan(actions=[])
    report = verify_structural(TINY_BOOK, out, plan)
    assert not report.passed
    assert any("page count" in f.lower() for f in report.failures())
```

- [ ] **Step 2: Run, verify fail**

```bash
uv run pytest tests/unit/test_verifier.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement**

`src/unsubsetter/verifier.py`:
```python
"""Verifier: structural and optional visual checks on the output PDF."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path

import pikepdf

from unsubsetter.inspector import inspect_pdf
from unsubsetter.planner import Plan, Replace


@dataclass
class VerificationReport:
    checks: list[tuple[str, bool, str]] = field(default_factory=list)  # (name, ok, detail)

    @property
    def passed(self) -> bool:
        return all(ok for _, ok, _ in self.checks)

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        self.checks.append((name, ok, detail))

    def failures(self) -> list[str]:
        return [f"{n}: {d}" for n, ok, d in self.checks if not ok]

    def render(self) -> str:
        lines = []
        for name, ok, detail in self.checks:
            mark = "OK  " if ok else "FAIL"
            extra = f" — {detail}" if detail else ""
            lines.append(f"  [{mark}] {name}{extra}")
        return "\n".join(lines)


def verify_structural(
    original_path: Path,
    modified_path: Path,
    plan: Plan,
) -> VerificationReport:
    """Re-parse the modified PDF and check structural invariants against the original."""
    report = VerificationReport()

    try:
        orig_pdf = pikepdf.open(original_path)
        mod_pdf = pikepdf.open(modified_path)
    except Exception as exc:
        report.add("open_modified_pdf", False, str(exc))
        return report
    report.add("open_modified_pdf", True)

    # Page count.
    same_pages = len(orig_pdf.pages) == len(mod_pdf.pages)
    report.add(
        "page count matches",
        same_pages,
        f"orig={len(orig_pdf.pages)} mod={len(mod_pdf.pages)}",
    )

    # MediaBoxes.
    if same_pages:
        for i, (op, mp) in enumerate(zip(orig_pdf.pages, mod_pdf.pages)):
            o_mb = list(op.get("/MediaBox", []))
            m_mb = list(mp.get("/MediaBox", []))
            report.add(f"page {i+1} MediaBox", o_mb == m_mb, f"orig={o_mb} mod={m_mb}")

    # Per-Replace checks.
    mod_records_by_objgen = {r.font_obj.objgen: r for r in inspect_pdf(mod_pdf)}
    for action in plan.actions:
        if not isinstance(action, Replace):
            continue
        target = mod_records_by_objgen.get(action.record.font_obj.objgen)
        ps = action.record.ps_name
        if target is None:
            report.add(f"font {ps} present", False, "object not found in modified PDF")
            continue
        report.add(f"font {ps} prefix stripped", target.subset_prefix is None,
                   f"got prefix={target.subset_prefix}")
        # CIDToGIDMap should now be /Identity.
        desc = target.font_obj["/DescendantFonts"][0]
        cid_map = str(desc.get("/CIDToGIDMap", "")).strip()
        report.add(f"font {ps} CIDToGIDMap=Identity", cid_map == "/Identity", cid_map)

    orig_pdf.close()
    mod_pdf.close()
    return report
```

- [ ] **Step 4: Run, verify pass**

```bash
uv run pytest tests/unit/test_verifier.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/unsubsetter/verifier.py tests/unit/test_verifier.py
git commit -m "Add verify_structural for post-write invariant checks"
```

---

## Task 17: `verifier.verify_visual` — opt-in pdftoppm pixel diff

**Files:**
- Modify: `src/unsubsetter/verifier.py`
- Modify: `tests/unit/test_verifier.py`

- [ ] **Step 1: Write failing test**

Append to `tests/unit/test_verifier.py`:

```python
def test_verify_visual_passes_on_identical_pdf(tmp_path):
    # Copying the same PDF should produce 0 pixel diffs.
    out = tmp_path / "copy.pdf"
    shutil.copy(TINY_BOOK, out)
    from unsubsetter.verifier import verify_visual
    report = verify_visual(TINY_BOOK, out, num_pages=1, seed=0)
    assert report.passed, report.failures()


def test_verify_visual_flags_obviously_different_pdf(tmp_path):
    # Construct a deliberately different PDF (add some pages we'll compare against).
    out = tmp_path / "different.pdf"
    with pikepdf.open(TINY_BOOK) as pdf:
        # Duplicate the page content stream to itself a couple times to make it
        # render quite differently. Easier: just blank a page.
        page = pdf.pages[0]
        page.Contents = pdf.make_stream(b"")
        pdf.save(out)
    from unsubsetter.verifier import verify_visual
    report = verify_visual(TINY_BOOK, out, num_pages=1, seed=0)
    assert not report.passed
```

- [ ] **Step 2: Run, verify fail**

```bash
uv run pytest tests/unit/test_verifier.py::test_verify_visual_passes_on_identical_pdf -v
```

Expected: ImportError for `verify_visual`.

- [ ] **Step 3: Implement**

Append to `src/unsubsetter/verifier.py`:

```python
import random
import subprocess
import tempfile

from PIL import Image, ImageChops


def verify_visual(
    original_path: Path,
    modified_path: Path,
    num_pages: int,
    seed: int | None = None,
    max_pixel_diff: int = 3,
    max_diff_ratio: float = 0.001,
) -> VerificationReport:
    """Render N random pages from both PDFs and pixel-diff them.

    Returns a VerificationReport with one check per sampled page.
    """
    report = VerificationReport()
    rng = random.Random(seed)
    with pikepdf.open(original_path) as pdf:
        total_pages = len(pdf.pages)
    if total_pages == 0:
        report.add("visual: page count > 0", False, "0 pages")
        return report

    sample_size = min(num_pages, total_pages)
    pages = sorted(rng.sample(range(1, total_pages + 1), sample_size))

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        for page_num in pages:
            orig_png = _render_page(original_path, page_num, td_path / f"orig_{page_num}")
            mod_png = _render_page(modified_path, page_num, td_path / f"mod_{page_num}")
            if orig_png is None or mod_png is None:
                report.add(f"page {page_num} render", False, "pdftoppm failed")
                continue
            ok, detail = _images_match(orig_png, mod_png, max_pixel_diff, max_diff_ratio)
            report.add(f"page {page_num} visual diff", ok, detail)
    return report


def _render_page(pdf_path: Path, page: int, prefix: Path) -> Path | None:
    """Render one page to PNG at 150 DPI via pdftoppm. Returns the PNG path or None."""
    try:
        subprocess.run(
            ["pdftoppm", "-r", "150", "-f", str(page), "-l", str(page),
             "-png", str(pdf_path), str(prefix)],
            check=True, capture_output=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    # pdftoppm appends -NN.png; the digit count varies with total pages.
    candidates = list(prefix.parent.glob(prefix.name + "-*.png"))
    return candidates[0] if candidates else None


def _images_match(
    a_path: Path, b_path: Path, max_pixel_diff: int, max_diff_ratio: float,
) -> tuple[bool, str]:
    a = Image.open(a_path).convert("RGB")
    b = Image.open(b_path).convert("RGB")
    if a.size != b.size:
        return False, f"size mismatch {a.size} vs {b.size}"
    diff = ImageChops.difference(a, b)
    bbox = diff.getbbox()
    if bbox is None:
        return True, "identical"
    # Count pixels with any channel > max_pixel_diff.
    diffs = sum(
        1 for px in diff.crop(bbox).getdata() if max(px) > max_pixel_diff
    )
    total = a.size[0] * a.size[1]
    ratio = diffs / total
    if ratio <= max_diff_ratio:
        return True, f"{diffs}/{total} differing pixels (ratio {ratio:.4%})"
    return False, f"{diffs}/{total} differing pixels (ratio {ratio:.4%})"
```

- [ ] **Step 4: Run, verify pass**

```bash
uv run pytest tests/unit/test_verifier.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/unsubsetter/verifier.py tests/unit/test_verifier.py
git commit -m "Add verify_visual with pdftoppm + Pillow pixel diff"
```

---

## Task 18: `cli.cli` — click entry point, check mode

**Files:**
- Create: `src/unsubsetter/cli.py`
- Create: `tests/unit/test_cli.py`

- [ ] **Step 1: Write failing test**

`tests/unit/test_cli.py`:
```python
from pathlib import Path

from click.testing import CliRunner

from unsubsetter.cli import cli


TINY_BOOK = Path(__file__).parent.parent / "fixtures" / "tiny_book.pdf"


def test_cli_check_mode_lists_plan():
    runner = CliRunner()
    result = runner.invoke(cli, [str(TINY_BOOK)])
    assert result.exit_code == 0, result.output
    assert "REPLACE" in result.output or "SKIP" in result.output
    assert "EBGaramond" in result.output or "ebgaramond" in result.output.lower()


def test_cli_check_mode_does_not_write_output(tmp_path):
    runner = CliRunner()
    out = tmp_path / "should_not_exist.pdf"
    result = runner.invoke(cli, [str(TINY_BOOK), "--output", str(out)])
    assert result.exit_code == 0
    assert not out.exists(), "check mode must not write output"
```

- [ ] **Step 2: Run, verify fail**

```bash
uv run pytest tests/unit/test_cli.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement**

`src/unsubsetter/cli.py`:
```python
"""CLI entry point."""
from __future__ import annotations
import sys
from pathlib import Path

import click
import pikepdf

from unsubsetter.applier import run_plan
from unsubsetter.font_index import FontIndex, default_search_paths
from unsubsetter.inspector import inspect_pdf
from unsubsetter.planner import build_plan
from unsubsetter.verifier import verify_structural, verify_visual


def _csv_set(value: str | None) -> set[str]:
    if not value:
        return set()
    return {tok.strip() for tok in value.split(",") if tok.strip()}


@click.command()
@click.argument("input_pdf", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--fix", is_flag=True, help="Write output (default: inspect-only).")
@click.option("--output", "-o", type=click.Path(dir_okay=False, path_type=Path),
              default=None, help="Output path (default: INPUT.unsubset.pdf).")
@click.option("--force", is_flag=True, help="Allow overwriting INPUT_PDF.")
@click.option("--only", default="", help="Comma-separated PostScript names to include.")
@click.option("--exclude", default="", help="Comma-separated PostScript names to skip.")
@click.option("--font-path", "font_paths", multiple=True, type=click.Path(path_type=Path),
              help="Additional font search dir (repeatable).")
@click.option("--verify-visual", "verify_visual_n", type=int, default=0,
              help="After fix, render N random pages and pixel-diff them.")
@click.option("-v", "--verbose", is_flag=True)
@click.version_option()
def cli(
    input_pdf: Path,
    fix: bool,
    output: Path | None,
    force: bool,
    only: str,
    exclude: str,
    font_paths: tuple[Path, ...],
    verify_visual_n: int,
    verbose: bool,
) -> None:
    """Re-embed full (non-subset) fonts in a PDF."""
    search_paths = default_search_paths() + list(font_paths)
    if verbose:
        click.echo(f"Building font index from {len(search_paths)} paths…", err=True)
    index = FontIndex.build(search_paths)
    if verbose:
        click.echo(f"Font index: {len(index)} unique faces.", err=True)

    with pikepdf.open(input_pdf) as pdf:
        records = inspect_pdf(pdf)
        plan = build_plan(records, index, only=_csv_set(only), exclude=_csv_set(exclude))

        click.echo(plan.render())

        if not fix:
            sys.exit(0)

        out_path = output or input_pdf.with_suffix(".unsubset.pdf")
        if out_path.resolve() == input_pdf.resolve() and not force:
            click.echo(
                f"ERROR: --output equals INPUT_PDF; pass --force to overwrite.",
                err=True,
            )
            sys.exit(1)

        if not plan.replaces():
            click.echo("Nothing to replace; not writing output.", err=True)
            sys.exit(0)

        run_plan(pdf, plan, out_path)
        click.echo(f"Wrote {out_path}", err=True)

    # Verification (re-opens output).
    structural = verify_structural(input_pdf, out_path, plan)
    click.echo("\nStructural verification:")
    click.echo(structural.render())
    if not structural.passed:
        sys.exit(2)

    if verify_visual_n > 0:
        visual = verify_visual(input_pdf, out_path, num_pages=verify_visual_n)
        click.echo("\nVisual verification:")
        click.echo(visual.render())
        if not visual.passed:
            sys.exit(3)
```

- [ ] **Step 4: Run, verify pass**

```bash
uv run pytest tests/unit/test_cli.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Smoke-test the CLI**

```bash
uv run unsubsetter tests/fixtures/tiny_book.pdf
```

Expected: prints a plan with one REPLACE for EBGaramond.

- [ ] **Step 6: Commit**

```bash
git add src/unsubsetter/cli.py tests/unit/test_cli.py
git commit -m "Add click CLI with check/fix modes and verification wiring"
```

---

## Task 19: CLI fix-mode integration test

**Files:**
- Create: `tests/integration/test_pipeline.py`

- [ ] **Step 1: Write the integration test**

`tests/integration/test_pipeline.py`:
```python
"""End-to-end pipeline integration tests."""
from pathlib import Path

import pytest
import pikepdf
from click.testing import CliRunner

from unsubsetter.cli import cli
from unsubsetter.inspector import inspect_pdf


TINY_BOOK = Path(__file__).parent.parent / "fixtures" / "tiny_book.pdf"
EBGARAMOND = Path.home() / "Library/Fonts/EBGaramond-Regular.ttf"


@pytest.fixture(autouse=True)
def _require_font():
    if not EBGARAMOND.exists():
        pytest.skip(f"Required font not installed: {EBGARAMOND}")


def test_fix_mode_unsubsets_font(tmp_path):
    out = tmp_path / "out.pdf"
    runner = CliRunner()
    result = runner.invoke(cli, [str(TINY_BOOK), "--fix", "--output", str(out)])
    assert result.exit_code == 0, result.output
    assert out.exists()
    with pikepdf.open(out) as pdf:
        records = inspect_pdf(pdf)
        eb = next(r for r in records if r.ps_name.lower().startswith("ebgaramond"))
        assert eb.subset_prefix is None


def test_fix_is_idempotent(tmp_path):
    """Running fix on an already-unsubset PDF should produce no replaces."""
    once = tmp_path / "once.pdf"
    runner = CliRunner()
    runner.invoke(cli, [str(TINY_BOOK), "--fix", "--output", str(once)])

    twice = tmp_path / "twice.pdf"
    result = runner.invoke(cli, [str(once), "--fix", "--output", str(twice)])
    assert result.exit_code == 0, result.output
    # The plan from the second run should have no REPLACE actions.
    assert "REPLACE" not in result.output or result.output.count("REPLACE") == 0


def test_only_filter_excludes_other_fonts(tmp_path):
    runner = CliRunner()
    # Use a font name that doesn't exist in the PDF; nothing should be replaced.
    result = runner.invoke(cli, [str(TINY_BOOK), "--only", "NonexistentFont"])
    assert result.exit_code == 0
    assert "REPLACE" not in result.output


def test_visual_verify_passes_after_fix(tmp_path):
    out = tmp_path / "out.pdf"
    runner = CliRunner()
    result = runner.invoke(cli, [
        str(TINY_BOOK), "--fix", "--output", str(out), "--verify-visual", "1",
    ])
    assert result.exit_code == 0, result.output
    assert "Visual verification" in result.output
    # No FAIL lines in the visual section.
    visual_section = result.output.split("Visual verification:")[-1]
    assert "FAIL" not in visual_section
```

- [ ] **Step 2: Run**

```bash
uv run pytest tests/integration/test_pipeline.py -v
```

Expected: 4 passed (or skipped if EBGaramond missing).

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_pipeline.py
git commit -m "Add end-to-end pipeline integration tests"
```

---

## Task 20: Acceptance procedure in README + run on the real book

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README with acceptance procedure**

Replace `README.md` with:

````markdown
# unsubsetter

Re-embed full (non-subset) fonts in PDFs so Amazon KDP's preflight check accepts them.

V1 handles **CID TrueType fonts only.** CFF (CIDFontType0) and simple Type 1 fonts
are reported but skipped — see `docs/superpowers/specs/2026-05-21-unsubsetter-design.md`.

## Install

    uv sync --extra dev

## Usage

Inspect (default — no writes):

    uv run unsubsetter book.pdf

Fix (writes `book.unsubset.pdf` by default):

    uv run unsubsetter --fix book.pdf

Filter to specific fonts:

    uv run unsubsetter --fix --only Preciosa,Janson book.pdf

With visual verification (renders N random pages and pixel-diffs them):

    uv run unsubsetter --fix --verify-visual 10 book.pdf

## Tests

    uv run pytest

## Acceptance procedure (manual — pre-KDP gate)

Before uploading to KDP, run the following on the production PDF:

1. **Inspect:**
   ```
   uv run unsubsetter ~/git/books/the_coast_of_everything/the_coast_of_everything.pdf
   ```
   Confirm the plan covers Preciosa (the font KDP flagged). Note any `SKIP` lines
   that mention missing-on-disk fonts and resolve them before proceeding.

2. **Fix with visual sampling:**
   ```
   uv run unsubsetter --fix --verify-visual 10 \
     ~/git/books/the_coast_of_everything/the_coast_of_everything.pdf
   ```
   This writes `the_coast_of_everything.unsubset.pdf`.

3. **Independent structural check:**
   ```
   pdffonts the_coast_of_everything.unsubset.pdf
   ```
   Confirm `sub=no` on Preciosa and every other previously-subset CID TrueType.

4. **Spot-check 5 pages visually** in Preview/Acrobat — focus on:
   - Pages with drop caps (uses CFF fonts skipped by V1; should look identical)
   - Pages with math symbols (CMSY7 — also skipped)
   - Heavy-text body pages (Janson Roman/Italic)

5. **Upload to KDP.** If it bounces again on a *different* font, run unsubsetter
   again with `--only THAT_FONT` to test in isolation, or report the issue.

## Out-of-scope fallbacks (V2 candidates)

The two CFF fonts (`P22PreissigCalligraphic`, `BradleyInitials`) appear only on
drop-cap pages. If KDP rejects those, the page-splice outline trick from the
spec is the right workaround for V1 — see the spec's "Future work" section.
````

- [ ] **Step 2: Run on the real book**

```bash
uv run unsubsetter ~/git/books/the_coast_of_everything/the_coast_of_everything.pdf
```

Expected: a plan with multiple REPLACE entries (one per CID TrueType font with prefix) and 3 SKIPs (P22Preissig, BradleyInitials, CMSY7).

If any expected REPLACE is missing because the font isn't found on disk, debug via:

```bash
uv run unsubsetter -v ~/git/books/the_coast_of_everything/the_coast_of_everything.pdf 2>&1 | head -5
```

- [ ] **Step 3: Fix + verify the real book**

```bash
uv run unsubsetter --fix --verify-visual 10 \
  ~/git/books/the_coast_of_everything/the_coast_of_everything.pdf
```

Expected: writes `the_coast_of_everything.unsubset.pdf`, structural verification passes, visual verification reports diffs within tolerance.

Manually verify:
```bash
pdffonts ~/git/books/the_coast_of_everything/the_coast_of_everything.unsubset.pdf
```

Expected: all targeted fonts now show `sub=no`.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "Document acceptance procedure for KDP upload gate"
```

---

## Final self-review checklist (for the implementer)

- All tests pass: `uv run pytest`
- `unsubsetter --help` prints sensible usage.
- `unsubsetter --check tests/fixtures/tiny_book.pdf` shows a plan.
- `unsubsetter --fix tests/fixtures/tiny_book.pdf` writes a usable output.
- Idempotent: running fix on the output reports nothing to do.
- The real book passes structural + visual verify.
- `pdffonts` confirms `sub=no` on Preciosa and the other targeted CID TrueType fonts in the real book.

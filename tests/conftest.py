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

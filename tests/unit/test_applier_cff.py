"""Unit tests for the CFF apply path and helpers."""
from __future__ import annotations
from io import BytesIO
from pathlib import Path

import pikepdf
import pytest
from fontTools.cffLib import CFFFontSet
from fontTools.fontBuilder import FontBuilder
from fontTools.misc.psCharStrings import T2CharString
from fontTools.ttLib import TTFont

from unsubsetter.applier import _cid_to_glyph_name, _read_embedded_cff
from unsubsetter.inspector import inspect_pdf


TINY_BOOK_CFF = Path(__file__).parent.parent / "fixtures" / "tiny_book_cff.pdf"


def _cff_record():
    """Return the CIDFontType0 record from the CFF fixture."""
    with pikepdf.open(TINY_BOOK_CFF) as pdf:
        records = inspect_pdf(pdf)
    cff_records = [r for r in records if r.descendant_subtype == "CIDFontType0"]
    if not cff_records:
        pytest.skip("CFF fixture has no CIDFontType0 record")
    return cff_records[0]


def test_read_embedded_cff_returns_parsed_cffset():
    record = _cff_record()
    # The font_obj reference is to a closed Pdf; reopen and pass the live record.
    with pikepdf.open(TINY_BOOK_CFF) as pdf:
        records = inspect_pdf(pdf)
        rec = next(r for r in records if r.descendant_subtype == "CIDFontType0")
        cff = _read_embedded_cff(rec)
    assert isinstance(cff, CFFFontSet)
    assert len(cff.topDictIndex) >= 1
    top = cff.topDictIndex[0]
    assert hasattr(top, "CharStrings")


def test_cid_to_glyph_name_for_cid_keyed_fixture():
    """TeX Gyre Termes embedded as /CIDFontType0 is CID-keyed CFF (has ROS).

    The mapping should be {document_cid: 'cidNNNNN'} covering every CID the
    PDF actually references, and .notdef (GID 0) should be excluded.
    """
    with pikepdf.open(TINY_BOOK_CFF) as pdf:
        records = inspect_pdf(pdf)
        rec = next(r for r in records if r.descendant_subtype == "CIDFontType0")
        cff = _read_embedded_cff(rec)
        mapping = _cid_to_glyph_name(cff)
    assert len(mapping) > 0
    # All entries should be cidNNNNN-form (CID-keyed branch).
    for cid, name in mapping.items():
        assert name == f"cid{cid:05d}", (cid, name)
    # .notdef (GID 0, no CID) must not appear.
    assert ".notdef" not in mapping.values()
    # Every CID the document uses must be in the mapping.
    assert rec.used_cids.issubset(mapping.keys()), \
        f"missing CIDs: {sorted(rec.used_cids - mapping.keys())}"


def test_cid_to_glyph_name_for_name_keyed_cff():
    """Synthesize a name-keyed CFF (FontBuilder default for OTF).

    With no ROS, the mapping returned is {gid: glyph_name} treating GIDs as
    document CIDs (the PDF /CIDFontType0 convention).
    """
    fb = FontBuilder(1000, isTTF=False)
    fb.setupGlyphOrder([".notdef", "A", "B"])
    fb.setupCharacterMap({0x41: "A", 0x42: "B"})
    # T2CharString objects (not bare lists): FontBuilder.setupCFF stamps
    # .private/.globalSubrs onto each value, so empty `[]` raises AttributeError.
    def _empty_cs() -> T2CharString:
        return T2CharString(program=["endchar"])
    fb.setupCFF(
        psName="NameKeyedTest",
        fontInfo={"FullName": "Name Keyed Test"},
        charStringsDict={".notdef": _empty_cs(), "A": _empty_cs(), "B": _empty_cs()},
        privateDict={},
    )
    fb.setupHorizontalMetrics({".notdef": (500, 0), "A": (600, 0), "B": (700, 0)})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({"familyName": "NameKeyedTest", "styleName": "Regular",
                       "fullName": "Name Keyed Test Regular",
                       "psName": "NameKeyedTest"})
    fb.setupOS2(sTypoAscender=800, sTypoDescender=-200,
                usWinAscent=800, usWinDescent=200)
    fb.setupPost()
    buf = BytesIO()
    fb.save(buf)
    tt = TTFont(BytesIO(buf.getvalue()))
    assert not hasattr(tt["CFF "].cff.topDictIndex[0], "ROS"), \
        "FontBuilder unexpectedly produced a CID-keyed CFF"

    mapping = _cid_to_glyph_name(tt["CFF "].cff)
    assert mapping == {0: ".notdef", 1: "A", 2: "B"}


from unsubsetter.applier import _validate_cff_replace
from unsubsetter.errors import UnsupportedFontError
from unsubsetter.planner import Replace


def _tex_gyre_termes_path() -> Path:
    p = Path(
        "/usr/local/texlive/2025/texmf-dist/fonts/opentype/public/tex-gyre/"
        "texgyretermes-regular.otf"
    )
    if not p.exists():
        pytest.skip(f"TeX Gyre Termes not installed at {p}")
    return p


def test_validate_cff_replace_passes_on_matching_disk_font():
    """Same disk font as the one originally embedded → correspondence holds."""
    disk = _tex_gyre_termes_path()
    with pikepdf.open(TINY_BOOK_CFF) as pdf:
        records = inspect_pdf(pdf)
        rec = next(r for r in records if r.descendant_subtype == "CIDFontType0")
        action = Replace(record=rec, source_path=disk, ttc_face=None)
        _validate_cff_replace(action)  # must not raise


def test_validate_cff_replace_refuses_non_cff_disk_font(make_ttf):
    """If --font-path points at a TTF for a CFF font slot, refuse cleanly."""
    fake = make_ttf("fake.ttf", ps_name="TeXGyreTermes-Regular")
    with pikepdf.open(TINY_BOOK_CFF) as pdf:
        records = inspect_pdf(pdf)
        rec = next(r for r in records if r.descendant_subtype == "CIDFontType0")
        action = Replace(record=rec, source_path=fake, ttc_face=None)
        with pytest.raises(UnsupportedFontError, match="not CFF-flavored"):
            _validate_cff_replace(action)


def test_validate_cff_replace_refuses_mismatched_disk_cff(tmp_path):
    """A disk OTF whose cmap maps the same Unicode values to wrong GIDs → refuse.

    Build a minimal CFF-flavored OTF whose cmap maps 'a' (U+0061) to GID 1,
    but the embedded subset's /ToUnicode says GID 29 should be 'a'. The
    validator should detect the GID mismatch.
    """
    from fontTools.fontBuilder import FontBuilder
    from fontTools.misc.psCharStrings import T2CharString
    from io import BytesIO

    def _empty_cs() -> T2CharString:
        return T2CharString(program=["endchar"])

    fb = FontBuilder(1000, isTTF=False)
    fb.setupGlyphOrder([".notdef", "a", "b"])  # 'a' at GID 1, not GID 29
    fb.setupCharacterMap({0x61: "a", 0x62: "b"})
    fb.setupCFF(
        psName="TeXGyreTermes-Regular",
        fontInfo={"FullName": "Wrong font"},
        charStringsDict={".notdef": _empty_cs(), "a": _empty_cs(), "b": _empty_cs()},
        privateDict={},
    )
    fb.setupHorizontalMetrics({".notdef": (500, 0), "a": (600, 0), "b": (600, 0)})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({"familyName": "Wrong", "styleName": "Regular",
                       "fullName": "Wrong Regular",
                       "psName": "TeXGyreTermes-Regular"})
    fb.setupOS2(sTypoAscender=800, sTypoDescender=-200,
                usWinAscent=800, usWinDescent=200)
    fb.setupPost()
    bad_path = tmp_path / "wrong.otf"
    buf = BytesIO()
    fb.save(buf)
    bad_path.write_bytes(buf.getvalue())

    with pikepdf.open(TINY_BOOK_CFF) as pdf:
        records = inspect_pdf(pdf)
        rec = next(r for r in records if r.descendant_subtype == "CIDFontType0")
        if not rec.used_cids:
            pytest.skip("CFF fixture has no used CIDs")
        action = Replace(record=rec, source_path=bad_path, ttc_face=None)
        with pytest.raises(UnsupportedFontError, match="correspondence check failed"):
            _validate_cff_replace(action)


def test_parse_to_unicode_cmap_bfchar():
    """Sanity test: the fixture's /ToUnicode uses bfchar and decodes correctly."""
    from unsubsetter.applier import _parse_to_unicode_cmap
    with pikepdf.open(TINY_BOOK_CFF) as pdf:
        records = inspect_pdf(pdf)
        rec = next(r for r in records if r.descendant_subtype == "CIDFontType0")
        mapping = _parse_to_unicode_cmap(rec)
    assert mapping is not None
    assert len(mapping) > 0
    # Per direct fixture inspection: CID 0x1D (29) → U+0061 ('a').
    assert mapping[0x1D] == "a"
    # CID 0x7E (126) → ligature U+0066 U+0069 ('fi').
    assert mapping[0x7E] == "fi"


def test_parse_to_unicode_cmap_returns_none_when_absent():
    """If a font record has no /ToUnicode entry, the parser returns None."""
    from unsubsetter.applier import _parse_to_unicode_cmap

    class _FakeRecord:
        font_obj = {}

    assert _parse_to_unicode_cmap(_FakeRecord()) is None


from unsubsetter.applier import _build_widths_array_cff


def test_build_widths_array_cff_covers_used_cids():
    """Width array should contain entries for every used CID."""
    disk = _tex_gyre_termes_path()
    with pikepdf.open(TINY_BOOK_CFF) as pdf:
        records = inspect_pdf(pdf)
        rec = next(r for r in records if r.descendant_subtype == "CIDFontType0")
        assert rec.used_cids, "fixture has no used CIDs"
    from fontTools.ttLib import TTFont
    full_tt = TTFont(str(disk))
    arr = _build_widths_array_cff(full_tt, rec.used_cids)
    # Flatten the run-length structure and pull CID entries.
    cids_present: set[int] = set()
    flat = list(arr)
    i = 0
    while i < len(flat):
        head = int(flat[i])
        run = flat[i + 1]
        cids_present.update(range(head, head + len(run)))
        i += 2
    assert rec.used_cids.issubset(cids_present), \
        f"missing CIDs: {sorted(rec.used_cids - cids_present)}"

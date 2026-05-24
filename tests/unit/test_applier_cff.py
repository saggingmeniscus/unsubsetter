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

"""Unit tests for the CFF apply path and helpers."""
from __future__ import annotations
from pathlib import Path

import pikepdf
import pytest
from fontTools.cffLib import CFFFontSet

from unsubsetter.applier import _read_embedded_cff
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

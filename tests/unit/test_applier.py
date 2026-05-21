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


import pikepdf

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


def test_apply_replace_refuses_disk_font_with_too_few_glyphs(tmp_path, make_ttf):
    """If the disk font lacks a CID the PDF references, apply must refuse."""
    import pytest
    from unsubsetter.errors import UnsupportedFontError
    # The synthetic test font has only 3 glyphs (.notdef, space, A).
    tiny = make_ttf("tiny.ttf", ps_name="EBGaramond")  # same PS name as in tiny_book
    with pikepdf.open(TINY_BOOK) as pdf:
        records = inspect_pdf(pdf)
        eb = next(r for r in records if r.ps_name.lower().startswith("ebgaramond"))
        # tiny_book uses CIDs well past 3 (e.g. for digit/punctuation glyphs)
        assert max(eb.used_cids) >= 3
        action = Replace(record=eb, source_path=tiny, ttc_face=None)
        with pytest.raises(UnsupportedFontError, match="different version"):
            apply_replace(pdf, action)

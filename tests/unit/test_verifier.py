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
    # Produce an output whose page count differs from the original.
    shutil.copy(TINY_BOOK, out)
    with pikepdf.open(out, allow_overwriting_input=True) as pdf:
        if len(pdf.pages) > 1:
            del pdf.pages[-1]
            pdf.save(out)
        else:
            # Single-page original: append a page to get a different count.
            pdf.pages.append(pdf.pages[0])
            pdf.save(out)
    plan = Plan(actions=[])
    report = verify_structural(TINY_BOOK, out, plan)
    assert not report.passed
    assert any("page count" in f.lower() for f in report.failures())

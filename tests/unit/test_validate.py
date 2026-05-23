"""Unit tests for the Validate phase."""
from __future__ import annotations
from pathlib import Path

import pikepdf
import pytest

from unsubsetter.applier import validate_plan, ValidationReport
from unsubsetter.errors import UnsupportedFontError
from unsubsetter.inspector import inspect_pdf
from unsubsetter.planner import Plan, Replace, Skip


TINY_BOOK = Path(__file__).parent.parent / "fixtures" / "tiny_book.pdf"


def _ebgaramond_path() -> Path:
    p = Path.home() / "Library/Fonts/EBGaramond-Regular.ttf"
    if not p.exists():
        pytest.skip("EBGaramond-Regular.ttf not found")
    return p


def test_validate_plan_returns_empty_report_on_passing_truetype():
    with pikepdf.open(TINY_BOOK) as pdf:
        records = inspect_pdf(pdf)
        eb = next(r for r in records if r.ps_name.lower().startswith("ebgaramond"))
        plan = Plan(actions=[Replace(eb, _ebgaramond_path(), None)])
        report = validate_plan(plan)
    assert report.passed
    assert report.failures == []


def test_validate_plan_flags_truetype_with_insufficient_glyphs(tmp_path, make_ttf):
    """If the disk font lacks a referenced CID, validate must flag it."""
    tiny = make_ttf("tiny.ttf", ps_name="EBGaramond")
    with pikepdf.open(TINY_BOOK) as pdf:
        records = inspect_pdf(pdf)
        eb = next(r for r in records if r.ps_name.lower().startswith("ebgaramond"))
        assert max(eb.used_cids) >= 3
        plan = Plan(actions=[Replace(eb, tiny, None)])
        report = validate_plan(plan)
    assert not report.passed
    assert len(report.failures) == 1
    action, msg = report.failures[0]
    assert action.record.ps_name.lower().startswith("ebgaramond")
    assert "different version" in msg


def test_validate_plan_ignores_skip_actions():
    plan = Plan(actions=[Skip(record=None, reason="not subsetted")])
    report = validate_plan(plan)
    assert report.passed
    assert report.failures == []


def test_validation_report_render_has_one_line_per_failure():
    report = ValidationReport(failures=[])
    report.failures.append((None, "first failure detail"))  # type: ignore[arg-type]
    report.failures.append((None, "second failure detail"))  # type: ignore[arg-type]
    text = report.render()
    assert "first failure detail" in text
    assert "second failure detail" in text

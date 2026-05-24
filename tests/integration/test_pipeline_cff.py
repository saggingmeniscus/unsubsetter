"""End-to-end CFF unsubsetting integration tests."""
from pathlib import Path

import pytest
import pikepdf
from click.testing import CliRunner

from unsubsetter.cli import cli
from unsubsetter.inspector import inspect_pdf


TINY_BOOK_CFF = Path(__file__).parent.parent / "fixtures" / "tiny_book_cff.pdf"
TEX_GYRE_TERMES = Path(
    "/usr/local/texlive/2025/texmf-dist/fonts/opentype/public/tex-gyre/"
    "texgyretermes-regular.otf"
)


@pytest.fixture(autouse=True)
def _require_font():
    if not TEX_GYRE_TERMES.exists():
        pytest.skip(f"Required font not installed: {TEX_GYRE_TERMES}")


def test_cff_fix_mode_unsubsets_font(tmp_path):
    out = tmp_path / "out.pdf"
    runner = CliRunner()
    result = runner.invoke(cli, [str(TINY_BOOK_CFF), "--fix", "--output", str(out)])
    assert result.exit_code == 0, result.output
    assert out.exists()
    with pikepdf.open(out) as pdf:
        records = inspect_pdf(pdf)
        cff = next(r for r in records if r.descendant_subtype == "CIDFontType0")
        assert cff.subset_prefix is None


def test_cff_fix_is_idempotent(tmp_path):
    once = tmp_path / "once.pdf"
    runner = CliRunner()
    runner.invoke(cli, [str(TINY_BOOK_CFF), "--fix", "--output", str(once)])

    twice = tmp_path / "twice.pdf"
    result = runner.invoke(cli, [str(once), "--fix", "--output", str(twice)])
    assert result.exit_code == 0, result.output
    assert "REPLACE" not in result.output or result.output.count("REPLACE") == 0


def test_cff_visual_verify_passes_after_fix(tmp_path):
    out = tmp_path / "out.pdf"
    runner = CliRunner()
    result = runner.invoke(cli, [
        str(TINY_BOOK_CFF), "--fix", "--output", str(out), "--verify-visual", "1",
    ])
    assert result.exit_code == 0, result.output
    assert "Visual verification" in result.output
    visual_section = result.output.split("Visual verification:")[-1]
    assert "FAIL" not in visual_section

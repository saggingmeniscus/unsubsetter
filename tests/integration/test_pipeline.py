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

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

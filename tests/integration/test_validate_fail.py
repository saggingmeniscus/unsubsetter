"""End-to-end test of the Validate phase rejecting a mismatched disk font."""
from io import BytesIO
from pathlib import Path

import pytest
from click.testing import CliRunner
from fontTools.fontBuilder import FontBuilder

from unsubsetter.cli import cli


TINY_BOOK_CFF = Path(__file__).parent.parent / "fixtures" / "tiny_book_cff.pdf"


def _make_wrong_cff(path: Path):
    """Synthesize an OTF whose CFF Charset doesn't match TeX Gyre Termes'."""
    from fontTools.misc.psCharStrings import T2CharString

    def _empty_cs() -> T2CharString:
        return T2CharString(program=["endchar"])

    fb = FontBuilder(1000, isTTF=False)
    fb.setupGlyphOrder([".notdef", "WRONG_GLYPH_NAME"])
    fb.setupCharacterMap({0x41: "WRONG_GLYPH_NAME"})
    fb.setupCFF(
        psName="TeXGyreTermes-Regular",
        fontInfo={"FullName": "Wrong"},
        charStringsDict={".notdef": _empty_cs(), "WRONG_GLYPH_NAME": _empty_cs()},
        privateDict={},
    )
    fb.setupHorizontalMetrics({".notdef": (500, 0), "WRONG_GLYPH_NAME": (600, 0)})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({"familyName": "Wrong", "styleName": "Regular",
                       "fullName": "Wrong Regular", "psName": "TeXGyreTermes-Regular"})
    fb.setupOS2(sTypoAscender=800, sTypoDescender=-200,
                usWinAscent=800, usWinDescent=200)
    fb.setupPost()
    buf = BytesIO()
    fb.save(buf)
    path.write_bytes(buf.getvalue())


def test_cli_exits_4_on_validation_failure(tmp_path, monkeypatch):
    """Run unsubsetter with ONLY a deliberately wrong CFF visible to the index.

    Monkeypatch unsubsetter.cli.default_search_paths to return [] so the test
    is deterministic regardless of what fonts exist on the developer's system.
    The CLI then sees only the wrong_dir we provide via --font-path.
    """
    wrong_dir = tmp_path / "wrong_fonts"
    wrong_dir.mkdir()
    _make_wrong_cff(wrong_dir / "wrong.otf")
    out = tmp_path / "out.pdf"

    monkeypatch.setattr("unsubsetter.cli.default_search_paths", lambda: [])

    runner = CliRunner()
    result = runner.invoke(cli, [
        str(TINY_BOOK_CFF), "--fix", "--output", str(out),
        "--font-path", str(wrong_dir),
    ])
    assert result.exit_code == 4, (result.output, result.stderr)
    assert not out.exists()
    assert "Validation failures" in result.stderr
    assert "correspondence" in result.stderr.lower()

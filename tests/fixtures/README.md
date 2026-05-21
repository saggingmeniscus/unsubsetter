# Test fixtures

## tiny_book.pdf

A minimal XeLaTeX-generated PDF with one subsetted CID TrueType font, used by
integration tests in `tests/integration/test_pipeline.py`.

Regenerate from `tiny_book.tex`:

    cd tests/fixtures
    xelatex tiny_book.tex
    rm -f tiny_book.aux tiny_book.log tiny_book.out

Requirements to regenerate: XeLaTeX (TeX Live) and the `EB Garamond` font
installed system-wide (the user has `~/Library/Fonts/EBGaramond-Regular.ttf`).
If you substitute a different font, update the `EXPECTED_SUBSET_FONT_PS_NAME`
constant in `tests/integration/test_pipeline.py`.

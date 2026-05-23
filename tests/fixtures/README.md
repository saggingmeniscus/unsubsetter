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
If you substitute a different font, search the test files for `ebgaramond`
(case-insensitive substring used by `tests/unit/test_inspector.py`,
`tests/unit/test_applier.py`, `tests/unit/test_verifier.py`, and
`tests/integration/test_pipeline.py`) and update accordingly.

## tiny_book_cff.pdf

A minimal XeLaTeX-generated PDF with one subsetted CID CFF font, used by
integration tests in `tests/integration/test_pipeline_cff.py`.

Regenerate from `tiny_book_cff.tex`:

    cd tests/fixtures
    xelatex tiny_book_cff.tex
    rm -f tiny_book_cff.aux tiny_book_cff.log tiny_book_cff.out

Requirements to regenerate: XeLaTeX (TeX Live) with the `tex-gyre` opentype
package installed (`/usr/local/texlive/2025/texmf-dist/fonts/opentype/public/tex-gyre/texgyretermes-regular.otf`).

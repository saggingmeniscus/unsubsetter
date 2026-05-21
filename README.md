# unsubsetter

Re-embed full (non-subset) fonts in PDFs so Amazon KDP's preflight check accepts them.

V1 handles **CID TrueType fonts only.** CFF (CIDFontType0) and simple Type 1 fonts
are reported but skipped.

## Install

Install the `unsubsetter` command into an isolated environment on your PATH:

    uv tool install git+https://github.com/saggingmeniscus/unsubsetter

Or, from a local clone:

    git clone https://github.com/saggingmeniscus/unsubsetter
    cd unsubsetter
    uv tool install .

Both install from source; a published PyPI release will come later.

## Usage

Inspect (default — no writes):

    unsubsetter book.pdf

Fix (writes `book.unsubset.pdf` by default):

    unsubsetter --fix book.pdf

Filter to specific fonts:

    unsubsetter --fix --only Preciosa,Janson book.pdf

With visual verification (renders N random pages and pixel-diffs them):

    unsubsetter --fix --verify-visual 10 book.pdf

## Acceptance procedure (manual — pre-KDP gate)

Before uploading to KDP, run the following on the production PDF:

1. **Inspect:**
   ```
   unsubsetter ~/books/myproject/interior.pdf
   ```
   Confirm the plan covers Preciosa (the font KDP flagged). Note any `SKIP` lines
   that mention missing-on-disk fonts and resolve them before proceeding.

2. **Fix with visual sampling:**
   ```
   unsubsetter --fix --verify-visual 10 \
     ~/books/myproject/interior.pdf
   ```
   This writes `interior.unsubset.pdf`.

3. **Independent structural check:**
   ```
   pdffonts interior.unsubset.pdf
   ```
   Confirm `sub=no` on Preciosa and every other previously-subset CID TrueType.

4. **Spot-check 5 pages visually** in Preview/Acrobat — focus on:
   - Pages with drop caps (uses CFF fonts skipped by V1; should look identical)
   - Pages with math symbols (CMSY7 — also skipped)
   - Heavy-text body pages (Janson Roman/Italic)

5. **Upload to KDP.** If it bounces again on a *different* font, run unsubsetter
   again with `--only THAT_FONT` to test in isolation, or report the issue.

## Out-of-scope fallbacks (V2 candidates)

The two CFF fonts (`P22PreissigCalligraphic`, `BradleyInitials`) appear only on
drop-cap pages. If KDP rejects those, the V1 workaround is to splice in
outlined versions of just those pages.

## Development

Set up the project and run the test suite:

    uv sync --extra dev
    uv run pytest

# unsubsetter

Re-embed full (non-subset) versions of fonts in PDFs.

PDF generators often *subset* embedded fonts, keeping only the glyphs a
document uses and marking the font's PostScript name with a six-letter
`ABCDEF+` prefix. Some preflight checkers treat subsetted fonts as "not
embedded" even though they are. `unsubsetter` swaps each subset for the
complete font found on disk. It was built to get a book past Amazon
KDP's preflight check, but applies to any PDF that needs non-subsetted
embedded fonts.

It handles **CID TrueType and CID CFF fonts.** Other font types are
detected and reported, but left unchanged — see [Limitations](#limitations).

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

    unsubsetter --fix --only Garamond,Helvetica book.pdf

With visual verification (renders N random pages and pixel-diffs them):

    unsubsetter --fix --verify-visual 10 book.pdf

## Example: preparing a PDF for Amazon KDP

KDP's preflight check is the use case this tool was built for — it can
reject a PDF whose fonts look un-embedded, which subsetting may trigger.
A careful pre-upload pass:

1. **Inspect** (default mode, no writes):
   ```
   unsubsetter interior.pdf
   ```
   Confirm the plan covers the font KDP flagged. Resolve any surprising
   `SKIP` lines — e.g. a font that can't be found on disk — first.

2. **Fix with visual sampling:**
   ```
   unsubsetter --fix --verify-visual 10 interior.pdf
   ```
   This writes `interior.unsubset.pdf` and pixel-diffs 10 random pages
   against the original.

3. **Independent structural check:**
   ```
   pdffonts interior.unsubset.pdf
   ```
   Confirm `sub=no` on every previously-subset CID TrueType or CID CFF font.

4. **Spot-check a few pages** in a PDF viewer, paying attention to pages
   that use fonts the tool reported as skipped — those pass through
   unchanged and should look identical.

5. **Upload to KDP.** If it flags a *different* font, re-run with
   `--only THAT_FONT` to test it in isolation, or report the issue.

### Troubleshooting exit code 4

If `unsubsetter --fix` exits with code 4, the disk font on your system
doesn't match the subset embedded in the PDF for one or more CFF fonts.
The report names the offending fonts. Either:

- Locate the matching font version and supply it via `--font-path
  /path/to/font/dir`; or
- Re-run with `--exclude FONT_NAME` to leave that font alone (it'll stay
  subset in the output).

## Limitations

V2 handles **CID TrueType** (`CIDFontType2`) and **CID CFF** (`CIDFontType0`)
subsetted fonts. Simple Type 1 (`/FontFile`) and Type 1C
(`/FontFile3 /Subtype Type1C`) are detected and reported, but left unchanged.
If a preflight checker flags one of those, outlining (converting the
affected glyphs to vector paths) is the usual workaround until those types
are supported.

For CFF fonts, `unsubsetter` runs a glyph-correspondence check between the
embedded subset and the disk full font. If they don't agree on glyph identity
(e.g., your disk font is a different version than the one originally
embedded), the run exits with code 4 and writes no output. Either supply
the matching font via `--font-path` or skip that font with `--exclude`.

## Development

Set up the project and run the test suite:

    uv sync --extra dev
    uv run pytest

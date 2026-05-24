from unsubsetter.inspector import split_subset_prefix


def test_split_subset_prefix_present():
    assert split_subset_prefix("ABCDEF+Preciosa") == ("ABCDEF", "Preciosa")


def test_split_subset_prefix_absent():
    assert split_subset_prefix("Preciosa") == (None, "Preciosa")


def test_split_subset_prefix_wrong_length_is_not_a_prefix():
    # 5 letters + '+' is not a valid subset prefix.
    assert split_subset_prefix("ABCDE+Preciosa") == (None, "ABCDE+Preciosa")


def test_split_subset_prefix_must_be_uppercase():
    # lowercase prefix is not a valid subset prefix per PDF spec.
    assert split_subset_prefix("abcdef+Preciosa") == (None, "abcdef+Preciosa")


def test_split_subset_prefix_with_spaces_in_name():
    assert split_subset_prefix("ZILMPO+Horst Regular") == ("ZILMPO", "Horst Regular")


def test_split_subset_prefix_strips_identity_cmap_suffix():
    """Type0 BaseFont may be <prefix>+<font-name>-<cmap-name>; strip the CMap part."""
    from unsubsetter.inspector import split_subset_prefix
    # Identity-H (the XeLaTeX CFF case)
    assert split_subset_prefix("LHTESP+TeXGyreTermes-Regular-Identity-H") == (
        "LHTESP", "TeXGyreTermes-Regular",
    )
    # Identity-V (vertical text)
    assert split_subset_prefix("ABCDEF+SomeFont-Identity-V") == (
        "ABCDEF", "SomeFont",
    )
    # No CMap suffix — unchanged
    assert split_subset_prefix("ABCDEF+SomeFont") == ("ABCDEF", "SomeFont")
    # No prefix, has CMap suffix
    assert split_subset_prefix("SomeFont-Identity-H") == (None, "SomeFont")
    # No prefix, no CMap suffix
    assert split_subset_prefix("SomeFont") == (None, "SomeFont")


from pathlib import Path

import pikepdf

from unsubsetter.inspector import FontRecord, inspect_pdf


TINY_BOOK = Path(__file__).parent.parent / "fixtures" / "tiny_book.pdf"


def test_inspect_pdf_finds_subset_font():
    with pikepdf.open(TINY_BOOK) as pdf:
        records = inspect_pdf(pdf)
    assert len(records) >= 1
    # tiny_book.pdf uses EB Garamond, which XeLaTeX subsets.
    eb = next(
        (r for r in records if r.ps_name.lower().startswith("ebgaramond")),
        None,
    )
    assert eb is not None, f"EBGaramond not found in {[r.ps_name for r in records]}"
    assert eb.subset_prefix is not None
    assert len(eb.subset_prefix) == 6
    assert eb.subtype == "Type0"
    assert eb.descendant_subtype == "CIDFontType2"
    assert eb.has_font_file is True
    assert eb.font_file_kind == "FontFile2"


def test_inspect_pdf_used_cids_nonempty_for_text_font():
    with pikepdf.open(TINY_BOOK) as pdf:
        records = inspect_pdf(pdf)
    eb = next(r for r in records if r.ps_name.lower().startswith("ebgaramond"))
    # The fixture document has English text so we expect CIDs to be present.
    assert len(eb.used_cids) > 0


def test_inspect_pdf_does_not_return_cid_descendants_as_top_level():
    with pikepdf.open(TINY_BOOK) as pdf:
        records = inspect_pdf(pdf)
    # Every returned record must be a top-level font subtype, not a descendant.
    for r in records:
        assert r.subtype not in ("CIDFontType0", "CIDFontType2"), (
            f"inspect_pdf returned a CID descendant as a top-level record: "
            f"{r.ps_name} {r.subtype}"
        )

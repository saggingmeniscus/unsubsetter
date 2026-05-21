from unsubsetter.font_index import normalize_name


def test_normalize_name_lowercases():
    assert normalize_name("Preciosa") == "preciosa"


def test_normalize_name_strips_spaces():
    assert normalize_name("Horst Regular") == "horstregular"


def test_normalize_name_strips_punctuation_and_underscores():
    assert normalize_name("EB-Garamond_Regular") == "ebgaramondregular"


def test_normalize_name_does_not_strip_subset_prefix():
    # Subset prefix stripping is the inspector's job, not normalize_name's,
    # so the rule lives in one place.
    assert normalize_name("ABCDEF+Preciosa") == "abcdefpreciosa"


def test_make_ttf_fixture_produces_valid_ttf(make_ttf):
    from fontTools.ttLib import TTFont
    path = make_ttf("test.ttf", ps_name="TestPSName")
    tt = TTFont(str(path))
    assert tt["name"].getDebugName(6) == "TestPSName"


from pathlib import Path

from unsubsetter.font_index import FontIndexEntry, read_font_entries


def test_read_font_entries_single_ttf(make_ttf):
    path = make_ttf("foo.ttf", ps_name="MyFontPS", family="MyFamily", subfamily="Bold")
    entries = read_font_entries(path)
    assert len(entries) == 1
    e = entries[0]
    assert isinstance(e, FontIndexEntry)
    assert e.path == path
    assert e.ttc_face is None
    assert e.ps_name == "MyFontPS"
    assert e.family == "MyFamily"
    assert e.subfamily == "Bold"


def test_read_font_entries_ttc_yields_one_per_face(make_ttc):
    path = make_ttc("bundle.ttc", faces=[
        {"ps_name": "FaceA", "family": "F", "subfamily": "Regular"},
        {"ps_name": "FaceB", "family": "F", "subfamily": "Bold"},
    ])
    entries = read_font_entries(path)
    assert len(entries) == 2
    assert {e.ps_name for e in entries} == {"FaceA", "FaceB"}
    assert {e.ttc_face for e in entries} == {0, 1}

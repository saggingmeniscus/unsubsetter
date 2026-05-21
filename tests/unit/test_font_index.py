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


from unsubsetter.font_index import FontIndex


def test_font_index_scans_directory(make_ttf, tmp_path):
    make_ttf("a.ttf", ps_name="FontA", family="F", subfamily="Regular")
    make_ttf("b.otf", ps_name="FontB", family="F", subfamily="Italic")
    idx = FontIndex.build([tmp_path])
    assert idx.lookup("FontA") is not None
    assert idx.lookup("FontB") is not None
    assert idx.lookup("FontC") is None


def test_font_index_lookup_is_case_and_punctuation_insensitive(make_ttf, tmp_path):
    make_ttf("h.ttf", ps_name="Horst", family="Horst", subfamily="Regular")
    idx = FontIndex.build([tmp_path])
    # The PDF often says "Horst Regular" while the disk has "Horst";
    # we look up by family+subfamily concat too.
    assert idx.lookup("HORST") is not None
    assert idx.lookup("horst regular") is not None  # family + subfamily


def test_font_index_returns_first_match_with_face_index(make_ttc, tmp_path):
    path = make_ttc("bundle.ttc", faces=[
        {"ps_name": "FaceA", "family": "F", "subfamily": "Regular"},
        {"ps_name": "FaceB", "family": "F", "subfamily": "Bold"},
    ])
    idx = FontIndex.build([tmp_path])
    entry = idx.lookup("FaceB")
    assert entry is not None
    assert entry.path == path
    assert entry.ttc_face == 1


def test_font_index_ignores_non_font_files(tmp_path):
    (tmp_path / "readme.txt").write_text("hi")
    (tmp_path / "subdir").mkdir()
    idx = FontIndex.build([tmp_path])
    assert idx.lookup("anything") is None


def test_font_index_recurses_into_subdirectories(make_ttf, tmp_path):
    # Build a TTF at the tmp_path root, then move it into a nested subdir so
    # the only copy on disk is below the root we hand to FontIndex.build.
    src = make_ttf("nested_font.ttf", ps_name="NestedFont")
    subdir = tmp_path / "deep" / "nested"
    subdir.mkdir(parents=True)
    src.rename(subdir / src.name)
    idx = FontIndex.build([tmp_path])
    assert idx.lookup("NestedFont") is not None


from unsubsetter.font_index import default_search_paths


def test_default_search_paths_returns_existing_dirs():
    # Smoke test: at least one path exists on this dev machine (macOS).
    paths = default_search_paths()
    assert all(p.exists() for p in paths)

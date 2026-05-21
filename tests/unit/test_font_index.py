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

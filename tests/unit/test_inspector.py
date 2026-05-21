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

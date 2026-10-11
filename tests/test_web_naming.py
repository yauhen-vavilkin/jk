"""Picking a name nothing else on the board is using."""

from __future__ import annotations

from jk.web.naming import copy_name, free_name, is_taken, tidy


def test_a_free_name_is_kept_exactly_as_it_is() -> None:
    assert free_name("Nightly Cypress", ["Rebuild EDEV"]) == "Nightly Cypress"


def test_a_name_that_only_looks_like_a_copy_is_still_kept() -> None:
    # Nothing else is called this, so it is the user's name, not a derived one.
    assert free_name("Nightly copy", ["Rebuild EDEV"]) == "Nightly copy"


def test_a_taken_name_becomes_a_copy_and_then_counts() -> None:
    taken = ["Nightly"]
    assert free_name("Nightly", taken) == "Nightly copy"
    taken.append("Nightly copy")
    assert free_name("Nightly", taken) == "Nightly copy 2"
    taken.append("Nightly copy 2")
    assert free_name("Nightly", taken) == "Nightly copy 3"


def test_duplicating_a_copy_counts_instead_of_stacking_the_word() -> None:
    assert free_name("Nightly copy", ["Nightly", "Nightly copy"]) == "Nightly copy 2"
    assert free_name("Nightly copy 2", ["Nightly", "Nightly copy", "Nightly copy 2"]) == (
        "Nightly copy 3"
    )


def test_case_and_stray_spaces_do_not_make_two_names_different() -> None:
    assert is_taken("rebuild EDEV", ["Rebuild edev"]) is True
    assert is_taken("  Nightly  ", ["Nightly"]) is True
    assert is_taken("Nightly run", ["Nightly"]) is False


def test_a_name_is_stored_without_its_edges() -> None:
    assert tidy("  Nightly  ") == "Nightly"
    assert free_name("  Nightly  ", []) == "Nightly"


def test_a_copy_is_named_after_what_it_copies() -> None:
    assert free_name("Nightly", []) == "Nightly"
    assert copy_name("Nightly", ["Nightly"]) == "Nightly copy"
    assert copy_name("Nightly", ["Nightly", "Nightly copy"]) == "Nightly copy 2"


def test_copying_a_copy_counts_from_the_original() -> None:
    taken = ["Nightly", "Nightly copy"]
    # Not `Nightly copy copy`: the tail is stripped before the walk.
    assert copy_name("Nightly copy", taken) == "Nightly copy 2"
    assert copy_name("Nightly copy 2", [*taken, "Nightly copy 2"]) == "Nightly copy 3"


def test_a_copy_takes_a_free_name_even_when_nothing_is_taken() -> None:
    # `copy_name` always makes a copy; it is `free_name` that keeps a name as it is.
    assert copy_name("Nightly", []) == "Nightly copy"

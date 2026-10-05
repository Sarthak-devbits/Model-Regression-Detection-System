import pytest
from pydantic import ValidationError

from shared.categories import Category
from shared.golden import Difficulty


# dummy comment
def test_valid_case_loads_into_typed_objects(make_case, make_dataset) -> None:
    dataset = make_dataset([make_case(1, category="technical", difficulty="hard")])
    case = dataset.cases[0]
    assert case.expected.category is Category.TECHNICAL
    assert case.expected_difficulty is Difficulty.HARD


def test_unknown_category_is_rejected(make_case, make_dataset) -> None:
    with pytest.raises(ValidationError, match="expected.category"):
        make_dataset([make_case(1, category="sales")])


def test_misspelled_field_is_rejected(make_case, make_dataset) -> None:
    case = make_case(1)
    case["expected"]["categroy"] = "billing"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        make_dataset([case])


def test_case_id_must_match_pattern(make_case, make_dataset) -> None:
    with pytest.raises(ValidationError, match="id"):
        make_dataset([make_case(1, id="billing-1")])


def test_duplicate_ids_are_rejected(make_case, make_dataset) -> None:
    with pytest.raises(ValidationError, match="duplicate case ids"):
        make_dataset([make_case(1), make_case(1, email="A different email body here.")])


def test_added_in_cannot_be_newer_than_dataset(make_case, make_dataset) -> None:
    with pytest.raises(ValidationError, match="added_in=v2"):
        make_dataset([make_case(1, added_in="v2")], version="v1")


def test_duplicate_edge_case_tags_are_rejected(make_case, make_dataset) -> None:
    with pytest.raises(ValidationError, match="more than once"):
        make_dataset([make_case(1, edge_cases=["typos", "typos"])])


def test_whitespace_is_stripped(make_case, make_dataset) -> None:
    dataset = make_dataset([make_case(1, email="   padded email body here   ")])
    assert dataset.cases[0].input.email == "padded email body here"


def test_content_hash_ignores_key_order(make_case, make_dataset) -> None:
    case = make_case(1)
    reordered = dict(reversed(list(case.items())))
    assert make_dataset([case]).content_hash() == make_dataset([reordered]).content_hash()


def test_content_hash_changes_when_a_label_changes(make_case, make_dataset) -> None:
    original = make_dataset([make_case(1, category="billing")])
    relabelled = make_dataset([make_case(1, category="account")])
    assert original.content_hash() != relabelled.content_hash()

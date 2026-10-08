"""Hermetic unit tests for the runner exact-ID collection hook."""
from scripts.runner_plugin import (
    extract_test_case_id_from_item,
    filter_items_by_test_case_ids,
)


class DummyCallSpec:
    def __init__(self, params):
        self.params = params


class DummyItem:
    def __init__(self, name: str, params: dict = None, doc: str = None):
        self.name = name
        self.callspec = DummyCallSpec(params) if params is not None else None
        self.obj = type("Obj", (), {"__doc__": doc}) if doc else None


def test_extract_case_id_from_callspec_params():
    item1 = DummyItem("test_one", params={"test_case_id": "TC_PARAM_01"})
    assert extract_test_case_id_from_item(item1) == "TC_PARAM_01"

    item2 = DummyItem("test_two", params={"description": "TC_IN_DESC_02: sample test"})
    assert extract_test_case_id_from_item(item2) == "TC_IN_DESC_02"


def test_extract_case_id_from_docstring():
    item = DummyItem("test_three", doc="Test docstring referencing TC_DOC_03 in text")
    assert extract_test_case_id_from_item(item) == "TC_DOC_03"


def test_filter_items_exact_match_prevents_prefix_collision():
    # TC_01 vs TC_012 (prefix collision)
    item_short = DummyItem("test_short", params={"test_case_id": "TC_01"})
    item_long = DummyItem("test_long", params={"test_case_id": "TC_012"})
    item_other = DummyItem("test_other", params={"test_case_id": "TC_99"})

    items = [item_short, item_long, item_other]

    # Exact filter for TC_01 only
    selected, deselected = filter_items_by_test_case_ids(items, "TC_01")
    assert len(selected) == 1
    assert selected[0] is item_short
    assert item_long in deselected
    assert item_other in deselected


def test_filter_items_with_multiple_ids():
    item1 = DummyItem("test_1", params={"test_case_id": "TC_A"})
    item2 = DummyItem("test_2", params={"test_case_id": "TC_B"})
    item3 = DummyItem("test_3", params={"test_case_id": "TC_C"})

    items = [item1, item2, item3]

    selected, deselected = filter_items_by_test_case_ids(items, "TC_A, TC_C")
    assert len(selected) == 2
    assert item1 in selected
    assert item3 in selected
    assert deselected == [item2]


def test_filter_items_empty_env_keeps_all():
    item1 = DummyItem("test_1", params={"test_case_id": "TC_A"})
    item2 = DummyItem("test_2", params={"test_case_id": "TC_B"})
    items = [item1, item2]

    selected, deselected = filter_items_by_test_case_ids(items, "")
    assert len(selected) == 2
    assert len(deselected) == 0

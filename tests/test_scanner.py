"""Tests for static AST TCMS scanner."""
import json
import pytest
from pathlib import Path
from scripts.tcms_scan import scan_repository
from app.services import db


def test_scanner_never_connects_to_db(tmp_path, monkeypatch):
    """Proves the scanner does not call db.query or db.execute."""
    called = []

    def mock_query(*args, **kwargs):
        called.append("query")
        raise AssertionError("Scanner must never query the database!")

    def mock_execute(*args, **kwargs):
        called.append("execute")
        raise AssertionError("Scanner must never execute database statements!")

    monkeypatch.setattr(db, "query", mock_query)
    monkeypatch.setattr(db, "execute", mock_execute)

    # Create dummy test files
    dummy_test = tmp_path / "test_dummy.py"
    dummy_test.write_text("""
import pytest

@pytest.mark.parametrize("test_case_id, payload", [
    ("TC_SAMPLE_01", {"a": 1}),
])
def test_sample(test_case_id, payload):
    '''Test sample docstring'''
    pass
""", encoding="utf-8")

    cases, hygiene = scan_repository(tmp_path)
    assert len(called) == 0, "Database was contacted during static scan!"
    assert len(cases) == 1
    assert cases[0]["case_id"] == "TC_SAMPLE_01"


def test_scanner_extracts_parametrize_with_test_case_ids(tmp_path):
    test_file = tmp_path / "test_with_helper.py"
    test_file.write_text("""
import pytest

def with_test_case_ids(ids, rows):
    return rows

@pytest.mark.parametrize("test_case_id, value", with_test_case_ids(["TC_HELPER_01", "TC_HELPER_02"], [1, 2]))
def test_with_helper_call(test_case_id, value):
    pass
""", encoding="utf-8")

    cases, hygiene = scan_repository(tmp_path)
    cids = [c["case_id"] for c in cases]
    assert "TC_HELPER_01" in cids
    assert "TC_HELPER_02" in cids


def test_scanner_extracts_regex_from_description(tmp_path):
    test_file = tmp_path / "test_desc.py"
    test_file.write_text("""
import pytest

@pytest.mark.parametrize("description, param", [
    ("TC_POINTS_CALC_01: Valid user transaction", 10),
    ("GRPC_BALANCE_02: Check gRPC stream", 20),
])
def test_via_description(description, param):
    pass
""", encoding="utf-8")

    cases, hygiene = scan_repository(tmp_path)
    cids = [c["case_id"] for c in cases]
    assert "TC_POINTS_CALC_01" in cids
    assert "GRPC_BALANCE_02" in cids


def test_scanner_detects_ambiguous_and_substring_unsafe_ids(tmp_path):
    f1 = tmp_path / "test_file_one.py"
    f1.write_text("""
import pytest

@pytest.mark.parametrize("test_case_id", ["TC_SHARED_ID", "TC_PREFIX"])
def test_function_one(test_case_id):
    pass
""", encoding="utf-8")

    f2 = tmp_path / "test_file_two.py"
    f2.write_text("""
import pytest

# TC_SHARED_ID reused in another file/function -> ambiguous
# TC_PREFIX_EXTENDED starts with TC_PREFIX -> TC_PREFIX is substring_unsafe
@pytest.mark.parametrize("test_case_id", ["TC_SHARED_ID", "TC_PREFIX_EXTENDED"])
def test_function_two(test_case_id):
    pass
""", encoding="utf-8")

    cases, hygiene = scan_repository(tmp_path)
    cases_map = {c["case_id"]: c for c in cases}

    # TC_SHARED_ID is in both functions -> ambiguous
    assert cases_map["TC_SHARED_ID"]["id_status"] == "ambiguous"
    assert "TC_SHARED_ID" in hygiene["ambiguous_ids"]

    # TC_PREFIX is a prefix of TC_PREFIX_EXTENDED -> substring_unsafe
    assert cases_map["TC_PREFIX"]["substring_unsafe"] is True
    assert "TC_PREFIX" in hygiene["substring_unsafe_ids"]

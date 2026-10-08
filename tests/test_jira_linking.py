"""Tests for Jira ticket linking, format validation, and soft-delete semantics."""
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.services import tcms_store

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_jira_cases(fake_db):
    tcms_store.assign_role("editor@vananam.com", "editor", assigned_by="system")
    tcms_store.create_case({"case_id": "TC_JIRA_TEST_1", "title": "Case 1"})
    tcms_store.create_case({"case_id": "TC_JIRA_TEST_2", "title": "Case 2"})


def test_valid_jira_key_linking():
    headers = {"X-User-Email": "editor@vananam.com"}
    response = client.post(
        "/api/tcms/cases/TC_JIRA_TEST_1/jira",
        json={"jira_key": "REW-1234"},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["link"]["jira_key"] == "REW-1234"


def test_invalid_jira_key_rejected():
    headers = {"X-User-Email": "editor@vananam.com"}
    invalid_keys = [
        "rew-123",       # lowercase
        "123-REW",       # starts with number
        "INVALID",       # no hyphen and number
        "REW-",          # no number
        "-123",          # no project key
        "R-123",         # single letter project key (PRD requires ^[A-Z][A-Z0-9]+-\d+$)
        "REW 123",       # space
    ]
    for key in invalid_keys:
        response = client.post(
            "/api/tcms/cases/TC_JIRA_TEST_1/jira",
            json={"jira_key": key},
            headers=headers,
        )
        assert response.status_code == 422, f"Key '{key}' should have been rejected with 422"


def test_idempotent_duplicate_linking():
    headers = {"X-User-Email": "editor@vananam.com"}
    # First link
    r1 = client.post(
        "/api/tcms/cases/TC_JIRA_TEST_1/jira",
        json={"jira_key": "REW-888"},
        headers=headers,
    )
    assert r1.status_code == 200

    # Second link with same key
    r2 = client.post(
        "/api/tcms/cases/TC_JIRA_TEST_1/jira",
        json={"jira_key": "REW-888"},
        headers=headers,
    )
    assert r2.status_code == 200
    assert r2.json()["link"]["jira_key"] == "REW-888"


def test_unlink_and_relink_lifecycle():
    headers = {"X-User-Email": "editor@vananam.com"}

    # Link
    client.post("/api/tcms/cases/TC_JIRA_TEST_1/jira", json={"jira_key": "REW-999"}, headers=headers)

    # Unlink
    un_resp = client.delete("/api/tcms/cases/TC_JIRA_TEST_1/jira/REW-999", headers=headers)
    assert un_resp.status_code == 200

    # Unlinked link should no longer appear in active links
    c_resp = client.get("/api/tcms/cases/TC_JIRA_TEST_1", headers=headers)
    links = c_resp.json()["jira_links"]
    assert not any(l["jira_key"] == "REW-999" for l in links)

    # Re-link restores it
    re_resp = client.post("/api/tcms/cases/TC_JIRA_TEST_1/jira", json={"jira_key": "REW-999"}, headers=headers)
    assert re_resp.status_code == 200

    c_resp_after = client.get("/api/tcms/cases/TC_JIRA_TEST_1", headers=headers)
    links_after = c_resp_after.json()["jira_links"]
    assert any(l["jira_key"] == "REW-999" for l in links_after)


def test_filtering_cases_by_jira_key():
    headers = {"X-User-Email": "editor@vananam.com"}
    link_resp = client.post("/api/tcms/cases/TC_JIRA_TEST_1/jira", json={"jira_key": "REW-7001"}, headers=headers)
    assert link_resp.status_code == 200

    # Query with jira_key filter
    response = client.get("/api/tcms/cases?jira_key=REW-7001", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["cases"][0]["case_id"] == "TC_JIRA_TEST_1"

    # Query by dedicated endpoint
    ep_resp = client.get("/api/tcms/jira/REW-7001/cases", headers=headers)
    assert ep_resp.status_code == 200
    assert ep_resp.json()["total"] == 1


def test_bulk_linking_from_pasted_ids():
    headers = {"X-User-Email": "editor@vananam.com"}
    payload = {
        "case_ids": ["TC_JIRA_TEST_1", "TC_JIRA_TEST_2"],
        "jira_key": "REW-8002",
    }
    response = client.post("/api/tcms/jira/bulk", json=payload, headers=headers)
    assert response.status_code == 200, response.json()
    data = response.json()
    assert data["total_linked"] == 2
    assert "TC_JIRA_TEST_1" in data["linked"]
    assert "TC_JIRA_TEST_2" in data["linked"]

"""Tests for AI agent JSON export endpoint."""
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.services import tcms_store

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_ai_export_cases(fake_db):
    # Active case with business rule and steps
    tcms_store.create_case({
        "case_id": "TC_AI_ACTIVE_01",
        "title": "Calculate loyalty point multipliers",
        "area": "rewards",
        "test_type": "api",
        "status": "active",
        "steps": "1. Add gold tier user\n2. Purchase $10 item\n3. Check 2x points",
        "business_rule": "Gold tier members receive 2x points on all purchases",
        "expected_result": "20 points credited to wallet",
        "id_status": "unique",
    })
    tcms_store.link_jira("TC_AI_ACTIVE_01", "REW-3333", user_email="qa@vananam.com")

    # Draft case (should not be in active export)
    tcms_store.create_case({
        "case_id": "TC_AI_DRAFT_02",
        "title": "Unfinished draft case",
        "status": "draft",
    })


def test_ai_export_endpoint_returns_active_cases():
    headers = {"X-User-Email": "viewer@vananam.com"}
    response = client.get("/api/tcms/export.json", headers=headers)
    assert response.status_code == 200
    data = response.json()

    assert "metadata" in data
    assert data["metadata"]["schema_version"] == "1.0.0"
    assert data["metadata"]["total_cases"] == 1

    cases = data["cases"]
    assert len(cases) == 1
    c = cases[0]
    assert c["case_id"] == "TC_AI_ACTIVE_01"
    assert "Gold tier members receive 2x points" in c["business_rule"]
    assert "1. Add gold tier user" in c["steps"]
    assert "20 points credited" in c["expected_result"]
    assert c["id_status"] == "unique"
    assert "REW-3333" in c["jira_links"]


def test_ai_export_is_read_only():
    headers = {"X-User-Email": "viewer@vananam.com"}
    # POST to export.json is not allowed
    post_resp = client.post("/api/tcms/export.json", json={}, headers=headers)
    assert post_resp.status_code == 405

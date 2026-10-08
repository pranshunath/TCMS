"""Tests for TCMS server-rendered HTML UI endpoints and role enforcement."""
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.services import tcms_store

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_ui_case(fake_db):
    tcms_store.assign_role("editor@vananam.com", "editor", assigned_by="system")
    tcms_store.create_case(
        {
            "case_id": "TC_UI_001",
            "title": "UI Test Case Title",
            "area": "navigation",
            "steps": "1. Open app\n2. Click nav",
            "status": "draft",
        },
        user_email="system",
    )


def test_ui_list_page_loads_for_viewer():
    headers = {"X-User-Email": "viewer@vananam.com"}
    response = client.get("/tcms", headers=headers)
    assert response.status_code == 200
    assert "TC_UI_001" in response.text
    assert "Test Case Management" in response.text


def test_ui_list_page_loads_without_headers_in_dev_mode():
    # Directly simulates browser request with no custom headers
    response = client.get("/tcms")
    assert response.status_code == 200
    assert "TC_UI_001" in response.text


def test_ui_detail_page_loads_for_viewer():
    headers = {"X-User-Email": "viewer@vananam.com"}
    response = client.get("/tcms/cases/TC_UI_001", headers=headers)
    assert response.status_code == 200
    assert "TC_UI_001" in response.text
    assert "UI Test Case Title" in response.text
    # Viewer must not see edit button
    assert "✏️ Edit Case" not in response.text


def test_ui_detail_page_shows_edit_for_editor():
    headers = {"X-User-Email": "editor@vananam.com"}
    response = client.get("/tcms/cases/TC_UI_001", headers=headers)
    assert response.status_code == 200
    assert "✏️ Edit Case" in response.text


def test_ui_edit_page_blocks_viewer_with_403():
    headers = {"X-User-Email": "viewer@vananam.com"}
    response = client.get("/tcms/cases/TC_UI_001/edit", headers=headers)
    assert response.status_code == 403


def test_ui_edit_page_allows_editor():
    headers = {"X-User-Email": "editor@vananam.com"}
    response = client.get("/tcms/cases/TC_UI_001/edit", headers=headers)
    assert response.status_code == 200
    assert "Edit Test Case" in response.text


def test_ui_submit_edit_updates_and_redirects():
    headers = {"X-User-Email": "editor@vananam.com"}
    form_data = {
        "title": "Updated Via UI Form",
        "area": "navigation",
        "test_type": "api",
        "status": "active",
        "steps": "New Steps via Form",
        "business_rule": "Rule via Form",
        "expected_result": "Result via Form",
        "change_summary": "UI edit test",
    }
    response = client.post(
        "/tcms/cases/TC_UI_001/edit",
        data=form_data,
        headers=headers,
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/tcms/cases/TC_UI_001"

    # Verify updated in DB
    updated = tcms_store.get_case("TC_UI_001")
    assert updated["title"] == "Updated Via UI Form"
    assert updated["version"] == 2
    assert updated["status"] == "active"


def test_ui_jira_compliance_report_loads():
    headers = {"X-User-Email": "viewer@vananam.com"}
    tcms_store.link_jira("TC_UI_001", "REW-1234", user_email="qa@vananam.com")

    response = client.get("/tcms/jira/REW-1234", headers=headers)
    assert response.status_code == 200
    assert "Jira Compliance Report" in response.text
    assert "REW-1234" in response.text
    assert "TC_UI_001" in response.text
    assert "/api/tcms/jira/REW-1234/report.csv" in response.text
    assert "/api/tcms/jira/REW-1234/audit-pack" in response.text

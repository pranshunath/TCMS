"""Tests for TCMS API endpoints, RBAC permissions, and version incrementing."""
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.services import tcms_store

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_roles_and_case(fake_db):
    """Seed test users and a sample test case."""
    # Config admins in settings are admin@vananam.com
    # Seed editor
    tcms_store.assign_role("editor@vananam.com", "editor", assigned_by="system")

    # Seed test case
    tcms_store.create_case(
        {
            "case_id": "TC_API_001",
            "title": "Initial API Title",
            "area": "checkout",
            "steps": "Step 1",
            "status": "draft",
        },
        user_email="system",
    )


def test_viewer_can_read_cases():
    headers = {"X-User-Email": "viewer@vananam.com"}
    response = client.get("/api/tcms/cases", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert any(c["case_id"] == "TC_API_001" for c in data["cases"])


def test_viewer_gets_403_for_patch_case():
    headers = {"X-User-Email": "viewer@vananam.com"}
    response = client.patch(
        "/api/tcms/cases/TC_API_001",
        json={"title": "Hacked Title"},
        headers=headers,
    )
    assert response.status_code == 403
    assert "insufficient" in response.json()["detail"].lower()


def test_viewer_gets_403_for_import():
    headers = {"X-User-Email": "viewer@vananam.com"}
    response = client.post(
        "/api/tcms/import",
        json={"cases": [{"case_id": "TC_NEW_01"}]},
        headers=headers,
    )
    assert response.status_code == 403


def test_editor_gets_403_for_import():
    headers = {"X-User-Email": "editor@vananam.com"}
    response = client.post(
        "/api/tcms/import",
        json={"cases": [{"case_id": "TC_NEW_01"}]},
        headers=headers,
    )
    assert response.status_code == 403


def test_editor_can_edit_and_creates_version_n_plus_one():
    headers = {"X-User-Email": "editor@vananam.com"}

    # Initial version is 1
    initial = tcms_store.get_case("TC_API_001")
    assert initial["version"] == 1

    # Edit via API
    response = client.patch(
        "/api/tcms/cases/TC_API_001",
        json={
            "title": "Edited by Editor",
            "steps": "1. New step A\n2. New step B",
            "status": "active",
            "change_summary": "Added steps via API",
        },
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["version"] == 2
    assert data["title"] == "Edited by Editor"
    assert data["status"] == "active"
    assert data["updated_by"] == "editor@vananam.com"

    # Verify version history via API
    v_resp = client.get("/api/tcms/cases/TC_API_001/versions", headers=headers)
    assert v_resp.status_code == 200
    v_data = v_resp.json()
    assert len(v_data["versions"]) == 2
    assert v_data["versions"][0]["version"] == 2
    assert v_data["versions"][0]["edited_by"] == "editor@vananam.com"
    assert v_data["versions"][1]["version"] == 1


def test_admin_can_import():
    headers = {"X-User-Email": "admin@vananam.com"}
    payload = {
        "cases": [
            {
                "case_id": "TC_IMPORT_01",
                "title": "Imported Case 1",
                "area": "rewards",
                "test_type": "api",
            },
            {
                "case_id": "TC_IMPORT_02",
                "title": "Imported Case 2",
                "area": "loyalty",
                "test_type": "grpc",
            },
        ]
    }
    response = client.post("/api/tcms/import", json=payload, headers=headers)
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["success"] is True
    assert res_data["created"] == 2

    # Verify imported cases can be fetched
    c_resp = client.get("/api/tcms/cases/TC_IMPORT_01", headers=headers)
    assert c_resp.status_code == 200
    assert c_resp.json()["case_id"] == "TC_IMPORT_01"


def test_get_nonexistent_case_returns_404():
    headers = {"X-User-Email": "viewer@vananam.com"}
    response = client.get("/api/tcms/cases/TC_DOES_NOT_EXIST", headers=headers)
    assert response.status_code == 404

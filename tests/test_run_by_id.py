"""Tests for running exact test cases by ID, validation, and environment locking."""
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.services import run_launch, tcms_store

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_run_test_cases(fake_db):
    tcms_store.assign_role("editor@vananam.com", "editor", assigned_by="system")

    # 1. Normal unique rewards case
    tcms_store.create_case({
        "case_id": "TC_VALID_01",
        "platform": "rewards",
        "test_type": "api",
        "id_status": "unique",
        "substring_unsafe": False,
    })

    # 2. Substring unsafe case
    tcms_store.create_case({
        "case_id": "TC_SUB_UNSAFE",
        "platform": "rewards",
        "test_type": "grpc",
        "id_status": "unique",
        "substring_unsafe": True,
    })

    # 3. Ambiguous case
    tcms_store.create_case({
        "case_id": "TC_AMBIGUOUS_ID",
        "platform": "rewards",
        "test_type": "api",
        "id_status": "ambiguous",
    })

    # 4. Loyalty platform case
    tcms_store.create_case({
        "case_id": "TC_LOYALTY_01",
        "platform": "loyalty",
        "test_type": "api",
        "id_status": "unique",
    })


def test_successful_single_case_run_with_fallback_filter():
    headers = {"X-User-Email": "editor@vananam.com"}
    payload = {
        "environment": "pre-prod",
        "case_ids": ["TC_VALID_01"],
    }
    response = client.post("/api/trigger", json=payload, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["runner_env"]["TEST_CASE_IDS"] == "TC_VALID_01"
    # Fallback FILTER is set because it is unique and not substring_unsafe
    assert data["runner_env"]["FILTER"] == "TC_VALID_01"
    assert data["test_type"] == "api"


def test_substring_unsafe_case_omits_filter_fallback():
    headers = {"X-User-Email": "editor@vananam.com"}
    payload = {
        "environment": "staging",
        "case_ids": ["TC_SUB_UNSAFE"],
    }
    response = client.post("/api/trigger", json=payload, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["runner_env"]["TEST_CASE_IDS"] == "TC_SUB_UNSAFE"
    # Substring unsafe must NOT set FILTER to avoid runner substring collisions
    assert data["runner_env"]["FILTER"] == ""
    assert data["test_type"] == "grpc"


def test_rejection_ambiguous_case_id():
    headers = {"X-User-Email": "editor@vananam.com"}
    payload = {
        "environment": "pre-prod",
        "case_ids": ["TC_AMBIGUOUS_ID"],
    }
    response = client.post("/api/trigger", json=payload, headers=headers)
    assert response.status_code == 400
    assert "Ambiguous test case ID" in response.json()["detail"]


def test_rejection_non_rewards_platform():
    headers = {"X-User-Email": "editor@vananam.com"}
    payload = {
        "environment": "pre-prod",
        "case_ids": ["TC_LOYALTY_01"],
    }
    response = client.post("/api/trigger", json=payload, headers=headers)
    assert response.status_code == 400
    assert "rewards" in response.json()["detail"].lower()


def test_rejection_non_existent_case_id():
    headers = {"X-User-Email": "editor@vananam.com"}
    payload = {
        "environment": "pre-prod",
        "case_ids": ["TC_DOES_NOT_EXIST"],
    }
    response = client.post("/api/trigger", json=payload, headers=headers)
    assert response.status_code == 400
    assert "does not exist in TCMS" in response.json()["detail"]


def test_rejection_invalid_id_format():
    headers = {"X-User-Email": "editor@vananam.com"}
    payload = {
        "environment": "pre-prod",
        "case_ids": ["_INVALID_START"],  # Must start with alphanumeric
    }
    response = client.post("/api/trigger", json=payload, headers=headers)
    assert response.status_code == 422


def test_rejection_more_than_20_case_ids():
    headers = {"X-User-Email": "editor@vananam.com"}
    twenty_one_ids = [f"TC_CASE_{i:02d}" for i in range(21)]
    payload = {
        "environment": "pre-prod",
        "case_ids": twenty_one_ids,
    }
    response = client.post("/api/trigger", json=payload, headers=headers)
    assert response.status_code == 422


def test_environment_locking_returns_409():
    headers = {"X-User-Email": "editor@vananam.com"}

    # First run acquires lock
    r1 = client.post(
        "/api/trigger",
        json={"environment": "pre-prod", "case_ids": ["TC_VALID_01"]},
        headers=headers,
    )
    assert r1.status_code == 200

    # Second run on same environment conflicts
    r2 = client.post(
        "/api/trigger",
        json={"environment": "pre-prod", "case_ids": ["TC_VALID_01"]},
        headers=headers,
    )
    assert r2.status_code == 409
    assert "currently busy" in r2.json()["detail"].lower()

    # Release lock, now succeeds
    run_launch.release_environment_lock("pre-prod")
    r3 = client.post(
        "/api/trigger",
        json={"environment": "pre-prod", "case_ids": ["TC_VALID_01"]},
        headers=headers,
    )
    assert r3.status_code == 200

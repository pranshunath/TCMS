"""Tests for execution history joins and Jira compliance CSV/JSON reporting."""
import csv
import io
import pytest
from datetime import datetime
from fastapi.testclient import TestClient
from app.main import app
from app.services import tcms_store

client = TestClient(app)


@pytest.fixture(autouse=True)
def seed_execution_data(fake_db):
    # Create test case
    tcms_store.create_case({
        "case_id": "TC_EXEC_001",
        "title": "Checkout payment test",
        "area": "checkout",
        "status": "active",
    })

    # Link to Jira
    tcms_store.link_jira("TC_EXEC_001", "REW-5000", user_email="qa@vananam.com")

    # Seed TestRuns
    fake_db.test_runs.append({
        "run_id": "run-alpha-1",
        "job_name": "rewards-tests-alpha",
        "environment": "pre-prod",
        "triggered_by": "qa-engineer@vananam.com",
        "image_digest": "sha256:111122223333",
        "started_at": datetime(2026, 10, 1, 10, 0, 0),
    })
    fake_db.test_runs.append({
        "run_id": "run-alpha-2",
        "job_name": "rewards-tests-alpha",
        "environment": "staging",
        "triggered_by": "ci-bot@vananam.com",
        "image_digest": "sha256:444455556666",
        "started_at": datetime(2026, 10, 2, 14, 30, 0),
    })

    # Seed TestCaseResults with test_case_id
    fake_db.test_case_results.append({
        "id": 1,
        "run_id": "run-alpha-1",
        "test_case_id": "TC_EXEC_001",
        "node_id": "tests/test_checkout.py::test_payment",
        "outcome": "Passed",
        "duration_ms": 120,
        "created_at": datetime(2026, 10, 1, 10, 5, 0),
    })
    fake_db.test_case_results.append({
        "id": 2,
        "run_id": "run-alpha-2",
        "test_case_id": "TC_EXEC_001",
        "node_id": "tests/test_checkout.py::test_payment",
        "outcome": "Failed",
        "duration_ms": 250,
        "created_at": datetime(2026, 10, 2, 14, 35, 0),
    })

    # Seed a TestCaseResult with NO test_case_id linked to REW-5000 run
    fake_db.run_jira_tickets.append({
        "run_id": "run-alpha-1",
        "jira_key": "REW-5000",
    })
    fake_db.test_case_results.append({
        "id": 3,
        "run_id": "run-alpha-1",
        "test_case_id": None,
        "node_id": "tests/test_legacy.py::test_without_id",
        "outcome": "Passed",
        "duration_ms": 50,
        "created_at": datetime(2026, 10, 1, 10, 2, 0),
    })


def test_get_case_executions_api():
    headers = {"X-User-Email": "viewer@vananam.com"}
    response = client.get("/api/tcms/cases/TC_EXEC_001/executions", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["case_id"] == "TC_EXEC_001"
    assert len(data["executions"]) == 2
    outcomes = [e["outcome"] for e in data["executions"]]
    assert "Passed" in outcomes
    assert "Failed" in outcomes


def test_get_jira_compliance_report_json():
    headers = {"X-User-Email": "viewer@vananam.com"}
    response = client.get("/api/tcms/jira/REW-5000/report", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["jira_key"] == "REW-5000"
    assert len(data["linked_cases"]) == 1

    case_rep = data["linked_cases"][0]
    assert case_rep["case_id"] == "TC_EXEC_001"
    assert "pre-prod" in case_rep["environment_results"]
    assert case_rep["environment_results"]["pre-prod"]["outcome"] == "Passed"
    assert case_rep["environment_results"]["pre-prod"]["image_digest"] == "sha256:111122223333"

    # Separate unlinked/no-id section
    assert len(data["unlinked_or_no_id_results"]) == 1
    assert data["unlinked_or_no_id_results"][0]["node_id"] == "tests/test_legacy.py::test_without_id"


def test_get_jira_compliance_report_csv():
    headers = {"X-User-Email": "viewer@vananam.com"}
    response = client.get("/api/tcms/jira/REW-5000/report.csv", headers=headers)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment; filename=compliance_REW-5000.csv" in response.headers["content-disposition"]

    # Parse CSV content
    reader = csv.reader(io.StringIO(response.text))
    rows = list(reader)

    # Check header
    header = rows[0]
    assert "case_id" in header
    assert "environment" in header
    assert "latest_outcome" in header
    assert "image_digest" in header

    # Find row with TC_EXEC_001
    case_rows = [r for r in rows if len(r) > 0 and r[0] == "TC_EXEC_001"]
    assert len(case_rows) >= 1
    # Check that image digest and environment are present
    env_list = [r[3] for r in case_rows]
    assert "pre-prod" in env_list

    # Verify no-id section exists in the CSV
    no_id_header = any("--- RUN RESULTS WITH NO TEST CASE ID ---" in cell for r in rows for cell in r)
    assert no_id_header is True

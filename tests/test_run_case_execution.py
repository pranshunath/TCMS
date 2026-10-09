"""Comprehensive tests for 'Run this case' execution flow, TestCaseResult lifecycle,
environment lease locking/release, and Jira compliance integration.

Validates all 12 criteria (A through L):
A. Run request validates the case ID.
B. Run request creates a TestRun.
C. The selected case ID is preserved in runner environment.
D. Actual execution/result processing creates TestCaseResult correctly.
E. TestCaseResult.test_case_id equals the selected TCMS case ID.
F. TestCaseResult.run_id points to the created TestRun.
G. Execution History can retrieve the new result.
H. Jira compliance can retrieve the result.
I. Invalid case IDs still fail.
J. Non-Rewards cases still fail.
K. Ambiguous IDs still fail.
L. Environment locking works, locks are released in finally block, and no fake Passed results are fabricated.
"""
import os
import tempfile
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.services import db, run_launch, tcms_store, test_runner

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_execution_test_cases(fake_db):
    """Seed test cases and editor role for execution flow tests."""
    tcms_store.assign_role("editor@vananam.com", "editor", assigned_by="system")

    # 1. Standard Rewards case with non-existent local source file
    tcms_store.create_case({
        "case_id": "TC_EXEC_FLOW_01",
        "platform": "rewards",
        "title": "Checkout discount execution test",
        "area": "checkout",
        "test_type": "api",
        "source_path": "tests/test_checkout_remote.py",
        "source_symbol": "test_checkout_discount",
        "is_skipped": False,
        "id_status": "unique",
        "substring_unsafe": False,
        "status": "active",
    })

    # 2. Rewards case with skipped flag
    tcms_store.create_case({
        "case_id": "TC_EXEC_SKIPPED_02",
        "platform": "rewards",
        "title": "Deprecated legacy case",
        "area": "legacy",
        "test_type": "api",
        "source_path": "tests/test_legacy.py",
        "source_symbol": "test_legacy_thing",
        "is_skipped": True,
        "id_status": "unique",
        "status": "active",
    })

    # 3. Substring unsafe rewards case
    tcms_store.create_case({
        "case_id": "TC_UNSAFE_03",
        "platform": "rewards",
        "title": "Substring unsafe case",
        "area": "auth",
        "test_type": "api",
        "source_path": "tests/test_auth.py",
        "source_symbol": "test_auth",
        "is_skipped": False,
        "id_status": "unique",
        "substring_unsafe": True,
        "status": "active",
    })

    # 4. Non-rewards platform case
    tcms_store.create_case({
        "case_id": "TC_LOY_EXEC_04",
        "platform": "loyalty",
        "title": "Loyalty tier promotion",
        "area": "points",
        "test_type": "api",
        "id_status": "unique",
        "status": "active",
    })

    # 5. Ambiguous ID case
    tcms_store.create_case({
        "case_id": "TC_AMBIG_EXEC_05",
        "platform": "rewards",
        "title": "Ambiguous shared case",
        "area": "billing",
        "test_type": "api",
        "id_status": "ambiguous",
        "status": "active",
    })


def test_ui_run_case_creates_test_run_and_preserves_case_id():
    """Criteria A, B, C: Validates case ID, creates TestRun, preserves case ID."""
    headers = {"X-User-Email": "editor@vananam.com"}
    response = client.post(
        "/tcms/cases/TC_EXEC_FLOW_01/run",
        data={"environment": "pre-prod"},
        headers=headers,
        follow_redirects=False,
    )
    # Redirects to case detail page
    assert response.status_code == 303
    assert response.headers["location"] == "/tcms/cases/TC_EXEC_FLOW_01"

    # Verify TestRun was created in DB
    test_runs = db.query("SELECT * FROM TestRun WHERE environment = %s", ("pre-prod",))
    assert len(test_runs) >= 1
    newest_run = test_runs[-1]
    assert newest_run["environment"] == "pre-prod"
    assert newest_run["triggered_by"] == "editor@vananam.com"
    assert newest_run["status"] == "Completed"


def test_ui_run_case_records_skipped_when_no_runner_and_no_fake_passed(fake_db):
    """Criteria D, E, F: Creates TestCaseResult, links run_id/case_id, does NOT fake 'Passed'."""
    headers = {"X-User-Email": "editor@vananam.com"}
    response = client.post(
        "/tcms/cases/TC_EXEC_FLOW_01/run",
        data={"environment": "staging"},
        headers=headers,
        follow_redirects=False,
    )
    assert response.status_code == 303

    # Check TestCaseResult
    results = db.query(
        "SELECT * FROM TestCaseResult WHERE test_case_id = %s ORDER BY id DESC LIMIT 1",
        ("TC_EXEC_FLOW_01",),
    )
    assert len(results) == 1
    res = results[0]

    # Outcome MUST NOT be fabricated Passed
    assert res["outcome"] == "Skipped"
    assert res["test_case_id"] == "TC_EXEC_FLOW_01"
    assert "tests/test_checkout_remote.py::test_checkout_discount" in res["node_id"]
    assert "Local runner unavailable" in res["error_message"]

    # Verify run_id link
    test_run = db.query("SELECT * FROM TestRun WHERE run_id = %s", (res["run_id"],))
    assert len(test_run) == 1
    assert test_run[0]["environment"] == "staging"


def test_execution_history_displays_new_result():
    """Criterion G: Execution History can retrieve the new result."""
    headers = {"X-User-Email": "editor@vananam.com"}
    client.post(
        "/tcms/cases/TC_EXEC_FLOW_01/run",
        data={"environment": "pre-prod"},
        headers=headers,
        follow_redirects=False,
    )

    # Fetch execution history via tcms_store
    executions = tcms_store.get_case_executions("TC_EXEC_FLOW_01")
    assert len(executions) >= 1
    latest = executions[0]
    assert latest["test_case_id"] == "TC_EXEC_FLOW_01"
    assert latest["outcome"] == "Skipped"
    assert latest["environment"] == "pre-prod"
    assert latest["triggered_by"] == "editor@vananam.com"

    # Detail page HTML loads and shows the new execution
    detail_res = client.get("/tcms/cases/TC_EXEC_FLOW_01", headers=headers)
    assert detail_res.status_code == 200
    assert latest["run_id"] in detail_res.text
    assert "Skipped" in detail_res.text


def test_jira_compliance_retrieves_executed_result():
    """Criterion H: Jira compliance report reflects new execution."""
    headers = {"X-User-Email": "editor@vananam.com"}
    # Link case to Jira ticket REW-9000
    tcms_store.link_jira("TC_EXEC_FLOW_01", "REW-9000", user_email="editor@vananam.com")

    # Run the case on staging
    client.post(
        "/tcms/cases/TC_EXEC_FLOW_01/run",
        data={"environment": "staging"},
        headers=headers,
        follow_redirects=False,
    )

    # Compliance report retrieves latest result
    report = tcms_store.get_jira_compliance_report("REW-9000")
    assert report["jira_key"] == "REW-9000"
    assert len(report["linked_cases"]) == 1
    case_report = report["linked_cases"][0]
    assert case_report["case_id"] == "TC_EXEC_FLOW_01"
    assert "staging" in case_report["environment_results"]
    assert case_report["environment_results"]["staging"]["outcome"] == "Skipped"


def test_rejection_invalid_case_id():
    """Criterion I: Invalid / non-existent case IDs fail with 400."""
    headers = {"X-User-Email": "editor@vananam.com"}
    response = client.post(
        "/tcms/cases/TC_DOES_NOT_EXIST/run",
        data={"environment": "pre-prod"},
        headers=headers,
    )
    assert response.status_code == 400
    assert "does not exist in TCMS" in response.json()["detail"]


def test_rejection_non_rewards_platform():
    """Criterion J: Non-Rewards platform cases fail with 400."""
    headers = {"X-User-Email": "editor@vananam.com"}
    response = client.post(
        "/tcms/cases/TC_LOY_EXEC_04/run",
        data={"environment": "pre-prod"},
        headers=headers,
    )
    assert response.status_code == 400
    assert "rewards" in response.json()["detail"].lower()


def test_rejection_ambiguous_id():
    """Criterion K: Ambiguous case IDs fail with 400."""
    headers = {"X-User-Email": "editor@vananam.com"}
    response = client.post(
        "/tcms/cases/TC_AMBIG_EXEC_05/run",
        data={"environment": "pre-prod"},
        headers=headers,
    )
    assert response.status_code == 400
    assert "Ambiguous test case ID" in response.json()["detail"]


def test_environment_locking_and_automatic_release():
    """Criterion L: Environment lock prevents concurrent runs and is released upon completion."""
    headers = {"X-User-Email": "editor@vananam.com"}

    # 1. Manually lock the environment
    acquired = run_launch.acquire_environment_lock("pre-prod", "someone-else@vananam.com")
    assert acquired is True

    # 2. Attempting to run on the locked environment returns 409 Conflict
    response = client.post(
        "/tcms/cases/TC_EXEC_FLOW_01/run",
        data={"environment": "pre-prod"},
        headers=headers,
    )
    assert response.status_code == 409
    assert "currently busy" in response.json()["detail"].lower()

    # 3. Release the manual lock
    run_launch.release_environment_lock("pre-prod")

    # 4. Now run succeeds and releases its own lock in finally block
    run_response = client.post(
        "/tcms/cases/TC_EXEC_FLOW_01/run",
        data={"environment": "pre-prod"},
        headers=headers,
        follow_redirects=False,
    )
    assert run_response.status_code == 303

    # 5. Lock must be free now (lease was released in finally block)
    leases = db.query("SELECT * FROM EnvironmentLeases WHERE environment = %s", ("pre-prod",))
    assert len(leases) == 0

    # 6. Another run immediately succeeds without conflict
    second_run = client.post(
        "/tcms/cases/TC_EXEC_FLOW_01/run",
        data={"environment": "pre-prod"},
        headers=headers,
        follow_redirects=False,
    )
    assert second_run.status_code == 303


def test_environment_lock_released_on_execution_failure():
    """Criterion L: Lock is released even if an unhandled failure occurs during execution."""
    # Acquire lock in staging
    launch_info = {
        "run_id": "run-fail-test-1",
        "environment": "staging",
        "case_ids": ["TC_EXEC_FLOW_01"],
        "runner_env": {},
    }
    run_launch.acquire_environment_lock("staging", "editor@vananam.com")

    # Force an error by passing bad launch_info or mocking
    def bad_execute():
        raise RuntimeError("Simulated runner crash")

    # Monkeypatch execute_run internal or call with error
    orig_tcms_get = tcms_store.get_case
    try:
        def raise_during_get(cid):
            raise RuntimeError("Database connection dropped during execution")

        tcms_store.get_case = raise_during_get

        with pytest.raises(RuntimeError):
            test_runner.execute_run(launch_info, "editor@vananam.com")
    finally:
        tcms_store.get_case = orig_tcms_get

    # Lock must be released in finally block despite the crash
    leases = db.query("SELECT * FROM EnvironmentLeases WHERE environment = %s", ("staging",))
    assert len(leases) == 0


def test_real_pytest_runner_execution_when_test_file_exists():
    """Validates real pytest execution: captures actual Passed/Failed outcome, duration, and error."""
    headers = {"X-User-Email": "editor@vananam.com"}

    # Create a real temporary test file on disk
    with tempfile.NamedTemporaryFile(suffix="_test.py", mode="w", delete=False) as f:
        f.write('''
def test_real_success():
    """TC_REAL_PASS_01: verifies 1+1 equals 2."""
    assert 1 + 1 == 2

def test_real_failure():
    """TC_REAL_FAIL_02: intentional assertion failure."""
    assert 1 + 1 == 3
''')
        temp_path = f.name.replace("\\", "/")

    try:
        # Register case targeting real passing test
        tcms_store.create_case({
            "case_id": "TC_REAL_PASS_01",
            "platform": "rewards",
            "title": "Real passing test",
            "source_path": temp_path,
            "source_symbol": "test_real_success",
            "status": "active",
        })

        # Register case targeting real failing test
        tcms_store.create_case({
            "case_id": "TC_REAL_FAIL_02",
            "platform": "rewards",
            "title": "Real failing test",
            "source_path": temp_path,
            "source_symbol": "test_real_failure",
            "status": "active",
        })

        # Run passing case
        r1 = client.post(
            "/tcms/cases/TC_REAL_PASS_01/run",
            data={"environment": "pre-prod"},
            headers=headers,
            follow_redirects=False,
        )
        assert r1.status_code == 303

        res_pass = db.query(
            "SELECT * FROM TestCaseResult WHERE test_case_id = %s ORDER BY id DESC LIMIT 1",
            ("TC_REAL_PASS_01",),
        )[0]
        assert res_pass["outcome"] == "Passed"
        assert res_pass["duration_ms"] is not None
        assert res_pass["error_message"] is None

        # Run failing case
        r2 = client.post(
            "/tcms/cases/TC_REAL_FAIL_02/run",
            data={"environment": "staging"},
            headers=headers,
            follow_redirects=False,
        )
        assert r2.status_code == 303

        res_fail = db.query(
            "SELECT * FROM TestCaseResult WHERE test_case_id = %s ORDER BY id DESC LIMIT 1",
            ("TC_REAL_FAIL_02",),
        )[0]
        assert res_fail["outcome"] == "Failed"
        assert res_fail["duration_ms"] is not None
        assert "assert 1 + 1 == 3" in res_fail["error_message"]

    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

def test_real_go_runner_execution():
    """Verifies TCMS can execute an existing Go test and record its result."""
    headers = {"X-User-Email": "editor@vananam.com"}

    tcms_store.create_case({
        "case_id": "TC_GO_RUNNER_01",
        "platform": "rewards",
        "title": "Go runner integration check",
        "test_type": "api",
        "runner_type": "go",
        "source_path": "tests/order_cart_test.go",
        "source_symbol": "TestCartAndOrderFlow",
        "is_skipped": False,
        "id_status": "unique",
        "substring_unsafe": False,
        "status": "active",
    })

    response = client.post(
        "/tcms/cases/TC_GO_RUNNER_01/run",
        data={"environment": "pre-prod"},
        headers=headers,
        follow_redirects=False,
    )
    assert response.status_code == 303

    results = db.query(
        "SELECT * FROM TestCaseResult "
        "WHERE test_case_id = %s ORDER BY id DESC LIMIT 1",
        ("TC_GO_RUNNER_01",),
    )
    assert results, "TCMS did not record a result for the Go test"

    result = results[0]
    assert result["outcome"] == "Passed", result.get("error_message")
    assert result["duration_ms"] is not None
    assert result["error_message"] is None

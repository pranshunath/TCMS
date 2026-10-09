"""Test execution runner service for TCMS.

Executes test cases using pytest if the test file and symbol exist on disk,
or records an explicit non-success state ('Skipped') when the local test runner
or test source file is not available in the development environment.

Maintains the strict lifecycle:
TestRun (Running) -> Actual Execution -> TestCaseResult -> TestRun (Completed/Failed)
-> TriggerRunHistory (Completed/Failed) -> EnvironmentLeases lock released.
"""
import os
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple
from app.services import db, run_launch, tcms_store


def _run_pytest_case(
    source_path: str,
    source_symbol: str,
    case_id: str,
    runner_env: Dict[str, str],
) -> Tuple[str, int, Optional[str]]:
    """Runs a single test case using pytest subprocess and captures outcome, duration, and error."""
    start_time = time.perf_counter()
    env = os.environ.copy()
    env.update(runner_env)
    env["TEST_CASE_IDS"] = case_id

    target = f"{source_path}::{source_symbol}" if source_symbol else source_path
    cmd = [sys.executable, "-m", "pytest", target, "-p", "scripts.runner_plugin", "-q"]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )
        duration_ms = int((time.perf_counter() - start_time) * 1000)

        if proc.returncode == 0:
            return "Passed", duration_ms, None
        elif proc.returncode == 5:
            # Pytest returncode 5 = no tests collected
            return "Skipped", duration_ms, f"No matching tests collected for {case_id}: {proc.stdout or proc.stderr}".strip()
        else:
            output = (proc.stderr or proc.stdout or "Test execution failed").strip()
            return "Failed", duration_ms, output
    except subprocess.TimeoutExpired:
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        return "Failed", duration_ms, "Test execution timed out after 30 seconds"
    except Exception as exc:
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        return "Failed", duration_ms, str(exc)


def _run_go_case(
    source_path: str,
    source_symbol: str,
    case_id: str,
    runner_env: Dict[str, str],
) -> Tuple[str, int, Optional[str]]:
    """Runs a specific Go test and captures its outcome, duration, and error."""
    start_time = time.perf_counter()

    # TCMS is expected to sit beside ProductManagementSystem.
    tcms_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    module_root = os.path.abspath(
        os.path.join(tcms_root, "..", "ProductManagementSystem")
    )

    env = os.environ.copy()
    env.update(runner_env)
    env["TEST_CASE_IDS"] = case_id

    # Accept only test files inside the sibling Go module's tests directory.
    tests_root = os.path.realpath(os.path.join(module_root, "tests"))
    candidate = os.path.realpath(os.path.join(module_root, source_path))

    if not os.path.isdir(module_root):
        return "Skipped", 0, f"Go module directory not found: {module_root}"

    if os.path.commonpath([tests_root, candidate]) != tests_root:
        return "Skipped", 0, "Go test source must be inside the module's tests directory."

    if not os.path.isfile(candidate) or not candidate.endswith("_test.go"):
        return "Skipped", 0, f"Go test file not found or invalid: {source_path}"

    if not source_symbol.startswith("Test"):
        return "Skipped", 0, f"Invalid Go test function name: {source_symbol}"

    try:
        proc = subprocess.run(
            ["go", "test", "./tests", "-run", f"^{source_symbol}$", "-count=1"],
            cwd=module_root,
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )
        duration_ms = int((time.perf_counter() - start_time) * 1000)

        if proc.returncode == 0:
            return "Passed", duration_ms, None

        output = (proc.stdout or "") + (proc.stderr or "")
        output = output.strip() or "Go test execution failed"

        if "no tests to run" in output.lower():
            return "Skipped", duration_ms, output

        return "Failed", duration_ms, output

    except subprocess.TimeoutExpired:
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        return "Failed", duration_ms, "Go test execution timed out after 30 seconds"
    except FileNotFoundError:
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        return "Skipped", duration_ms, "Go is not installed or the go executable is not on PATH."
    except Exception as exc:
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        return "Failed", duration_ms, str(exc)
def execute_run(
    launch_info: Dict[str, Any],
    user_email: str,
) -> List[Dict[str, Any]]:
    """Executes the test run lifecycle and records real execution results into TestCaseResult.

    Guarantees environment lock release in a finally block.
    """
    run_id = launch_info["run_id"]
    environment = launch_info["environment"]
    case_ids = launch_info.get("case_ids") or []
    runner_env = launch_info.get("runner_env") or {}

    results: List[Dict[str, Any]] = []

    try:
        for cid in case_ids:
            case = tcms_store.get_case(cid)
            if not case:
                continue

            source_path = case.get("source_path") or ""
            source_symbol = case.get("source_symbol") or ""
            node_id = f"{source_path}::{source_symbol}" if source_path and source_symbol else (source_path or cid)

            # Check if case is explicitly marked skipped
            if case.get("is_skipped"):
                outcome = "Skipped"
                duration_ms = 0
                error_msg = f"Test case '{cid}' is marked as skipped in TCMS."

            elif case.get("runner_type", "pytest") == "go":
                outcome, duration_ms, error_msg = _run_go_case(
                    source_path=source_path,
                    source_symbol=source_symbol,
                    case_id=cid,
                    runner_env=runner_env,
                )
            elif source_path and os.path.isfile(source_path):
                # Real Python test execution against an existing test file.
                outcome, duration_ms, error_msg = _run_pytest_case(
                    source_path=source_path,
                    source_symbol=source_symbol,
                    case_id=cid,
                    runner_env=runner_env,
                )
            else:
                # No executable runner / source file available in this environment.
                # Per TCMS rules: NEVER fabricate a Passed result.
                # Record explicit non-success state ("Skipped") with clear indication.
                outcome = "Skipped"
                duration_ms = 0
                if not source_path:
                    error_msg = f"Local runner unavailable: test case '{cid}' has no source_path configured."
                else:
                    error_msg = f"Local runner unavailable: test source file '{source_path}' not found in development environment."

            # Insert TestCaseResult record
            db.execute(
                """
                INSERT INTO TestCaseResult (run_id, test_case_id, node_id, outcome, duration_ms, error_message)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (run_id, cid, node_id, outcome, duration_ms, error_msg),
            )

            results.append({
                "run_id": run_id,
                "test_case_id": cid,
                "node_id": node_id,
                "outcome": outcome,
                "duration_ms": duration_ms,
                "error_message": error_msg,
            })

        # Determine overall run status
        has_failures = any(r["outcome"] == "Failed" for r in results)
        run_status = "Failed" if has_failures else "Completed"

        db.execute(
            "UPDATE TestRun SET status = %s, completed_at = CURRENT_TIMESTAMP WHERE run_id = %s",
            (run_status, run_id),
        )
        db.execute(
            "UPDATE TriggerRunHistory SET status = %s WHERE run_id = %s",
            (run_status, run_id),
        )

        return results

    except Exception:
        # If an unhandled exception occurred, mark runs as Failed if created
        try:
            db.execute(
                "UPDATE TestRun SET status = 'Failed', completed_at = CURRENT_TIMESTAMP WHERE run_id = %s",
                (run_id,),
            )
            db.execute(
                "UPDATE TriggerRunHistory SET status = 'Failed' WHERE run_id = %s",
                (run_id,),
            )
        except Exception:
            pass
        raise

    finally:
        # Environment lock MUST be released after execution completes or fails
        run_launch.release_environment_lock(environment)

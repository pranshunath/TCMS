"""Run launch service with validation for exact test case ID selection and environment locking."""
import os
import uuid
from typing import Any, Dict, List, Optional
from fastapi import HTTPException, status
from app.models import TriggerRequest
from app.services import db, tcms_store

# In-memory / DB environment lease tracker
ACTIVE_LEASES: Dict[str, Dict[str, Any]] = {}


def acquire_environment_lock(environment: str, holder: str) -> bool:
    """Attempts to acquire environment execution lock. Returns False if already locked."""
    # Check DB or lease table
    rows = db.query(
        "SELECT * FROM EnvironmentLeases WHERE environment = %s AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)",
        (environment,),
    )
    if rows:
        return False

    db.execute(
        "INSERT INTO EnvironmentLeases (environment, holder_identity, expires_at) "
        "VALUES (%s, %s, TIMESTAMPADD(MINUTE, 30, CURRENT_TIMESTAMP)) "
        "ON DUPLICATE KEY UPDATE holder_identity = %s, expires_at = TIMESTAMPADD(MINUTE, 30, CURRENT_TIMESTAMP)",
        (environment, holder, holder),
    )
    return True


def release_environment_lock(environment: str) -> None:
    """Releases environment execution lock."""
    db.execute("DELETE FROM EnvironmentLeases WHERE environment = %s", (environment,))


def validate_and_prepare_run(req: TriggerRequest, user_email: str) -> Dict[str, Any]:
    """Validates trigger request against TCMS rules and builds runner environment variables."""
    case_ids = req.case_ids or []
    test_type = "api"
    env_vars: Dict[str, str] = {}

    if case_ids:
        if len(case_ids) > 20:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot trigger more than 20 cases at once (received {len(case_ids)})",
            )

        cases_found = []
        for cid in case_ids:
            case = tcms_store.get_case(cid)
            if not case:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Test case ID '{cid}' does not exist in TCMS database",
                )

            # Platform must be rewards
            if case.get("platform", "").lower() != "rewards":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Test case '{cid}' belongs to '{case.get('platform')}' platform. Only 'rewards' is supported in MVP.",
                )

            # Refuse ambiguous IDs
            if case.get("id_status") == "ambiguous":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Ambiguous test case ID '{cid}' matches multiple test functions. Cannot run in isolation.",
                )

            cases_found.append(case)

        # Inherit test_type from the case record
        test_type = cases_found[0].get("test_type", "api")

        # Set TEST_CASE_IDS for runner
        env_vars["TEST_CASE_IDS"] = ",".join(case_ids)

        # Fallback mechanism for runner:
        # For exactly one unique ID that is NOT substring_unsafe, set FILTER to the ID
        if len(case_ids) == 1:
            single_case = cases_found[0]
            if not single_case.get("substring_unsafe", False):
                env_vars["FILTER"] = case_ids[0]
            else:
                # Substring unsafe: Cannot safely use substring -k FILTER fallback
                # Still pass TEST_CASE_IDS for the exact hook runner
                env_vars["FILTER"] = ""
    else:
        if req.filter_expr:
            env_vars["FILTER"] = req.filter_expr

    return {
        "test_type": test_type,
        "env_vars": env_vars,
        "case_ids": case_ids,
    }


def launch_run(req: TriggerRequest, user_email: str) -> Dict[str, Any]:
    """Orchestrates validation, lock acquisition, and test execution launch."""
    env = req.environment or "pre-prod"

    # 1. Validation
    prep = validate_and_prepare_run(req, user_email)

    # 2. Environment Lock check
    locked = acquire_environment_lock(env, holder=user_email)
    if not locked:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Environment '{env}' is currently busy with an active test run. Please wait for it to complete.",
        )

    # 3. Create run record
    run_id = f"run-{uuid.uuid4().hex[:12]}"
    job_name = req.job_name or f"rewards-{prep['test_type']}-{run_id}"

    db.execute(
        """
        INSERT INTO TriggerRunHistory (run_id, job_name, environment, triggered_by, test_type, status)
        VALUES (%s, %s, %s, %s, %s, 'Triggered')
        """,
        (run_id, job_name, env, user_email, prep["test_type"]),
    )

    db.execute(
        """
        INSERT INTO TestRun (run_id, job_name, environment, triggered_by, status)
        VALUES (%s, %s, %s, %s, 'Running')
        """,
        (run_id, job_name, env, user_email),
    )

    return {
        "success": True,
        "run_id": run_id,
        "job_name": job_name,
        "environment": env,
        "triggered_by": user_email,
        "test_type": prep["test_type"],
        "runner_env": prep["env_vars"],
        "case_ids": prep["case_ids"],
    }

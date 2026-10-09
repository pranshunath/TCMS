"""TCMS Data Store service implementing raw SQL operations for Tm tables."""
from typing import Any, Dict, List, Optional, Tuple
from app.services import db


def get_case(case_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves a single test case by its unique case_id."""
    sql = "SELECT * FROM TmCase WHERE case_id = %s"
    rows = db.query(sql, (case_id,))
    if not rows:
        return None
    case = dict(rows[0])
    # Attach active Jira tickets
    case["jira_links"] = get_case_jira_links(case_id, include_removed=False)
    return case


def list_cases(
    search: Optional[str] = None,
    area: Optional[str] = None,
    status: Optional[str] = None,
    jira_key: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Tuple[List[Dict[str, Any]], int]:
    """Lists test cases matching optional filters with pagination."""
    conditions = []
    params: List[Any] = []

    if jira_key:
        conditions.append(
            "c.case_id IN (SELECT case_id FROM TmCaseJira WHERE jira_key = %s AND removed_at IS NULL)"
        )
        params.append(jira_key)

    if search:
        conditions.append("(c.case_id LIKE %s OR c.title LIKE %s OR c.business_rule LIKE %s)")
        search_param = f"%{search}%"
        params.extend([search_param, search_param, search_param])

    if area:
        conditions.append("c.area = %s")
        params.append(area)

    if status:
        conditions.append("c.status = %s")
        params.append(status)

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    # Count query
    count_sql = f"SELECT COUNT(*) as total FROM TmCase c {where_clause}"
    count_rows = db.query(count_sql, tuple(params))
    total = count_rows[0]["total"] if count_rows else 0

    # Data query
    data_sql = f"""
        SELECT c.* FROM TmCase c
        {where_clause}
        ORDER BY c.case_id ASC
        LIMIT %s OFFSET %s
    """
    data_params = list(params) + [limit, offset]
    rows = db.query(data_sql, tuple(data_params))

    cases = [dict(r) for r in rows]
    for case in cases:
        case["jira_links"] = get_case_jira_links(case["case_id"], include_removed=False)

    return cases, total


def create_case(data: Dict[str, Any], user_email: str = "system") -> Dict[str, Any]:
    """Creates a new test case and creates its initial version 1 snapshot."""
    case_id = data["case_id"]
    platform = data.get("platform", "rewards")
    title = data.get("title", "")
    area = data.get("area", "")
    test_type = data.get("test_type", "api")
    source_path = data.get("source_path", "")
    source_symbol = data.get("source_symbol", "")
    runner_type = data.get("runner_type", "pytest")
    is_skipped = bool(data.get("is_skipped", False))
    id_status = data.get("id_status", "unique")
    substring_unsafe = bool(data.get("substring_unsafe", False))
    steps = data.get("steps")
    business_rule = data.get("business_rule")
    expected_result = data.get("expected_result")
    status = data.get("status", "draft")
    version = 1


    insert_sql = """
        INSERT INTO TmCase (
            case_id, platform, title, area, test_type,
            source_path, source_symbol, runner_type, is_skipped, id_status,
            substring_unsafe, steps, business_rule, expected_result,
            status, version, created_by, updated_by
        ) VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s
        )
    """
    db.execute(
        insert_sql,
        (
            case_id, platform, title, area, test_type,
            source_path, source_symbol, runner_type, is_skipped, id_status,
            substring_unsafe, steps, business_rule, expected_result,
            status, version, user_email, user_email,
        ),
    )


    # Initial snapshot in TmCaseVersion
    version_sql = """
        INSERT INTO TmCaseVersion (
            case_id, version, title, area, test_type,
            source_path, source_symbol, runner_type, is_skipped, steps,
            business_rule, expected_result, status, edited_by, change_summary
        ) VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s
        )
    """
    db.execute(
        version_sql,
        (
            case_id, version, title, area, test_type,
            source_path, source_symbol, runner_type, is_skipped, steps,
            business_rule, expected_result, status, user_email, "Initial creation",
        ),
    )


    try:
        from app.services import tcms_audit
        tcms_audit.record_audit_event(
            event_type="CASE_CREATED",
            entity_type="case",
            entity_id=case_id,
            actor_email=user_email,
            payload={"case_id": case_id, "title": title, "area": area, "version": version, "status": status},
        )
    except Exception:
        pass

    return get_case(case_id)  # type: ignore


def update_case(
    case_id: str,
    updates: Dict[str, Any],
    user_email: str,
    change_summary: Optional[str] = None,
) -> Dict[str, Any]:
    """Updates an existing test case and atomically snapshots the new version (N+1)."""
    current = get_case(case_id)
    if not current:
        raise ValueError(f"Test case {case_id} not found")

    new_version = current["version"] + 1

    title = updates.get("title", current["title"])
    area = updates.get("area", current["area"])
    test_type = updates.get("test_type", current["test_type"])
    source_path = updates.get("source_path", current["source_path"])
    source_symbol = updates.get("source_symbol", current["source_symbol"])
    runner_type = updates.get("runner_type", current.get("runner_type", "pytest"))
    is_skipped = bool(updates.get("is_skipped", current["is_skipped"]))
    steps = updates.get("steps", current["steps"])
    business_rule = updates.get("business_rule", current["business_rule"])
    expected_result = updates.get("expected_result", current["expected_result"])
    status = updates.get("status", current["status"])


    update_sql = """
        UPDATE TmCase SET
            title = %s,
            area = %s,
            test_type = %s,
            source_path = %s,
            source_symbol = %s,
            runner_type = %s,
            is_skipped = %s,
            steps = %s,
            business_rule = %s,
            expected_result = %s,
            status = %s,
            version = %s,
            updated_by = %s,
            updated_at = CURRENT_TIMESTAMP
        WHERE case_id = %s
    """
    db.execute(
        update_sql,
        (
            title, area, test_type, source_path, source_symbol,
            runner_type, is_skipped, steps, business_rule, expected_result,
            status, new_version, user_email, case_id,
        ),
    )



    # Snapshot to TmCaseVersion
    version_sql = """
        INSERT INTO TmCaseVersion (
            case_id, version, title, area, test_type,
            source_path, source_symbol, runner_type, is_skipped, steps,
            business_rule, expected_result, status, edited_by, change_summary
        ) VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s
        )
    """
    db.execute(
        version_sql,
        (
            case_id, new_version, title, area, test_type,
            source_path, source_symbol, runner_type, is_skipped, steps,
            business_rule, expected_result, status, user_email,
            change_summary or f"Updated to version {new_version}",
        ),
    )


    try:
        from app.services import tcms_audit
        tcms_audit.record_audit_event(
            event_type="CASE_UPDATED",
            entity_type="case",
            entity_id=case_id,
            actor_email=user_email,
            payload={"case_id": case_id, "version": new_version, "change_summary": change_summary or f"Updated to version {new_version}"},
        )
    except Exception:
        pass

    return get_case(case_id)  # type: ignore


def get_case_versions(case_id: str) -> List[Dict[str, Any]]:
    """Returns append-only version history snapshots for a test case."""
    sql = "SELECT * FROM TmCaseVersion WHERE case_id = %s ORDER BY version DESC"
    rows = db.query(sql, (case_id,))
    return [dict(r) for r in rows]


def link_jira(
    case_id: str,
    jira_key: str,
    user_email: str = "system",
    link_kind: str = "covers",
) -> Dict[str, Any]:
    """Idempotently links a test case to a Jira key."""
    # Check if case exists
    case = db.query("SELECT id FROM TmCase WHERE case_id = %s", (case_id,))
    if not case:
        raise ValueError(f"Cannot link: test case '{case_id}' does not exist")

    rows = db.query(
        "SELECT * FROM TmCaseJira WHERE case_id = %s AND jira_key = %s",
        (case_id, jira_key),
    )
    if rows:
        existing = rows[0]
        if existing["removed_at"] is not None:
            # Restore soft-deleted link
            db.execute(
                """UPDATE TmCaseJira
                   SET removed_at = NULL, linked_by = %s, linked_at = CURRENT_TIMESTAMP, link_kind = %s
                   WHERE id = %s""",
                (user_email, link_kind, existing["id"]),
            )
        return dict(existing)

    insert_sql = """
        INSERT INTO TmCaseJira (case_id, jira_key, link_kind, linked_by)
        VALUES (%s, %s, %s, %s)
    """
    db.execute(insert_sql, (case_id, jira_key, link_kind, user_email))
    link_rows = db.query(
        "SELECT * FROM TmCaseJira WHERE case_id = %s AND jira_key = %s",
        (case_id, jira_key),
    )
    try:
        from app.services import tcms_audit
        tcms_audit.record_audit_event(
            event_type="JIRA_LINKED",
            entity_type="jira_link",
            entity_id=jira_key,
            actor_email=user_email,
            payload={"case_id": case_id, "jira_key": jira_key, "link_kind": link_kind},
        )
    except Exception:
        pass
    return dict(link_rows[0])


def unlink_jira(case_id: str, jira_key: str, user_email: str = "system") -> bool:
    """Soft deletes a Jira ticket link by setting removed_at timestamp."""
    sql = """
        UPDATE TmCaseJira
        SET removed_at = CURRENT_TIMESTAMP
        WHERE case_id = %s AND jira_key = %s AND removed_at IS NULL
    """
    affected = db.execute(sql, (case_id, jira_key))
    if affected > 0:
        try:
            from app.services import tcms_audit
            tcms_audit.record_audit_event(
                event_type="JIRA_UNLINKED",
                entity_type="jira_link",
                entity_id=jira_key,
                actor_email=user_email,
                payload={"case_id": case_id, "jira_key": jira_key},
            )
        except Exception:
            pass
    return affected > 0


def get_case_jira_links(case_id: str, include_removed: bool = False) -> List[Dict[str, Any]]:
    """Returns Jira links for a given case."""
    if include_removed:
        sql = "SELECT * FROM TmCaseJira WHERE case_id = %s ORDER BY linked_at DESC"
        params = (case_id,)
    else:
        sql = "SELECT * FROM TmCaseJira WHERE case_id = %s AND removed_at IS NULL ORDER BY linked_at DESC"
        params = (case_id,)
    rows = db.query(sql, params)
    return [dict(r) for r in rows]


def list_cases_by_jira(jira_key: str) -> List[Dict[str, Any]]:
    """Returns all active cases linked to a given Jira ticket."""
    sql = """
        SELECT c.*, j.link_kind, j.linked_at, j.linked_by
        FROM TmCase c
        INNER JOIN TmCaseJira j ON c.case_id = j.case_id
        WHERE j.jira_key = %s AND j.removed_at IS NULL
        ORDER BY c.case_id ASC
    """
    rows = db.query(sql, (jira_key,))
    return [dict(r) for r in rows]


def bulk_link_jira(case_ids: List[str], jira_key: str, user_email: str) -> Dict[str, Any]:
    """Links multiple test case IDs to a Jira ticket."""
    linked = []
    errors = []
    for cid in case_ids:
        cid = cid.strip()
        if not cid:
            continue
        try:
            link_jira(cid, jira_key, user_email)
            linked.append(cid)
        except Exception as e:
            errors.append({"case_id": cid, "error": str(e)})
    return {"linked": linked, "errors": errors, "total_linked": len(linked)}


def get_user_role(email: str, tcms_admins: Optional[List[str]] = None) -> str:
    """Resolves user role: admin, editor, or viewer."""
    clean_email = email.strip().lower() if email else ""
    if not clean_email:
        return "viewer"

    # Check bootstrap settings admins
    if tcms_admins:
        clean_admins = [a.strip().lower() for a in tcms_admins]
        if clean_email in clean_admins:
            return "admin"

    # Check database role assignment
    rows = db.query("SELECT role FROM TmRoleAssignment WHERE email = %s", (clean_email,))
    if rows:
        role = rows[0]["role"].lower()
        if role in ("admin", "editor"):
            return role

    return "viewer"


def assign_role(email: str, role: str, assigned_by: str = "system") -> Dict[str, Any]:
    """Assigns or updates role for an email (editor or admin)."""
    clean_email = email.strip().lower()
    if role not in ("editor", "admin"):
        raise ValueError(f"Invalid role '{role}'. Allowed roles: editor, admin")

    sql = """
        INSERT INTO TmRoleAssignment (email, role, assigned_by)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE role = %s, assigned_by = %s, assigned_at = CURRENT_TIMESTAMP
    """
    db.execute(sql, (clean_email, role, assigned_by, role, assigned_by))
    rows = db.query("SELECT * FROM TmRoleAssignment WHERE email = %s", (clean_email,))
    try:
        from app.services import tcms_audit
        tcms_audit.record_audit_event(
            event_type="ROLE_ASSIGNED",
            entity_type="role",
            entity_id=clean_email,
            actor_email=assigned_by,
            payload={"email": clean_email, "role": role},
        )
    except Exception:
        pass
    return dict(rows[0])


def list_role_assignments() -> List[Dict[str, Any]]:
    """Returns all role assignments."""
    rows = db.query("SELECT * FROM TmRoleAssignment ORDER BY email ASC")
    return [dict(r) for r in rows]


def import_scanned_cases(cases_list: List[Dict[str, Any]], user_email: str) -> Dict[str, Any]:
    """Imports or updates scanned test cases, preserving human-curated steps and rules."""
    created = 0
    updated = 0

    for item in cases_list:
        case_id = item["case_id"]
        existing = db.query("SELECT * FROM TmCase WHERE case_id = %s", (case_id,))
        if existing:
            # Update source/code attributes, keep steps, rule, result, status

            update_sql = """
                UPDATE TmCase SET
                    platform = %s,
                    title = %s,
                    area = %s,
                    test_type = %s,
                    source_path = %s,
                    source_symbol = %s,
                    runner_type = %s,
                    is_skipped = %s,
                    id_status = %s,
                    substring_unsafe = %s,
                    updated_by = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE case_id = %s
            """
            db.execute(
                update_sql,
                (
                    item.get("platform", "rewards"),
                    item.get("title", existing[0]["title"]),
                    item.get("area", existing[0]["area"]),
                    item.get("test_type", existing[0]["test_type"]),
                    item.get("source_path", existing[0]["source_path"]),
                    item.get("source_symbol", existing[0]["source_symbol"]),
                    item.get("runner_type", existing[0].get("runner_type", "pytest")),
                    bool(item.get("is_skipped", False)),
                    item.get("id_status", "unique"),
                    bool(item.get("substring_unsafe", False)),
                    user_email,
                    case_id,
                ),
            )

            updated += 1
        else:
            # Create fresh draft case
            create_case(item, user_email=user_email)
            created += 1

    try:
        from app.services import tcms_audit
        tcms_audit.record_audit_event(
            event_type="CASES_IMPORTED",
            entity_type="import",
            entity_id=f"batch-{created + updated}",
            actor_email=user_email,
            payload={"total": len(cases_list), "created": created, "updated": updated},
        )
    except Exception:
        pass

    return {"created": created, "updated": updated, "total": len(cases_list)}


def get_case_executions(case_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Retrieves execution history for a test case using read-only joins."""
    sql = """
        SELECT
            tcr.id,
            tcr.run_id,
            tcr.test_case_id,
            tcr.node_id,
            tcr.outcome,
            tcr.duration_ms,
            tcr.error_message,
            tcr.created_at,
            tr.job_name,
            tr.environment,
            tr.started_at,
            tr.triggered_by,
            tr.image_digest
        FROM TestCaseResult tcr
        LEFT JOIN TestRun tr ON tcr.run_id = tr.run_id
        WHERE tcr.test_case_id = %s
        ORDER BY tcr.created_at DESC
        LIMIT %s
    """
    rows = db.query(sql, (case_id, limit))
    return [dict(r) for r in rows]


def get_jira_compliance_report(jira_key: str) -> Dict[str, Any]:
    """Generates compliance evidence for a Jira ticket with latest result per environment."""
    # 1. Get all active cases linked to this ticket
    linked_cases = list_cases_by_jira(jira_key)

    case_reports = []
    for case in linked_cases:
        cid = case["case_id"]
        # Query results for this case
        exec_rows = get_case_executions(cid, limit=100)

        # Find latest result per environment
        env_latest: Dict[str, Dict[str, Any]] = {}
        for row in exec_rows:
            env = row.get("environment") or "unknown"
            if env not in env_latest:
                env_latest[env] = {
                    "outcome": row["outcome"],
                    "run_id": row["run_id"],
                    "started_at": str(row.get("started_at") or row.get("created_at") or ""),
                    "triggered_by": row.get("triggered_by") or "system",
                    "image_digest": row.get("image_digest") or "unknown",
                }

        case_reports.append({
            "case_id": cid,
            "title": case.get("title", ""),
            "status": case.get("status", "draft"),
            "environment_results": env_latest,
        })

    # 2. Query runs associated with this ticket that had results with no test_case_id
    unlinked_sql = """
        SELECT
            tcr.id,
            tcr.run_id,
            tcr.node_id,
            tcr.outcome,
            tcr.created_at,
            tr.environment,
            tr.triggered_by,
            tr.image_digest
        FROM TestCaseResult tcr
        INNER JOIN RunJiraTickets rjt ON tcr.run_id = rjt.run_id
        LEFT JOIN TestRun tr ON tcr.run_id = tr.run_id
        WHERE rjt.jira_key = %s AND (tcr.test_case_id IS NULL OR tcr.test_case_id = '')
        ORDER BY tcr.created_at DESC
        LIMIT 100
    """
    unlinked_rows = db.query(unlinked_sql, (jira_key,))

    return {
        "jira_key": jira_key,
        "linked_cases": case_reports,
        "unlinked_or_no_id_results": [dict(r) for r in unlinked_rows],
    }


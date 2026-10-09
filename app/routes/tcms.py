"""API endpoints for Test Case Management System (TCMS)."""
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from app.dependencies import UserContext, require_role, get_current_user
from app.models import (
    CaseUpdatePayload,
    ImportPayload,
    JiraLinkPayload,
    BulkJiraLinkPayload,
    RoleAssignmentPayload,
)
from app.services import tcms_store

router = APIRouter(prefix="/api/tcms", tags=["TCMS"])


@router.get("/me")
def get_my_profile(user: UserContext = Depends(get_current_user)):
    """Returns the authenticated user's email and role."""
    return {"email": user.email, "role": user.role}


@router.get("/cases")
def list_test_cases(
    search: Optional[str] = Query(None, description="Search case_id, title, or rule"),
    area: Optional[str] = Query(None, description="Filter by area"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status"),
    jira_key: Optional[str] = Query(None, description="Filter by linked Jira ticket"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user: UserContext = Depends(require_role("viewer")),
):
    """Lists test cases with optional filtering (Viewer role)."""
    cases, total = tcms_store.list_cases(
        search=search,
        area=area,
        status=status_filter,
        jira_key=jira_key,
        limit=limit,
        offset=offset,
    )
    return {
        "cases": cases,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/cases/{case_id}")
def get_test_case(
    case_id: str,
    user: UserContext = Depends(require_role("viewer")),
):
    """Retrieves a single test case by case_id (Viewer role)."""
    case = tcms_store.get_case(case_id)
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Test case '{case_id}' not found",
        )
    return case


@router.get("/cases/{case_id}/versions")
def get_case_version_history(
    case_id: str,
    user: UserContext = Depends(require_role("viewer")),
):
    """Returns append-only version snapshots for a test case (Viewer role)."""
    case = tcms_store.get_case(case_id)
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Test case '{case_id}' not found",
        )
    versions = tcms_store.get_case_versions(case_id)
    return {"case_id": case_id, "versions": versions}


@router.patch("/cases/{case_id}")
def update_test_case(
    case_id: str,
    payload: CaseUpdatePayload,
    user: UserContext = Depends(require_role("editor")),
):
    """Updates a test case and produces version snapshot N+1 (Editor/Admin role)."""
    existing = tcms_store.get_case(case_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Test case '{case_id}' not found",
        )

    updates = payload.model_dump(exclude_unset=True)
    change_summary = updates.pop("change_summary", None)

    updated = tcms_store.update_case(
        case_id=case_id,
        updates=updates,
        user_email=user.email,
        change_summary=change_summary,
    )
    return updated


@router.post("/import")
def import_scanned_test_cases(
    payload: ImportPayload,
    user: UserContext = Depends(require_role("admin")),
):
    """Imports scanned test cases from AST scanner (Admin role only)."""
    if not payload.cases:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payload must contain a non-empty list of test cases in 'cases'",
        )

    result = tcms_store.import_scanned_cases(payload.cases, user_email=user.email)
    return {
        "success": True,
        "message": f"Successfully processed {result['total']} test cases",
        "created": result["created"],
        "updated": result["updated"],
        "total": result["total"],
    }


# Jira Linking endpoints
@router.post("/cases/{case_id}/jira")
def link_case_to_jira(
    case_id: str,
    payload: JiraLinkPayload,
    user: UserContext = Depends(require_role("editor")),
):
    """Idempotently links a case to a Jira ticket (Editor role)."""
    try:
        link = tcms_store.link_jira(
            case_id=case_id,
            jira_key=payload.jira_key,
            user_email=user.email,
            link_kind=payload.link_kind,
        )
        return {"success": True, "link": link}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/cases/{case_id}/jira/{jira_key}")
def unlink_case_from_jira(
    case_id: str,
    jira_key: str,
    user: UserContext = Depends(require_role("editor")),
):
    """Soft deletes a Jira ticket link via removed_at timestamp (Editor role)."""
    unlinked = tcms_store.unlink_jira(case_id, jira_key, user_email=user.email)
    if not unlinked:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Active link between case '{case_id}' and Jira '{jira_key}' not found",
        )
    return {"success": True, "message": f"Unlinked {case_id} from {jira_key}"}


@router.post("/jira/bulk")
def bulk_link_jira_tickets(
    payload: BulkJiraLinkPayload,
    user: UserContext = Depends(require_role("editor")),
):
    """Bulk links multiple case IDs to a Jira ticket (Editor role)."""
    res = tcms_store.bulk_link_jira(
        case_ids=payload.case_ids,
        jira_key=payload.jira_key,
        user_email=user.email,
    )
    return res


@router.get("/jira/{jira_key}/cases")
def list_cases_for_jira_ticket(
    jira_key: str,
    user: UserContext = Depends(require_role("viewer")),
):
    """Lists all active test cases linked to a Jira ticket (Viewer role)."""
    cases = tcms_store.list_cases_by_jira(jira_key)
    return {"jira_key": jira_key, "cases": cases, "total": len(cases)}


# Role administration endpoints
@router.get("/roles")
def list_roles(user: UserContext = Depends(require_role("viewer"))):
    """Lists role assignments."""
    return {"assignments": tcms_store.list_role_assignments()}


@router.post("/roles")
def assign_user_role(
    payload: RoleAssignmentPayload,
    user: UserContext = Depends(require_role("admin")),
):
    """Assigns or updates a user role (Admin role only)."""
    assigned = tcms_store.assign_role(
        email=payload.email,
        role=payload.role,
        assigned_by=user.email,
    )
    return {"success": True, "assignment": assigned}


@router.get("/cases/{case_id}/executions")
def get_case_executions_api(
    case_id: str,
    limit: int = Query(50, ge=1, le=200),
    user: UserContext = Depends(require_role("viewer")),
):
    """Returns execution history for a test case (Viewer role)."""
    case = tcms_store.get_case(case_id)
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Test case '{case_id}' not found",
        )
    executions = tcms_store.get_case_executions(case_id, limit=limit)
    return {"case_id": case_id, "executions": executions}


@router.get("/jira/{jira_key}/report")
def get_jira_compliance_report_json(
    jira_key: str,
    user: UserContext = Depends(require_role("viewer")),
):
    """Returns compliance evidence report for a Jira ticket as JSON (Viewer role)."""
    report = tcms_store.get_jira_compliance_report(jira_key)
    return report


@router.get("/jira/{jira_key}/report.csv")
def get_jira_compliance_report_csv(
    jira_key: str,
    user: UserContext = Depends(require_role("viewer")),
):
    """Returns compliance evidence report for a Jira ticket as CSV (Viewer role)."""
    import io
    import csv
    from fastapi.responses import Response

    report = tcms_store.get_jira_compliance_report(jira_key)

    output = io.StringIO()
    writer = csv.writer(output)

    # 1. Linked Cases Section
    writer.writerow([
        "case_id",
        "title",
        "case_status",
        "environment",
        "latest_outcome",
        "run_id",
        "started_at",
        "triggered_by",
        "image_digest",
    ])

    for case in report["linked_cases"]:
        cid = case["case_id"]
        title = case["title"]
        c_status = case["status"]
        env_results = case["environment_results"]

        if not env_results:
            writer.writerow([cid, title, c_status, "none", "No Runs", "", "", "", ""])
        else:
            for env, res in env_results.items():
                writer.writerow([
                    cid,
                    title,
                    c_status,
                    env,
                    res["outcome"],
                    res["run_id"],
                    res["started_at"],
                    res["triggered_by"],
                    res["image_digest"],
                ])

    # 2. Separate section for unlinked / no ID results
    writer.writerow([])
    writer.writerow(["--- RUN RESULTS WITH NO TEST CASE ID ---"])
    writer.writerow([
        "result_id",
        "node_id",
        "outcome",
        "run_id",
        "environment",
        "triggered_by",
        "image_digest",
        "created_at",
    ])
    for un in report["unlinked_or_no_id_results"]:
        writer.writerow([
            un.get("id"),
            un.get("node_id"),
            un.get("outcome"),
            un.get("run_id"),
            un.get("environment"),
            un.get("triggered_by"),
            un.get("image_digest"),
            un.get("created_at"),
        ])

    csv_data = output.getvalue()
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=compliance_{jira_key}.csv"},
    )


@router.get("/export.json")
def export_cases_for_ai(
    user: UserContext = Depends(require_role("viewer")),
):
    """Read-only JSON export of active test cases formatted for AI agents."""
    import datetime

    # Query active cases
    cases, _ = tcms_store.list_cases(status="active", limit=10000, offset=0)

    exported_cases = []
    for c in cases:
        exported_cases.append({
            "case_id": c["case_id"],
            "title": c.get("title", ""),
            "area": c.get("area", ""),
            "test_type": c.get("test_type", "api"),
            "runner_type": c.get("runner_type", "pytest"),
            "platform": c.get("platform", "rewards"),
            "steps": c.get("steps") or "",
            "business_rule": c.get("business_rule") or "",
            "expected_result": c.get("expected_result") or "",
            "jira_links": [j["jira_key"] for j in c.get("jira_links", [])],
            "id_status": c.get("id_status", "unique"),
            "version": c.get("version", 1),
            "updated_at": str(c.get("updated_at") or ""),
        })

    return {
        "metadata": {
            "schema_version": "1.0.0",
            "exported_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "total_cases": len(exported_cases),
            "description": "Read-only TCMS test case and business rule export for AI agents",
        },
        "cases": exported_cases,
    }


@router.get("/audit/verify")
def verify_audit_chain_endpoint(
    limit: Optional[int] = Query(None, ge=1),
    user: UserContext = Depends(require_role("viewer")),
):
    """Verifies the integrity of the tamper-evident audit event hash chain."""
    from app.services import tcms_audit
    verification = tcms_audit.verify_audit_chain(limit=limit)
    return verification


@router.get("/jira/{jira_key}/audit-pack")
def get_jira_audit_pack_endpoint(
    jira_key: str,
    user: UserContext = Depends(require_role("viewer")),
):
    """Generates a tamper-evident audit pack for a Jira ticket with proof of integrity."""
    from app.services import tcms_audit
    clean_key = jira_key.strip().upper()
    pack = tcms_audit.generate_jira_audit_pack(clean_key)
    return pack


@router.get("/cases/{case_id}/audit-trail")
def get_case_audit_trail_endpoint(
    case_id: str,
    limit: int = Query(50, ge=1, le=200),
    user: UserContext = Depends(require_role("viewer")),
):
    """Returns the immutable audit event trail for a specific test case."""
    from app.services import tcms_audit
    events = tcms_audit.get_audit_events_for_entity("case", case_id, limit=limit)
    return {"case_id": case_id, "audit_events": events}


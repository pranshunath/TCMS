"""HTML server-rendered UI routes for TCMS under /tcms."""
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from app.dependencies import UserContext, get_current_user, require_role
from app.services import tcms_store

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

ui_router = APIRouter(prefix="/tcms", tags=["TCMS UI"])


@ui_router.get("", response_class=HTMLResponse)
def ui_list_cases(
    request: Request,
    search: Optional[str] = None,
    area: Optional[str] = None,
    status_filter: Optional[str] = None,
    jira_key: Optional[str] = None,
    user: UserContext = Depends(require_role("viewer")),
):
    """HTML list view with filtering."""
    cases, total = tcms_store.list_cases(
        search=search,
        area=area,
        status=status_filter,
        jira_key=jira_key,
        limit=100,
        offset=0,
    )
        # Dashboard summary statistics
    _, total_cases = tcms_store.list_cases(
        limit=1,
        offset=0,
    )

    _, active_cases = tcms_store.list_cases(
        status="active",
        limit=1,
        offset=0,
    )

    _, draft_cases = tcms_store.list_cases(
        status="draft",
        limit=1,
        offset=0,
    )

    _, deprecated_cases = tcms_store.list_cases(
        status="deprecated",
        limit=1,
        offset=0,
    )
       
    return templates.TemplateResponse(
        request=request,
        name="tcms/list.html",
                context={
            "cases": cases,
            "total": total,
            "search": search,
            "area": area,
            "status": status_filter,
            "jira_key": jira_key,
            "current_user": user,

            # Dashboard statistics
            "total_cases": total_cases,
            "active_cases": active_cases,
            "draft_cases": draft_cases,
            "deprecated_cases": deprecated_cases,
        },
    )


@ui_router.get("/cases/{case_id}", response_class=HTMLResponse)
def ui_case_detail(
    request: Request,
    case_id: str,
    user: UserContext = Depends(require_role("viewer")),
):
    """HTML case detail view with metadata, Jira links, and version history."""
    case = tcms_store.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")

    versions = tcms_store.get_case_versions(case_id)
    executions = tcms_store.get_case_executions(case_id)

    return templates.TemplateResponse(
        request=request,
        name="tcms/detail.html",
        context={
            "case": case,
            "versions": versions,
            "executions": executions,
            "current_user": user,
        },
    )


@ui_router.get("/cases/{case_id}/edit", response_class=HTMLResponse)
def ui_edit_case_form(
    request: Request,
    case_id: str,
    user: UserContext = Depends(require_role("editor")),
):
    """HTML edit form for test case (Editor/Admin role only)."""
    case = tcms_store.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")

    return templates.TemplateResponse(
        request=request,
        name="tcms/edit.html",
        context={
            "case": case,
            "current_user": user,
        },
    )


@ui_router.post("/cases/{case_id}/edit")
def ui_submit_case_edit(
    case_id: str,
    title: str = Form(...),
    area: str = Form(""),
    test_type: str = Form("api"),
    status: str = Form("draft"),
    steps: Optional[str] = Form(None),
    business_rule: Optional[str] = Form(None),
    expected_result: Optional[str] = Form(None),
    change_summary: Optional[str] = Form(None),
    user: UserContext = Depends(require_role("editor")),
):
    """Handles HTML form submission to update case and create version N+1."""
    updates = {
        "title": title,
        "area": area,
        "test_type": test_type,
        "status": status,
        "steps": steps,
        "business_rule": business_rule,
        "expected_result": expected_result,
    }
    tcms_store.update_case(
        case_id=case_id,
        updates=updates,
        user_email=user.email,
        change_summary=change_summary,
    )
    return RedirectResponse(url=f"/tcms/cases/{case_id}", status_code=303)


@ui_router.post("/cases/{case_id}/jira")
def ui_link_jira_form(
    case_id: str,
    jira_key: str = Form(...),
    user: UserContext = Depends(require_role("editor")),
):
    """Handles HTML form to link Jira ticket."""
    clean_key = jira_key.strip().upper()
    try:
        tcms_store.link_jira(case_id, clean_key, user_email=user.email)
    except Exception:
        pass
    return RedirectResponse(url=f"/tcms/cases/{case_id}", status_code=303)


@ui_router.post("/cases/{case_id}/jira/{jira_key}/delete")
def ui_unlink_jira_form(
    case_id: str,
    jira_key: str,
    user: UserContext = Depends(require_role("editor")),
):
    """Handles HTML form to unlink Jira ticket."""
    tcms_store.unlink_jira(case_id, jira_key, user_email=user.email)
    return RedirectResponse(url=f"/tcms/cases/{case_id}", status_code=303)

@ui_router.post("/cases/{case_id}/run")
def ui_run_case_form(
    case_id: str,
    environment: str = Form("pre-prod"),
    user: UserContext = Depends(require_role("editor")),
):
    """Handles HTML form for 'Run this case'."""
    from app.models import TriggerRequest
    from app.services import run_launch, test_runner

    req = TriggerRequest(
        environment=environment,
        case_ids=[case_id],
    )

    launch_info = run_launch.launch_run(
        req,
        user_email=user.email,
    )

    test_runner.execute_run(
        launch_info=launch_info,
        user_email=user.email,
    )

    return RedirectResponse(
        url=f"/tcms/cases/{case_id}",
        status_code=303,
    )
@ui_router.get("/jira/{jira_key}", response_class=HTMLResponse)
def ui_jira_compliance_report(
    request: Request,
    jira_key: str,
    user: UserContext = Depends(require_role("viewer")),
):
    """HTML Jira compliance report page with CSV and Audit Pack download links."""
    clean_key = jira_key.strip().upper()
    report = tcms_store.get_jira_compliance_report(clean_key)
    return templates.TemplateResponse(
        request=request,
        name="tcms/report.html",
        context={
            "jira_key": clean_key,
            "report": report,
            "current_user": user,
        },
    )
@ui_router.get("/ai-export", response_class=HTMLResponse)
def ui_ai_export(
    request: Request,
    user: UserContext = Depends(require_role("viewer")),
):
    """HTML page for AI-ready TCMS export."""
    cases, total = tcms_store.list_cases(
        limit=100,
        offset=0,
    )

    return templates.TemplateResponse(
        request=request,
        name="tcms/ai_export.html",
        context={
            "cases": cases,
            "total": total,
            "current_user": user,
        },
    )
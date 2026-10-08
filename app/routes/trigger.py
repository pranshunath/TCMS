"""API route for triggering test suite execution."""
from fastapi import APIRouter, Depends
from app.dependencies import UserContext, require_role
from app.models import TriggerRequest
from app.services import run_launch

router = APIRouter(prefix="/api/trigger", tags=["Trigger"])


@router.post("")
def trigger_test_run(
    payload: TriggerRequest,
    user: UserContext = Depends(require_role("editor")),
):
    """Launches test run on specified environment (Editor role required)."""
    result = run_launch.launch_run(payload, user_email=user.email)
    return result

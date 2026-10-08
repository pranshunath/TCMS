"""Authentication and Role-Based Access Control dependencies."""
from typing import Callable, Optional
from fastapi import Header, HTTPException, Request, Depends
from pydantic import BaseModel
from app.config import get_settings
from app.services import tcms_store

ROLE_HIERARCHY = {
    "viewer": 1,
    "editor": 2,
    "admin": 3,
}


class UserContext(BaseModel):
    email: str
    role: str

    def can_edit(self) -> bool:
        return ROLE_HIERARCHY.get(self.role, 1) >= ROLE_HIERARCHY["editor"]

    def is_admin(self) -> bool:
        return ROLE_HIERARCHY.get(self.role, 1) >= ROLE_HIERARCHY["admin"]


def get_current_user(
    request: Request,
    x_user_email: Optional[str] = Header(None, alias="X-User-Email"),
    x_forwarded_email: Optional[str] = Header(None, alias="X-Forwarded-Email"),
) -> UserContext:
    """Extracts authenticated user from headers/session and resolves their TCMS role."""
    settings = get_settings()

    # Determine email from headers, query, or dev fallback
    email = x_user_email or x_forwarded_email
    if not email and "session" in request.scope and "user" in request.session:
        email = request.session["user"].get("email")

    if not email and settings.TRIGGER_DEV_AUTH:
        # Check query param for dev convenience or default dev user
        email = request.query_params.get("dev_user", "dev-viewer@vananam.com")

    if not email:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Provide X-User-Email header or login.",
        )

    clean_email = email.strip().lower()
    role = tcms_store.get_user_role(clean_email, settings.get_tcms_admins())
    return UserContext(email=clean_email, role=role)


def require_role(min_role: str) -> Callable[[UserContext], UserContext]:
    """Dependency factory checking that user role meets or exceeds min_role."""
    min_level = ROLE_HIERARCHY.get(min_role.lower(), 1)

    def dependency(user: UserContext = Depends(get_current_user)) -> UserContext:
        user_level = ROLE_HIERARCHY.get(user.role.lower(), 1)
        if user_level < min_level:
            raise HTTPException(
                status_code=403,
                detail=f"Forbidden: role '{user.role}' is insufficient for required '{min_role}' action.",
            )
        return user

    return dependency

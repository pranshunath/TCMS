"""Data models and schemas for trigger-service and TCMS."""
import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class CaseUpdatePayload(BaseModel):
    title: Optional[str] = None
    area: Optional[str] = None
    test_type: Optional[str] = None
    source_path: Optional[str] = None
    source_symbol: Optional[str] = None

    runner_type: Optional[str] = None

    is_skipped: Optional[bool] = None
    steps: Optional[str] = None
    business_rule: Optional[str] = None
    expected_result: Optional[str] = None
    status: Optional[str] = None
    change_summary: Optional[str] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ("draft", "active", "deprecated"):
            raise ValueError("status must be 'draft', 'active', or 'deprecated'")
        return v


    @field_validator("test_type")
    @classmethod
    def validate_test_type(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ("api", "grpc", "ui"):
            raise ValueError("test_type must be 'api', 'grpc', or 'ui'")
        return v

    @field_validator("runner_type")
    @classmethod
    def validate_runner_type(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ("pytest", "go"):
            raise ValueError("runner_type must be 'pytest' or 'go'")
        return v


class CaseCreatePayload(BaseModel):
    case_id: str
    platform: str = "rewards"
    title: str = ""
    area: str = ""
    test_type: str = "api"
    source_path: str = ""
    source_symbol: str = ""
    runner_type: str = "pytest"
    is_skipped: bool = False
    id_status: str = "unique"
    substring_unsafe: bool = False
    steps: Optional[str] = None
    business_rule: Optional[str] = None
    expected_result: Optional[str] = None
    status: str = "draft"


class ImportPayload(BaseModel):
    cases: List[Dict[str, Any]]
    source: Optional[Dict[str, Any]] = None
    hygiene: Optional[Dict[str, Any]] = None


class JiraLinkPayload(BaseModel):
    jira_key: str
    link_kind: str = "covers"

    @field_validator("jira_key")
    @classmethod
    def validate_jira_key(cls, v: str) -> str:
        if not re.match(r"^[A-Z][A-Z0-9]+-\d+$", v):
            raise ValueError(f"Invalid Jira key format '{v}'. Must match '^[A-Z][A-Z0-9]+-\\d+$'")
        return v


class BulkJiraLinkPayload(BaseModel):
    case_ids: List[str]
    jira_key: str
    link_kind: str = "covers"

    @field_validator("jira_key")
    @classmethod
    def validate_jira_key(cls, v: str) -> str:
        if not re.match(r"^[A-Z][A-Z0-9]+-\d+$", v):
            raise ValueError(f"Invalid Jira key format '{v}'. Must match '^[A-Z][A-Z0-9]+-\\d+$'")
        return v


class RoleAssignmentPayload(BaseModel):
    email: str
    role: str

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        clean = v.strip().lower()
        if clean not in ("editor", "admin"):
            raise ValueError("Role must be 'editor' or 'admin'")
        return clean


class TriggerRequest(BaseModel):
    """Execution trigger payload with exact test case ID support."""
    environment: str = "pre-prod"
    job_name: Optional[str] = None
    filter_expr: Optional[str] = None
    case_ids: Optional[List[str]] = Field(default=None, max_length=20)

    @field_validator("case_ids")
    @classmethod
    def validate_case_ids(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return v
        if len(v) > 20:
            raise ValueError("Maximum 20 case_ids allowed per trigger run")
        pattern = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{2,99}$")
        for cid in v:
            if not pattern.match(cid):
                raise ValueError(
                    f"Invalid case_id '{cid}'. Must match ^[A-Za-z0-9][A-Za-z0-9_.-]{{2,99}}$"
                )
        return v

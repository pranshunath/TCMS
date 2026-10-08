"""Migration service and schema registry for trigger-service."""
import os
from pathlib import Path
from typing import List, Tuple
from app.services import db

_MIGRATIONS: Tuple[str, ...] = (
    "001_initial_schema",
    "002_test_runs",
    "003_test_case_results",
    "004_trigger_run_history",
    "005_run_jira_tickets",
    "006_environment_leases",
    "007_schema_migrations_lock",
    "008_tm_case",
    "009_tm_case_version",
    "010_tm_case_jira",
    "011_tm_role_assignment",
    "012_tm_audit_event",
)

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent.parent / "sql" / "migrations"


def get_available_migrations() -> List[str]:
    """Returns the ordered list of registered migration names."""
    return list(_MIGRATIONS)


def get_migration_sql_path(name: str) -> Path:
    """Returns the path to a migration's SQL file."""
    return MIGRATIONS_DIR / f"{name}.sql"


def get_applied_migrations() -> List[str]:
    """Queries applied migrations from SchemaMigrations table."""
    try:
        rows = db.query("SELECT name FROM SchemaMigrations ORDER BY id ASC")
        return [r["name"] for r in rows]
    except Exception:
        return []


def apply_migrations() -> List[str]:
    """Applies all pending migrations in contiguous order."""
    applied = set(get_applied_migrations())
    applied_now = []

    for name in _MIGRATIONS:
        if name in applied:
            continue

        sql_path = get_migration_sql_path(name)
        if not sql_path.exists():
            raise FileNotFoundError(f"Migration file not found: {sql_path}")

        sql_content = sql_path.read_text(encoding="utf-8")
        # Split statements if multiple, execute sequentially
        statements = [stmt.strip() for stmt in sql_content.split(";") if stmt.strip()]
        for stmt in statements:
            db.execute(stmt)

        db.execute("INSERT INTO SchemaMigrations (name) VALUES (%s)", (name,))
        applied_now.append(name)

    return applied_now

"""Database service providing raw SQL execution against MySQL."""
from typing import Any, Dict, List, Optional, Tuple, Union
import pymysql
import pymysql.cursors
from app.config import get_settings

# Double/hook for offline hermetic testing
_test_db_override = None


def set_test_db_override(override_obj: Any) -> None:
    """Set an in-memory double for testing (fake_db)."""
    global _test_db_override
    _test_db_override = override_obj


def get_connection() -> pymysql.Connection:
    settings = get_settings()

    # Safety assertion
    if settings.TRIGGER_DEV_AUTH and settings.REPORTING_PORT == 3306:
        raise RuntimeError(
            "CRITICAL SAFETY VIOLATION: Database connection refused. "
            "TRIGGER_DEV_AUTH is true and REPORTING_PORT is 3306."
        )

    return pymysql.connect(
        host=settings.REPORTING_HOST,
        port=settings.REPORTING_PORT,
        user=settings.REPORTING_USER,
        password=settings.REPORTING_PASSWORD,
        database=settings.REPORTING_DB,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


def _get_or_init_fallback():
    global _test_db_override
    if _test_db_override is None:
        from app.services.dev_double import create_seeded_dev_double
        _test_db_override = create_seeded_dev_double()
    return _test_db_override


def query(sql: str, params: Optional[Union[Tuple, Dict, List]] = None) -> List[Dict[str, Any]]:
    """Executes a SELECT query and returns rows as dictionaries."""
    if _test_db_override is not None:
        return _test_db_override.query(sql, params)

    try:
        conn = get_connection()
    except (pymysql.err.OperationalError, pymysql.err.MySQLError):
        settings = get_settings()
        if settings.TRIGGER_DEV_AUTH:
            double = _get_or_init_fallback()
            return double.query(sql, params)
        raise

    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, params or ())
            return cursor.fetchall()
    finally:
        conn.close()


def execute(sql: str, params: Optional[Union[Tuple, Dict, List]] = None) -> int:
    """Executes an INSERT, UPDATE, or DELETE query and returns rows affected or lastrowid."""
    if _test_db_override is not None:
        return _test_db_override.execute(sql, params)

    try:
        conn = get_connection()
    except (pymysql.err.OperationalError, pymysql.err.MySQLError):
        settings = get_settings()
        if settings.TRIGGER_DEV_AUTH:
            double = _get_or_init_fallback()
            return double.execute(sql, params)
        raise

    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, params or ())
            return cursor.lastrowid or cursor.rowcount
    finally:
        conn.close()

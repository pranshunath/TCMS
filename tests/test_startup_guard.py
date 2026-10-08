"""Tests for startup safety guard enforcing port 3306 protection."""
import pytest
from app.config import Settings
from app.main import verify_startup_safety
from app.services import db


def test_startup_guard_blocks_port_3306_with_dev_auth():
    settings = Settings(
        TRIGGER_DEV_AUTH=True,
        REPORTING_PORT=3306,
        REPORTING_HOST="127.0.0.1",
    )
    with pytest.raises(RuntimeError) as exc_info:
        verify_startup_safety(settings)
    assert "CRITICAL SAFETY VIOLATION" in str(exc_info.value)
    assert "3306" in str(exc_info.value)
    assert "3307" in str(exc_info.value)


def test_startup_guard_allows_port_3307_with_dev_auth():
    settings = Settings(
        TRIGGER_DEV_AUTH=True,
        REPORTING_PORT=3307,
        REPORTING_HOST="127.0.0.1",
    )
    # Should not raise any exception
    verify_startup_safety(settings)


def test_startup_guard_allows_non_dev_auth_on_prod_port():
    settings = Settings(
        TRIGGER_DEV_AUTH=False,
        REPORTING_PORT=3306,
        REPORTING_HOST="mysql-prod.internal",
    )
    # Production without dev auth should not be blocked by this dev check
    verify_startup_safety(settings)


def test_db_get_connection_enforces_port_3306_safety(monkeypatch):
    test_settings = Settings(
        TRIGGER_DEV_AUTH=True,
        REPORTING_PORT=3306,
        REPORTING_HOST="127.0.0.1",
    )
    monkeypatch.setattr("app.services.db.get_settings", lambda: test_settings)

    with pytest.raises(RuntimeError) as exc_info:
        db.get_connection()
    assert "CRITICAL SAFETY VIOLATION" in str(exc_info.value)
    assert "3306" in str(exc_info.value)

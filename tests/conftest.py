"""Pytest configuration and hermetic in-memory database test double."""
import pytest
from app.services import db
from app.services.dev_double import FakeDatabaseDouble


@pytest.fixture(autouse=True)
def fake_db():
    """Sets the in-memory FakeDatabaseDouble for all offline tests."""
    double = FakeDatabaseDouble()
    db.set_test_db_override(double)
    yield double
    db.set_test_db_override(None)

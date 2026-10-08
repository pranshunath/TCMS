"""Tests for migration integrity, contiguous numbering, and parity."""
from pathlib import Path
from app.services.schema import _MIGRATIONS, MIGRATIONS_DIR, get_available_migrations, get_migration_sql_path


def test_migrations_list_is_not_empty():
    assert len(_MIGRATIONS) >= 11


def test_migrations_have_contiguous_numbering():
    numbers = []
    for m in _MIGRATIONS:
        prefix = m.split("_")[0]
        assert prefix.isdigit(), f"Migration '{m}' does not start with digits"
        numbers.append(int(prefix))

    expected = list(range(1, len(_MIGRATIONS) + 1))
    assert numbers == expected, f"Migration numbering is not contiguous: {numbers} != {expected}"


def test_migrations_parity_with_sql_files():
    # Check that every migration in _MIGRATIONS has a corresponding SQL file
    for name in _MIGRATIONS:
        sql_path = get_migration_sql_path(name)
        assert sql_path.exists(), f"Migration SQL file missing: {sql_path}"

    # Check for orphan SQL files in sql/migrations/
    sql_files = list(MIGRATIONS_DIR.glob("*.sql"))
    sql_names = {f.stem for f in sql_files}
    registered_names = set(_MIGRATIONS)

    orphans = sql_names - registered_names
    assert not orphans, f"Found orphan SQL migration files not registered in _MIGRATIONS: {orphans}"


def test_new_migrations_start_at_008_and_contain_tm():
    for name in _MIGRATIONS:
        num = int(name.split("_")[0])
        if num >= 8:
            assert "tm_" in name, f"Migration {name} is >= 008 but does not contain 'tm_'"


def test_migrations_contain_create_table_only_and_no_alter():
    for name in _MIGRATIONS:
        sql_path = get_migration_sql_path(name)
        content = sql_path.read_text(encoding="utf-8").upper()

        assert "ALTER TABLE" not in content, f"ALTER TABLE found in {name}. Only CREATE TABLE allowed."
        assert "CREATE TABLE" in content, f"CREATE TABLE missing in {name}."

"""Unit tests for TCMS data store operations using the fake_db double."""
import pytest
from app.services import tcms_store


def test_create_and_get_case():
    case_data = {
        "case_id": "TC_REWARDS_001",
        "platform": "rewards",
        "title": "Verify user points balance on login",
        "area": "auth",
        "test_type": "api",
        "source_path": "tests/test_balance.py",
        "source_symbol": "test_balance",
        "steps": "1. Login with user\n2. Call GET /points",
        "business_rule": "Points must equal sum of completed transactions",
        "expected_result": "Status 200 with non-negative balance",
        "status": "draft",
    }
    created = tcms_store.create_case(case_data, user_email="qa@vananam.com")
    assert created["case_id"] == "TC_REWARDS_001"
    assert created["version"] == 1
    assert created["title"] == "Verify user points balance on login"
    assert created["created_by"] == "qa@vananam.com"

    fetched = tcms_store.get_case("TC_REWARDS_001")
    assert fetched is not None
    assert fetched["case_id"] == "TC_REWARDS_001"
    assert fetched["area"] == "auth"

    # Verify initial version snapshot in TmCaseVersion
    versions = tcms_store.get_case_versions("TC_REWARDS_001")
    assert len(versions) == 1
    assert versions[0]["version"] == 1
    assert versions[0]["edited_by"] == "qa@vananam.com"


def test_update_case_creates_version_n_plus_one():
    case_data = {
        "case_id": "TC_REWARDS_002",
        "platform": "rewards",
        "title": "Initial title",
        "area": "rewards",
        "status": "draft",
    }
    tcms_store.create_case(case_data, user_email="author@vananam.com")

    # First update
    updated = tcms_store.update_case(
        "TC_REWARDS_002",
        {"title": "Updated title", "steps": "Step 1: Check wallet", "status": "active"},
        user_email="editor@vananam.com",
        change_summary="Added steps and activated",
    )
    assert updated["version"] == 2
    assert updated["title"] == "Updated title"
    assert updated["status"] == "active"
    assert updated["updated_by"] == "editor@vananam.com"

    # Second update
    updated_v3 = tcms_store.update_case(
        "TC_REWARDS_002",
        {"business_rule": "Rule A"},
        user_email="admin@vananam.com",
    )
    assert updated_v3["version"] == 3
    assert updated_v3["business_rule"] == "Rule A"

    # Verify snapshots
    versions = tcms_store.get_case_versions("TC_REWARDS_002")
    assert len(versions) == 3
    v_nums = [v["version"] for v in versions]
    assert v_nums == [3, 2, 1]


def test_update_nonexistent_case_raises_error():
    with pytest.raises(ValueError) as exc:
        tcms_store.update_case("TC_NON_EXISTENT", {"title": "X"}, "user@vananam.com")
    assert "not found" in str(exc.value)


def test_list_cases_with_filters():
    tcms_store.create_case({"case_id": "TC_AUTH_1", "area": "auth", "status": "active", "title": "Login test"})
    tcms_store.create_case({"case_id": "TC_AUTH_2", "area": "auth", "status": "draft", "title": "Logout test"})
    tcms_store.create_case({"case_id": "TC_PAY_1", "area": "payment", "status": "active", "title": "Redeem points"})

    # All cases
    cases, total = tcms_store.list_cases()
    assert total >= 3

    # Filter by area
    cases_auth, total_auth = tcms_store.list_cases(area="auth")
    assert total_auth == 2
    assert all(c["area"] == "auth" for c in cases_auth)

    # Filter by status
    cases_draft, total_draft = tcms_store.list_cases(status="draft")
    assert any(c["case_id"] == "TC_AUTH_2" for c in cases_draft)

    # Search filter
    cases_search, total_search = tcms_store.list_cases(search="Redeem")
    assert total_search == 1
    assert cases_search[0]["case_id"] == "TC_PAY_1"


def test_jira_linking_idempotency_and_soft_delete():
    tcms_store.create_case({"case_id": "TC_JIRA_01", "title": "Jira linked case"})

    # Linking non-existent case fails
    with pytest.raises(ValueError):
        tcms_store.link_jira("TC_INVALID", "REW-101", user_email="qa@vananam.com")

    # Link to REW-101
    link = tcms_store.link_jira("TC_JIRA_01", "REW-101", user_email="qa@vananam.com")
    assert link["jira_key"] == "REW-101"
    assert link["case_id"] == "TC_JIRA_01"

    # Idempotent second link
    link2 = tcms_store.link_jira("TC_JIRA_01", "REW-101", user_email="qa@vananam.com")
    assert link2["jira_key"] == "REW-101"

    # Verify link appears on case
    case = tcms_store.get_case("TC_JIRA_01")
    assert len(case["jira_links"]) == 1
    assert case["jira_links"][0]["jira_key"] == "REW-101"

    # Query by Jira ticket
    linked_cases = tcms_store.list_cases_by_jira("REW-101")
    assert len(linked_cases) == 1
    assert linked_cases[0]["case_id"] == "TC_JIRA_01"

    # Unlink (soft delete)
    unlinked = tcms_store.unlink_jira("TC_JIRA_01", "REW-101", user_email="qa@vananam.com")
    assert unlinked is True

    # Active links should now be empty
    active_links = tcms_store.get_case_jira_links("TC_JIRA_01", include_removed=False)
    assert len(active_links) == 0

    # With include_removed=True, should show soft deleted
    all_links = tcms_store.get_case_jira_links("TC_JIRA_01", include_removed=True)
    assert len(all_links) == 1
    assert all_links[0]["removed_at"] is not None

    # Re-linking restores the link
    tcms_store.link_jira("TC_JIRA_01", "REW-101", user_email="qa@vananam.com")
    restored_links = tcms_store.get_case_jira_links("TC_JIRA_01", include_removed=False)
    assert len(restored_links) == 1
    assert restored_links[0]["removed_at"] is None


def test_bulk_jira_linking():
    tcms_store.create_case({"case_id": "TC_BULK_1"})
    tcms_store.create_case({"case_id": "TC_BULK_2"})

    res = tcms_store.bulk_link_jira(
        ["TC_BULK_1", "TC_BULK_2", "TC_NON_EXISTENT"],
        "REW-555",
        user_email="lead@vananam.com",
    )
    assert res["total_linked"] == 2
    assert "TC_BULK_1" in res["linked"]
    assert "TC_BULK_2" in res["linked"]
    assert len(res["errors"]) == 1
    assert res["errors"][0]["case_id"] == "TC_NON_EXISTENT"


def test_roles_resolution():
    admins_config = ["superadmin@vananam.com"]

    # Default role is viewer
    assert tcms_store.get_user_role("random@vananam.com", admins_config) == "viewer"
    assert tcms_store.get_user_role("", admins_config) == "viewer"

    # Config bootstrap admin
    assert tcms_store.get_user_role("superadmin@vananam.com", admins_config) == "admin"
    assert tcms_store.get_user_role("SUPERADMIN@VANANAM.COM", admins_config) == "admin"

    # Explicit role assignment
    tcms_store.assign_role("writer@vananam.com", "editor", assigned_by="superadmin@vananam.com")
    assert tcms_store.get_user_role("writer@vananam.com", admins_config) == "editor"

    # Upgrade to admin in DB
    tcms_store.assign_role("writer@vananam.com", "admin", assigned_by="superadmin@vananam.com")
    assert tcms_store.get_user_role("writer@vananam.com", admins_config) == "admin"


def test_import_scanned_cases():
    scanned_batch = [
        {
            "case_id": "TC_SCAN_01",
            "platform": "rewards",
            "title": "Title 1",
            "area": "cart",
            "test_type": "api",
            "source_path": "tests/test_cart.py",
            "source_symbol": "test_add_to_cart",
            "is_skipped": False,
            "id_status": "unique",
        },
        {
            "case_id": "TC_SCAN_02",
            "platform": "rewards",
            "title": "Title 2",
            "area": "checkout",
            "test_type": "api",
            "source_path": "tests/test_checkout.py",
            "source_symbol": "test_checkout",
            "is_skipped": False,
            "id_status": "unique",
        },
    ]

    # Initial import: both created
    res1 = tcms_store.import_scanned_cases(scanned_batch, user_email="importer@vananam.com")
    assert res1["created"] == 2
    assert res1["updated"] == 0

    # Human enriches TC_SCAN_01 with steps and business rule
    tcms_store.update_case(
        "TC_SCAN_01",
        {
            "steps": "1. Put item in cart\n2. Verify total",
            "business_rule": "Cart items must have positive quantity",
            "status": "active",
        },
        user_email="qa@vananam.com",
    )

    # Re-run scan with an updated title from code
    updated_batch = [
        {
            "case_id": "TC_SCAN_01",
            "platform": "rewards",
            "title": "New Title From Code Refactor",
            "area": "cart",
            "test_type": "api",
            "source_path": "tests/test_cart.py",
            "source_symbol": "test_add_to_cart",
        },
        {
            "case_id": "TC_SCAN_03",
            "platform": "rewards",
            "title": "Title 3",
            "area": "loyalty",
            "test_type": "grpc",
        },
    ]
    res2 = tcms_store.import_scanned_cases(updated_batch, user_email="importer@vananam.com")
    assert res2["created"] == 1
    assert res2["updated"] == 1

    # Verify TC_SCAN_01 retained its curated steps, rule, and active status
    c1 = tcms_store.get_case("TC_SCAN_01")
    assert c1["title"] == "New Title From Code Refactor"
    assert c1["steps"] == "1. Put item in cart\n2. Verify total"
    assert c1["business_rule"] == "Cart items must have positive quantity"
    assert c1["status"] == "active"

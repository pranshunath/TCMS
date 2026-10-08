"""Tests for Phase 11: Tamper-evident audit event log with SHA-256 hash chaining and Jira audit pack."""
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.services import tcms_store, tcms_audit

client = TestClient(app)


def test_audit_event_recorded_on_case_lifecycle(fake_db):
    headers = {"X-User-Email": "editor@vananam.com"}

    # 1. Create case
    case = tcms_store.create_case({
        "case_id": "TC_AUDIT_001",
        "title": "Audit trail test case",
        "area": "compliance",
        "status": "draft",
    }, user_email="editor@vananam.com")

    # Verify audit event recorded
    events = tcms_audit.get_audit_events_for_entity("case", "TC_AUDIT_001")
    assert len(events) >= 1
    create_ev = events[0]
    assert create_ev["event_type"] == "CASE_CREATED"
    assert create_ev["actor_email"] == "editor@vananam.com"
    assert create_ev["prev_hash"] == tcms_audit.GENESIS_HASH
    assert len(create_ev["event_hash"]) == 64

    # 2. Update case
    tcms_store.update_case("TC_AUDIT_001", {"title": "Updated Title"}, user_email="editor@vananam.com")
    events = tcms_audit.get_audit_events_for_entity("case", "TC_AUDIT_001")
    assert len(events) == 2
    update_ev = events[0]  # sorted DESC
    assert update_ev["event_type"] == "CASE_UPDATED"
    # Verify hash chaining
    assert update_ev["prev_hash"] == create_ev["event_hash"]


def test_audit_chain_verification_succeeds_when_untampered(fake_db):
    # Record multiple events
    tcms_store.create_case({"case_id": "TC_CHAIN_1", "title": "Chain 1"}, user_email="qa@vananam.com")
    tcms_store.create_case({"case_id": "TC_CHAIN_2", "title": "Chain 2"}, user_email="qa@vananam.com")
    tcms_store.link_jira("TC_CHAIN_1", "REW-9000", user_email="qa@vananam.com")

    # Verify chain
    result = tcms_audit.verify_audit_chain()
    assert result["valid"] is True
    assert result["total_events"] == 3
    assert result["tampered_event_id"] is None


def test_audit_chain_verification_fails_when_payload_tampered(fake_db):
    # Record events
    tcms_store.create_case({"case_id": "TC_TAMPER_1", "title": "Tamper 1"}, user_email="qa@vananam.com")
    tcms_store.create_case({"case_id": "TC_TAMPER_2", "title": "Tamper 2"}, user_email="qa@vananam.com")

    # Tamper with the first event payload directly in the database
    fake_db.audit_events[0]["payload_json"] = '{"tampered": "illegal modification"}'

    # Verify chain detects tampering
    result = tcms_audit.verify_audit_chain()
    assert result["valid"] is False
    assert result["tampered_event_id"] == fake_db.audit_events[0]["id"]
    assert "Tampered event" in result["reason"]


def test_audit_chain_verification_fails_when_chain_broken(fake_db):
    # Record 3 events
    tcms_store.create_case({"case_id": "TC_BREAK_1", "title": "Break 1"}, user_email="qa@vananam.com")
    tcms_store.create_case({"case_id": "TC_BREAK_2", "title": "Break 2"}, user_email="qa@vananam.com")
    tcms_store.create_case({"case_id": "TC_BREAK_3", "title": "Break 3"}, user_email="qa@vananam.com")

    # Tamper with prev_hash of event 2 (index 1)
    fake_db.audit_events[1]["prev_hash"] = "f" * 64

    # Verify chain detects broken link
    result = tcms_audit.verify_audit_chain()
    assert result["valid"] is False
    assert result["tampered_event_id"] == fake_db.audit_events[1]["id"]
    assert "Broken chain" in result["reason"]


def test_verify_audit_endpoint():
    headers = {"X-User-Email": "viewer@vananam.com"}
    response = client.get("/api/tcms/audit/verify", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "valid" in data
    assert "total_events" in data


def test_jira_audit_pack_generation():
    headers = {"X-User-Email": "viewer@vananam.com"}

    # Seed case and Jira link
    tcms_store.create_case({
        "case_id": "TC_PACK_001",
        "title": "Pack test case",
        "steps": "Step 1\nStep 2",
        "business_rule": "Rule 1",
        "expected_result": "Result 1",
        "status": "active",
    }, user_email="lead@vananam.com")

    tcms_store.link_jira("TC_PACK_001", "REW-7777", user_email="lead@vananam.com")

    # Request audit pack
    response = client.get("/api/tcms/jira/REW-7777/audit-pack", headers=headers)
    assert response.status_code == 200
    pack = response.json()

    assert pack["jira_key"] == "REW-7777"
    assert "compliance_report" in pack
    assert "case_specifications" in pack
    assert len(pack["case_specifications"]) == 1
    assert pack["case_specifications"][0]["case_id"] == "TC_PACK_001"
    assert "case_versions" in pack
    assert "TC_PACK_001" in pack["case_versions"]
    assert "audit_events" in pack
    assert "chain_verification" in pack
    assert pack["chain_verification"]["valid"] is True
    assert "pack_digest" in pack
    assert len(pack["pack_digest"]) == 64


def test_case_audit_trail_endpoint():
    headers = {"X-User-Email": "viewer@vananam.com"}
    tcms_store.create_case({"case_id": "TC_TRAIL_001", "title": "Trail"}, user_email="qa@vananam.com")

    response = client.get("/api/tcms/cases/TC_TRAIL_001/audit-trail", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["case_id"] == "TC_TRAIL_001"
    assert len(data["audit_events"]) >= 1
    assert data["audit_events"][0]["event_type"] == "CASE_CREATED"

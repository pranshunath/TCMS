"""Tamper-evident audit event log with SHA-256 hash chaining and SOC 2 audit pack generation."""
import hashlib
import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from app.services import db

GENESIS_HASH = "0" * 64


def canonical_json(data: Any) -> str:
    """Serializes data into canonical JSON with sorted keys and compact separators."""
    return json.dumps(data, sort_keys=True, separators=(',', ':'), default=str)


def calculate_event_hash(
    prev_hash: str,
    event_uuid: str,
    event_type: str,
    entity_type: str,
    entity_id: str,
    actor_email: str,
    payload_json: str,
) -> str:
    """Calculates SHA-256 hash over an audit event record."""
    data_str = f"{prev_hash}|{event_uuid}|{event_type}|{entity_type}|{entity_id}|{actor_email}|{payload_json}"
    return hashlib.sha256(data_str.encode("utf-8")).hexdigest()


def record_audit_event(
    event_type: str,
    entity_type: str,
    entity_id: str,
    actor_email: str,
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Records an audit event, chaining it to the latest event hash."""
    payload = payload or {}
    payload_str = canonical_json(payload)
    event_uuid = str(uuid.uuid4())

    # Get latest event hash
    latest_rows = db.query(
        "SELECT event_hash FROM TmAuditEvent ORDER BY id DESC LIMIT 1"
    )
    prev_hash = latest_rows[0]["event_hash"] if latest_rows else GENESIS_HASH

    event_hash = calculate_event_hash(
        prev_hash=prev_hash,
        event_uuid=event_uuid,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_email=actor_email,
        payload_json=payload_str,
    )

    sql = """
        INSERT INTO TmAuditEvent (
            event_uuid, event_type, entity_type, entity_id, actor_email,
            payload_json, prev_hash, event_hash
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """
    row_id = db.execute(
        sql,
        (
            event_uuid,
            event_type,
            entity_type,
            entity_id,
            actor_email,
            payload_str,
            prev_hash,
            event_hash,
        ),
    )

    return {
        "id": row_id,
        "event_uuid": event_uuid,
        "event_type": event_type,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "actor_email": actor_email,
        "payload": payload,
        "prev_hash": prev_hash,
        "event_hash": event_hash,
        "created_at": datetime.now().isoformat(),
    }


def verify_audit_chain(limit: Optional[int] = None) -> Dict[str, Any]:
    """Verifies the integrity of the audit event hash chain."""
    sql = "SELECT * FROM TmAuditEvent ORDER BY id ASC"
    if limit is not None:
        sql += f" LIMIT {int(limit)}"

    events = db.query(sql)
    if not events:
        return {
            "valid": True,
            "total_events": 0,
            "head_hash": GENESIS_HASH,
            "tampered_event_id": None,
            "reason": "Audit chain is empty",
        }

    for idx, ev in enumerate(events):
        ev_id = ev["id"]
        prev_hash = ev["prev_hash"]
        event_uuid = ev["event_uuid"]
        event_type = ev["event_type"]
        entity_type = ev["entity_type"]
        entity_id = ev["entity_id"]
        actor_email = ev["actor_email"]
        payload_json = ev["payload_json"]
        stored_hash = ev["event_hash"]

        # 1. Check genesis / link to predecessor
        if idx == 0:
            if prev_hash != GENESIS_HASH:
                return {
                    "valid": False,
                    "total_events": len(events),
                    "tampered_event_id": ev_id,
                    "reason": f"First event does not link to genesis hash ({prev_hash} != {GENESIS_HASH})",
                }
        else:
            prev_event_hash = events[idx - 1]["event_hash"]
            if prev_hash != prev_event_hash:
                return {
                    "valid": False,
                    "total_events": len(events),
                    "tampered_event_id": ev_id,
                    "reason": f"Broken chain at event {ev_id}: prev_hash does not match preceding event hash",
                }

        # 2. Recalculate hash over content
        expected_hash = calculate_event_hash(
            prev_hash=prev_hash,
            event_uuid=event_uuid,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            actor_email=actor_email,
            payload_json=payload_json,
        )

        if stored_hash != expected_hash:
            return {
                "valid": False,
                "total_events": len(events),
                "tampered_event_id": ev_id,
                "reason": f"Tampered event {ev_id}: stored event_hash does not match recalculated content hash",
            }

    return {
        "valid": True,
        "total_events": len(events),
        "head_hash": events[-1]["event_hash"],
        "tampered_event_id": None,
        "reason": "Audit chain intact and verified",
    }


def get_audit_events_for_entity(entity_type: str, entity_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Retrieves audit events for a specific entity."""
    sql = """
        SELECT * FROM TmAuditEvent
        WHERE entity_type = %s AND entity_id = %s
        ORDER BY id DESC
        LIMIT %s
    """
    rows = db.query(sql, (entity_type, entity_id, limit))
    for r in rows:
        if isinstance(r.get("payload_json"), str):
            try:
                r["payload"] = json.loads(r["payload_json"])
            except Exception:
                r["payload"] = r["payload_json"]
    return rows


def generate_jira_audit_pack(jira_key: str) -> Dict[str, Any]:
    """Generates a complete tamper-evident audit pack for a Jira key (SOC 2 Type II compliance)."""
    from app.services import tcms_store
    # 1. Fetch compliance execution report
    compliance_report = tcms_store.get_jira_compliance_report(jira_key)

    # 2. Extract linked cases and gather full specifications & historical versions
    linked_case_ids = [c["case_id"] for c in compliance_report.get("linked_cases", [])]
    case_specifications = []
    case_versions = {}

    for cid in linked_case_ids:
        case = tcms_store.get_case(cid)
        if case:
            case_specifications.append(case)
        versions = tcms_store.get_case_versions(cid)
        case_versions[cid] = versions

    # 3. Fetch audit events related to this Jira key and its linked cases
    audit_events: List[Dict[str, Any]] = []
    # Events for jira linking itself
    jira_events = get_audit_events_for_entity("jira_link", jira_key, limit=100)
    audit_events.extend(jira_events)

    for cid in linked_case_ids:
        c_events = get_audit_events_for_entity("case", cid, limit=50)
        audit_events.extend(c_events)

    # Deduplicate and sort by id ascending
    seen_ids = set()
    unique_audit_events = []
    for ev in audit_events:
        if ev["id"] not in seen_ids:
            seen_ids.add(ev["id"])
            unique_audit_events.append(ev)
    unique_audit_events.sort(key=lambda x: x["id"])

    # 4. Verify whole chain integrity
    chain_status = verify_audit_chain()

    # 5. Build pack and calculate overall pack signature
    now_str = datetime.now().isoformat()
    pack_data = {
        "jira_key": jira_key,
        "generated_at": now_str,
        "compliance_report": compliance_report,
        "case_specifications": case_specifications,
        "case_versions": case_versions,
        "audit_events": unique_audit_events,
        "chain_verification": chain_status,
    }

    # Digest over canonical pack content
    canonical_repr = canonical_json(pack_data)
    pack_digest = hashlib.sha256(canonical_repr.encode("utf-8")).hexdigest()

    pack_data["pack_digest"] = pack_digest
    return pack_data
